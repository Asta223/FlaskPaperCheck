# -*- coding: utf-8 -*-
"""站内聊天测试：发送/未读数/已读标记/增量拉取/IDOR/边界输入。"""
from conftest import get_csrf, login

from app import db
from app.models import ChatMessage, User
from app.services import chat_service


def _admin():
    return User.query.filter_by(username='admin').first()


def _leader():
    return User.query.filter_by(username='leader1').first()


def _send(client, receiver_id, content):
    # 发送表单只在会话窗口（有 peer）时渲染，token 须从带 peer_id 的页面取
    token = get_csrf(client, '/chat/?peer_id=%d' % receiver_id)
    return client.post('/chat/send', data={'csrf_token': token,
                                           'receiver_id': str(receiver_id),
                                           'content': content},
                       follow_redirects=True)


# ---------------- 基本收发 ----------------

def test_send_message_persisted(client):
    login(client, 'admin', 'admin123')
    leader = _leader()
    resp = _send(client, leader.id, '你好，主管')
    assert resp.status_code == 200
    msg = ChatMessage.query.filter_by(sender_id=_admin().id,
                                      receiver_id=leader.id).first()
    assert msg is not None and msg.content == '你好，主管'
    assert msg.is_read is False


def test_send_to_self_rejected(client):
    """发送给自己应被拒绝（token 从他人会话页取：发给自己时页面不渲染表单）。"""
    login(client, 'admin', 'admin123')
    leader = _leader()
    token = get_csrf(client, '/chat/?peer_id=%d' % leader.id)
    resp = client.post('/chat/send', data={'csrf_token': token,
                                           'receiver_id': str(_admin().id),
                                           'content': '自言自语'},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert ChatMessage.query.count() == 0


def test_send_to_inactive_rejected(client):
    login(client, 'admin', 'admin123')
    leader = _leader()
    leader.is_active = False
    db.session.commit()
    resp = _send(client, leader.id, '发给停用用户')
    assert resp.status_code == 200
    assert ChatMessage.query.count() == 0


def test_send_empty_content_rejected(client):
    login(client, 'admin', 'admin123')
    resp = _send(client, _leader().id, '')
    assert resp.status_code == 200
    assert ChatMessage.query.count() == 0


# ---------------- 未读与已读 ----------------

def test_unread_api_and_mark_read(client):
    """发送方 admin → 接收方 leader1：未读数、增量拉取、已读标记全链路。"""
    admin, leader = _admin(), _leader()
    # admin 发 2 条
    login(client, 'admin', 'admin123')
    _send(client, leader.id, '消息一')
    _send(client, leader.id, '消息二')
    # leader 查看
    login(client, 'leader1', '123456')
    resp = client.get('/chat/api/unread')
    data = resp.get_json()
    assert resp.status_code == 200 and data['code'] == 0
    assert data['data']['count'] == 2
    item = next(i for i in data['data']['items'] if i['partner_id'] == admin.id)
    assert item['count'] == 2 and item['last_message'] == '消息二'
    # 增量拉取 after_id=0 → 2 条
    resp = client.get('/chat/api/messages?peer_id=%d&after_id=0' % admin.id)
    data = resp.get_json()
    assert data['code'] == 0
    assert len(data['data']['messages']) == 2
    last_id = data['data']['last_id']
    # 增量拉取 after_id=last_id → 0 条
    resp = client.get('/chat/api/messages?peer_id=%d&after_id=%d' % (admin.id, last_id))
    assert len(resp.get_json()['data']['messages']) == 0
    # admin 再发一条 → 增量 1 条
    login(client, 'admin', 'admin123')
    _send(client, leader.id, '消息三')
    login(client, 'leader1', '123456')
    resp = client.get('/chat/api/messages?peer_id=%d&after_id=%d' % (admin.id, last_id))
    msgs = resp.get_json()['data']['messages']
    assert len(msgs) == 1 and msgs[0]['content'] == '消息三'
    # 标记已读
    resp = client.post('/chat/api/read', json={'peer_id': admin.id})
    assert resp.get_json()['code'] == 0
    resp = client.get('/chat/api/unread')
    assert resp.get_json()['data']['count'] == 0
    unread_msgs = ChatMessage.query.filter_by(receiver_id=leader.id, is_read=False).all()
    assert unread_msgs == []


def test_open_conversation_marks_read(client):
    """打开会话页自动将对方→我的消息标记已读。"""
    admin, leader = _admin(), _leader()
    db.session.add(ChatMessage(sender_id=admin.id, receiver_id=leader.id, content='看看'))
    db.session.commit()
    login(client, 'leader1', '123456')
    resp = client.get('/chat/?peer_id=%d' % admin.id)
    assert resp.status_code == 200
    db.session.expire_all()
    msg = ChatMessage.query.first()
    assert msg.is_read is True


def test_conversation_list_unread_counts(client):
    admin, leader = _admin(), _leader()
    db.session.add(ChatMessage(sender_id=admin.id, receiver_id=leader.id, content='a'))
    db.session.add(ChatMessage(sender_id=leader.id, receiver_id=admin.id, content='b'))
    db.session.commit()
    login(client, 'leader1', '123456')
    resp = client.get('/chat/')
    assert resp.status_code == 200
    convs = chat_service.conversation_list(leader.id)
    partner = next(c for c in convs if c['peer'].id == admin.id)
    assert partner['unread'] == 1


# ---------------- IDOR / 数据隔离 ----------------

def test_cannot_fetch_others_conversation(client):
    """staff1 无法通过 API 拉取 admin 与 leader1 之间的消息。"""
    admin, leader = _admin(), _leader()
    db.session.add(ChatMessage(sender_id=admin.id, receiver_id=leader.id, content='机密'))
    db.session.commit()
    login(client, 'staff1', '123456')
    resp = client.get('/chat/api/messages?peer_id=%d&after_id=0' % admin.id)
    data = resp.get_json()
    assert data['code'] == 0
    assert data['data']['messages'] == []  # 只会返回 staff1↔admin 的消息


# ---------------- 边界输入 ----------------

def test_send_content_over_limit_no_500(client):
    """超过 1000 字限制：应被表单校验拒绝而非 500/落库。"""
    login(client, 'admin', 'admin123')
    resp = _send(client, _leader().id, '超' * 2000)
    assert resp.status_code != 500
    assert ChatMessage.query.count() == 0


def test_send_whitespace_content_rejected(client):
    login(client, 'admin', 'admin123')
    resp = _send(client, _leader().id, '    ')
    assert resp.status_code != 500
    assert ChatMessage.query.count() == 0


def test_send_non_integer_receiver_id_no_500(client):
    """receiver_id 传非整数（'abc'）不应导致 500。"""
    login(client, 'admin', 'admin123')
    leader = _leader()
    token = get_csrf(client, '/chat/?peer_id=%d' % leader.id)
    resp = client.post('/chat/send', data={'csrf_token': token,
                                           'receiver_id': 'abc',
                                           'content': 'hello'},
                       follow_redirects=True)
    assert resp.status_code != 500, 'receiver_id=abc 引发了 500'
    assert ChatMessage.query.count() == 0


def test_api_messages_missing_peer_id(client):
    login(client, 'admin', 'admin123')
    resp = client.get('/chat/api/messages?after_id=0')
    assert resp.status_code == 400
    assert resp.get_json()['code'] != 0


def test_api_read_missing_peer_id(client):
    login(client, 'admin', 'admin123')
    resp = client.post('/chat/api/read', json={})
    assert resp.status_code == 400
    assert resp.get_json()['code'] != 0


def test_api_read_non_int_peer_id(client):
    login(client, 'admin', 'admin123')
    resp = client.post('/chat/api/read', json={'peer_id': 'abc'})
    assert resp.status_code != 500
