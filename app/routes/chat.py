"""站内聊天路由：会话页、发送、JSON API（unread/messages/read，轮询 13s）。"""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import csrf, db
from app.forms.chat import ChatSendForm
from app.models.chat import ChatMessage
from app.models.user import User
from app.services import chat_service
from app.services.soft_delete_service import mark_deleted

bp = Blueprint('chat', __name__, url_prefix='/chat')


@bp.route('/')
@login_required
def index():
    """会话列表 + 聊天窗口（?peer_id= 指定对方）。"""
    peer_id = request.args.get('peer_id', type=int)
    conversations = chat_service.conversation_list(current_user.id)
    peer = db.session.get(User, peer_id) if peer_id else None
    if peer is not None and peer.id == current_user.id:
        peer = None
    if peer is not None:
        chat_service.unhide_conversation(current_user.id, peer.id)

    messages = []
    earliest_id = 0
    has_more = False
    if peer is not None:
        # 首屏加载最近 20 条（P1-13），并判断是否还有更早消息
        all_count = chat_service.pair_messages(current_user.id, peer.id, limit=100000)
        messages = all_count[-20:]
        earliest_id = messages[0].id if messages else 0
        has_more = len(all_count) > len(messages)
        chat_service.mark_read(current_user.id, peer.id)  # 打开即已读

    q = request.args.get('q', '').strip()
    all_colleagues = (User.query.filter(User.id != current_user.id, User.is_active.is_(True))
                      .order_by(User.name).all())
    if q:
        needle = q.lower()
        colleagues = [u for u in all_colleagues
                      if needle in (u.name or '').lower()
                      or needle in (u.employee_no or '').lower()
                      or needle in (u.username or '').lower()]
    else:
        colleagues = all_colleagues
    form = ChatSendForm()
    if peer is not None:
        form.receiver_id.data = peer.id
    last_id = messages[-1].id if messages else 0
    return render_template('chat/index.html', conversations=conversations, peer=peer,
                           messages=messages, colleagues=colleagues, form=form,
                           last_id=last_id, earliest_id=earliest_id, has_more=has_more, q=q)


@bp.route('/send', methods=['POST'])
@login_required
def send():
    """发送消息（常规表单 POST，服务端渲染回聊天页）。"""
    form = ChatSendForm()
    if form.validate_on_submit():
        try:
            receiver_id = int(form.receiver_id.data)
        except (TypeError, ValueError):
            receiver_id = 0
        receiver = db.session.get(User, receiver_id)
        if receiver is None or not receiver.is_active or receiver.id == current_user.id:
            flash('接收人不存在或已停用', 'danger')
        else:
            db.session.add(ChatMessage(sender_id=current_user.id, receiver_id=receiver.id,
                                       content=form.content.data.strip()))
            db.session.commit()
            return redirect(url_for('chat.index', peer_id=receiver.id))
    else:
        flash('消息不能为空', 'danger')
    return redirect(url_for('chat.index'))


@bp.route('/conversations/<int:peer_id>/delete', methods=['POST'])
@login_required
def conversation_delete(peer_id):
    """从最近会话移除：仅隐藏本端入口，消息保留；对方再发消息会自动重现。"""
    if peer_id == current_user.id:
        abort(400)
    chat_service.hide_conversation(current_user.id, peer_id)
    flash('已从最近会话移除，聊天记录仍保留；对方再发消息会重新显示', 'success')
    return redirect(url_for('chat.index', q=request.args.get('q', '')))


@bp.route('/messages/<int:msg_id>/delete', methods=['POST'])
@login_required
def message_delete(msg_id):
    """软删除聊天消息（撤回）：仅发送人本人可删，回收站可恢复。"""
    msg = db.get_or_404(ChatMessage, msg_id)
    if msg.sender_id != current_user.id:
        abort(403)
    receiver_id = msg.receiver_id
    mark_deleted(msg, module='chat', target_type='chat_message',
                 summary='撤回消息#%s（软删除，可在回收站恢复）' % msg_id)
    return jsonify({'code': 0, 'data': {'id': msg_id, 'peer_id': receiver_id},
                    'message': 'ok'})


@bp.route('/api/unread')
@login_required
def api_unread():
    """JSON：未读总数 + 每会话未读（base.html 13s 轮询）。"""
    return {'code': 0, 'data': chat_service.unread_summary(current_user.id), 'message': 'ok'}


@bp.route('/api/messages')
@login_required
def api_messages():
    """JSON：增量新消息（after_id）或更早历史页（before_id），二者互斥。"""
    peer_id = request.args.get('peer_id', type=int)
    after_id = request.args.get('after_id', 0, type=int)
    before_id = request.args.get('before_id', type=int)
    limit = request.args.get('limit', 20, type=int)
    limit = max(1, min(limit or 20, 100))
    if not peer_id:
        return {'code': 1, 'data': None, 'message': '缺少 peer_id'}, 400

    if before_id is not None and before_id > 0:
        # 历史页：用 before_id+1 作边界再多取 1 条判断 has_more
        window = chat_service.pair_messages(current_user.id, peer_id,
                                            before_id=before_id, limit=limit + 1)
        has_more = len(window) > limit
        # window 为 id 升序：紧邻 before_id 的是末尾 limit 条（取最靠前的更早页）
        msgs = window[-limit:]
        earliest_id = msgs[0].id if msgs else before_id
        return {'code': 0,
                'data': {'messages': [m.to_dict() for m in msgs],
                         'earliest_id': earliest_id, 'has_more': has_more},
                'message': 'ok'}

    # P0 默认分支：after_id 增量，保持原行为（limit 200 默认）
    msgs = chat_service.pair_messages(current_user.id, peer_id, after_id=after_id)
    last_id = msgs[-1].id if msgs else after_id
    return {'code': 0,
            'data': {'messages': [m.to_dict() for m in msgs], 'last_id': last_id},
            'message': 'ok'}


@bp.route('/api/read', methods=['POST'])
@login_required
@csrf.exempt
def api_read():
    """JSON：标记对方→我 的消息为已读。"""
    payload = request.get_json(silent=True) or request.form
    try:
        peer_id = int(payload.get('peer_id', 0))
    except (TypeError, ValueError):
        peer_id = 0
    if not peer_id:
        return {'code': 1, 'data': None, 'message': '缺少 peer_id'}, 400
    chat_service.mark_read(current_user.id, peer_id)
    return {'code': 0, 'data': {'peer_id': peer_id}, 'message': 'ok'}
