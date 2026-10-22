"""站内聊天路由：会话页、发送、JSON API（unread/messages/read，轮询 13s）。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import csrf, db
from app.forms.chat import ChatSendForm
from app.models.chat import ChatMessage
from app.models.user import User
from app.services import chat_service

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

    messages = []
    if peer is not None:
        messages = chat_service.pair_messages(current_user.id, peer.id)
        chat_service.mark_read(current_user.id, peer.id)  # 打开即已读

    colleagues = (User.query.filter(User.id != current_user.id, User.is_active.is_(True))
                  .order_by(User.name).all())
    form = ChatSendForm()
    if peer is not None:
        form.receiver_id.data = peer.id
    last_id = messages[-1].id if messages else 0
    return render_template('chat/index.html', conversations=conversations, peer=peer,
                           messages=messages, colleagues=colleagues, form=form,
                           last_id=last_id)


@bp.route('/send', methods=['POST'])
@login_required
def send():
    """发送消息（常规表单 POST，服务端渲染回聊天页）。"""
    form = ChatSendForm()
    if form.validate_on_submit():
        receiver = db.session.get(User, int(form.receiver_id.data))
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


@bp.route('/api/unread')
@login_required
def api_unread():
    """JSON：未读总数 + 每会话未读（base.html 13s 轮询）。"""
    return {'code': 0, 'data': chat_service.unread_summary(current_user.id), 'message': 'ok'}


@bp.route('/api/messages')
@login_required
def api_messages():
    """JSON：增量新消息（id > after_id）。"""
    peer_id = request.args.get('peer_id', type=int)
    after_id = request.args.get('after_id', 0, type=int)
    if not peer_id:
        return {'code': 1, 'data': None, 'message': '缺少 peer_id'}, 400
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
