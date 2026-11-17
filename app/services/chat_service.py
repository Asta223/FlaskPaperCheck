"""站内聊天服务：未读位点（ConversationRead）、会话列表、已读标记、分页消息。

P0 兼容红线（不可破坏）：
- pair_messages(user, peer, after_id, limit) 默认行为与返回不变（按 id 升序，limit 默认 200）；
- mark_read 仍把 is_read 更新为 True，未读消息 is_read=False 语义保留；
- 老数据用 is_read=True 的最大 id 初始化位点（迁移已完成，运行时缺省位点=0）。

P1 增量：未读计数改用持久化位点按条数精确计算；pair_messages 增 before_id 加载更早页。
"""
from sqlalchemy import func, or_

from app import db
from app.models.chat import ChatMessage, ConversationRead
from app.models.user import User
from app.utils.time_utils import now


def _get_site(user_id: int, peer_id: int) -> int:
    """读取 user 对 peer 的已读位点（缺省 0）。"""
    row = (ConversationRead.query
           .filter_by(user_id=user_id, peer_id=peer_id).first())
    return row.last_read_message_id if row else 0


def _set_site(user_id: int, peer_id: int, last_id: int) -> None:
    """ upsert 已读位点（查-改-增，兼容 SQLite/MySQL）。"""
    row = (ConversationRead.query
           .filter_by(user_id=user_id, peer_id=peer_id).first())
    if row is None:
        row = ConversationRead(user_id=user_id, peer_id=peer_id,
                               last_read_message_id=last_id, updated_at=now())
        db.session.add(row)
    elif row.last_read_message_id < last_id:
        row.last_read_message_id = last_id
        row.updated_at = now()


def unread_count(user_id: int) -> int:
    """未读消息总数（基于位点的精确计数，替代 is_read 布尔计数）。"""
    sites = {
        r.peer_id: r.last_read_message_id
        for r in ConversationRead.query.filter_by(user_id=user_id).all()
    }
    msgs = (db.session.query(ChatMessage.sender_id, func.count())
            .filter(ChatMessage.receiver_id == user_id)
            .group_by(ChatMessage.sender_id).all())
    total = 0
    for sender_id, count in msgs:
        total += count - sites.get(sender_id, 0) if count > sites.get(sender_id, 0) else 0
    return total


def unread_by_peer(user_id: int) -> dict:
    """按会话分组的精确未读计数 {peer_id: count}。"""
    sites = {
        r.peer_id: r.last_read_message_id
        for r in ConversationRead.query.filter_by(user_id=user_id).all()
    }
    rows = (db.session.query(ChatMessage.sender_id, func.count())
            .filter(ChatMessage.receiver_id == user_id)
            .group_by(ChatMessage.sender_id).all())
    return {
        sender_id: count - sites.get(sender_id, 0)
        for sender_id, count in rows if count > sites.get(sender_id, 0)
    }


def unread_summary(user_id: int, limit: int = 20) -> dict:
    """未读汇总（/chat/api/unread 载荷）：精确总数 + 按会话分组列表 + 预警聚合。"""
    unread_map = unread_by_peer(user_id)
    total = sum(unread_map.values())

    # 每个会话的最新一条消息内容（用于摘要）
    latest = {}
    msgs = (ChatMessage.query
            .filter(ChatMessage.receiver_id == user_id,
                    ChatMessage.sender_id.in_(list(unread_map.keys()) or [-1]))
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).all())
    for msg in msgs:
        if msg.sender_id not in latest:
            latest[msg.sender_id] = msg.content or ''

    items = []
    for peer_id in sorted(unread_map, key=lambda pid: -unread_map[pid])[:limit]:
        sender = db.session.get(User, peer_id)
        items.append({
            'partner_id': peer_id,
            'partner_name': sender.display_name() if sender else '未知用户',
            'count': unread_map[peer_id],
            'last_message': (latest.get(peer_id, '') or '')[:50],
        })

    # P1-09 顶部角标聚合：聊天未读 + 库存预警未读
    warning_unread = 0
    try:
        from app.services.notification_service import unread_warning_count
        warning_unread = unread_warning_count(user_id)
    except Exception:
        pass
    return {
        'count': total,
        'items': items,
        'chat_unread': total,
        'warning_unread': warning_unread,
        'total': total + warning_unread,
    }


def conversation_list(user_id: int) -> list:
    """会话列表：按对方聚合双方消息，取最近一条，附精确未读数，按最近时间倒序。"""
    msgs = (ChatMessage.query
            .filter(or_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == user_id))
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .all())
    peers = {}
    for msg in msgs:
        peer_id = msg.receiver_id if msg.sender_id == user_id else msg.sender_id
        if peer_id not in peers:
            peers[peer_id] = msg

    unread_map = unread_by_peer(user_id)

    result = []
    for peer_id, msg in peers.items():
        peer = db.session.get(User, peer_id)
        if peer is None:
            continue
        result.append({
            'peer': peer,
            'last_message': (msg.content or '')[:50],
            'last_time': msg.created_at,
            'unread': unread_map.get(peer_id, 0),
        })
    return result


def mark_read(user_id: int, peer_id: int) -> None:
    """标记 peer→user 的消息为已读：写位点 + 保留 is_read 语义（兼容 P0）。"""
    max_id = db.session.query(func.max(ChatMessage.id)).filter(
        ChatMessage.sender_id == peer_id, ChatMessage.receiver_id == user_id).scalar() or 0
    _set_site(user_id, peer_id, max_id)
    ChatMessage.query.filter_by(receiver_id=user_id, sender_id=peer_id,
                                is_read=False).update({'is_read': True})
    db.session.commit()


def pair_messages(user_id: int, peer_id: int, after_id: int = 0, limit: int = 200,
                  before_id: int = None) -> list:
    """与某对方的双方消息（P0：id>after_id 升序；P1：before_id 加载更早页）。

    - before_id 缺省：保持 P0 行为（id>after_id，升序，limit 默认 200）。
    - before_id 提供：取 id<before_id 的最近 limit 条（先倒序取再反转），返回升序，
      供前端追加到顶部。与 after_id 互斥（before_id 优先）。
    """
    pair_filter = or_(
        db.and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == peer_id),
        db.and_(ChatMessage.sender_id == peer_id, ChatMessage.receiver_id == user_id),
    )
    if before_id is not None and before_id > 0:
        page = (ChatMessage.query
                .filter(pair_filter, ChatMessage.id < before_id)
                .order_by(ChatMessage.id.desc())
                .limit(limit).all())
        return list(reversed(page))
    return (ChatMessage.query
            .filter(pair_filter, ChatMessage.id > after_id)
            .order_by(ChatMessage.id.asc())
            .limit(limit)
            .all())
