"""站内聊天服务：未读聚合、会话列表、已读标记。"""
from sqlalchemy import or_

from app import db
from app.models.chat import ChatMessage
from app.models.user import User


def unread_count(user_id: int) -> int:
    """未读消息总数。"""
    return ChatMessage.query.filter_by(receiver_id=user_id, is_read=False).count()


def unread_summary(user_id: int, limit: int = 20) -> dict:
    """未读汇总（/chat/api/unread 载荷）：总数 + 按发送人分组列表。"""
    msgs = (ChatMessage.query
            .filter_by(receiver_id=user_id, is_read=False)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .all())
    groups = {}
    order = []
    for msg in msgs:
        if msg.sender_id not in groups:
            groups[msg.sender_id] = {'count': 0, 'last_message': msg.content or ''}
            order.append(msg.sender_id)
        groups[msg.sender_id]['count'] += 1
    items = []
    for sender_id in order[:limit]:
        sender = db.session.get(User, sender_id)
        items.append({
            'partner_id': sender_id,
            'partner_name': sender.display_name() if sender else '未知用户',
            'count': groups[sender_id]['count'],
            'last_message': (groups[sender_id]['last_message'] or '')[:50],
        })
    return {'count': len(msgs), 'items': items}


def conversation_list(user_id: int) -> list:
    """会话列表：按对方聚合双方消息，取最近一条，附未读数，按最近时间倒序。

    返回 [{'peer': User, 'last_message': str, 'last_time': datetime, 'unread': int}, ...]
    """
    msgs = (ChatMessage.query
            .filter(or_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == user_id))
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .all())
    peers = {}
    for msg in msgs:
        peer_id = msg.receiver_id if msg.sender_id == user_id else msg.sender_id
        if peer_id not in peers:
            peers[peer_id] = msg  # 首次出现即最近一条（已按时间倒序）

    unread_map = dict(
        db.session.query(ChatMessage.sender_id, db.func.count())
        .filter_by(receiver_id=user_id, is_read=False)
        .group_by(ChatMessage.sender_id)
        .all()
    )

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
    """标记 peer → user 的全部消息为已读。"""
    ChatMessage.query.filter_by(receiver_id=user_id, sender_id=peer_id,
                                is_read=False).update({'is_read': True})
    db.session.commit()


def pair_messages(user_id: int, peer_id: int, after_id: int = 0, limit: int = 200) -> list:
    """与某对方的双方消息（增量：id > after_id），按 id 升序。"""
    return (ChatMessage.query
            .filter(or_(
                db.and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == peer_id),
                db.and_(ChatMessage.sender_id == peer_id, ChatMessage.receiver_id == user_id),
            ), ChatMessage.id > after_id)
            .order_by(ChatMessage.id.asc())
            .limit(limit)
            .all())
