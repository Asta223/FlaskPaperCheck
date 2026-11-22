# -*- coding: utf-8 -*-
"""站内聊天增量：按姓名/工号查询同事、最近会话移除（保留记录、新消息重现）。"""
from conftest import get_csrf, login

from app import db
from app.models import ChatMessage, User
from app.services import chat_service


def _admin():
    return User.query.filter_by(username='admin').first()


def _leader():
    return User.query.filter_by(username='leader1').first()


def _send(client, receiver_id, content):
    token = get_csrf(client, '/chat/?peer_id=%d' % receiver_id)
    return client.post('/chat/send', data={
        'csrf_token': token, 'receiver_id': str(receiver_id), 'content': content,
    }, follow_redirects=True)


def _conv_section(html):
    """只取“最近会话”卡片，同事列表里也可能出现同名。"""
    return html.split('id="convList"', 1)[1].split('bi bi-people', 1)[0]


def test_search_colleagues_by_name_and_employee_no(client):
    login(client, 'admin', 'admin123')

    by_name = client.get('/chat/?q=张主管').get_data(as_text=True)
    assert '张主管' in by_name
    assert 'EMP0002' in by_name
    assert '王仓管' not in by_name

    by_no = client.get('/chat/?q=EMP0003').get_data(as_text=True)
    assert '王仓管' in by_no
    assert 'EMP0003' in by_no
    assert '张主管' not in by_no

    no_match = client.get('/chat/?q=不存在的人').get_data(as_text=True)
    assert '未找到匹配的同事' in no_match


def test_delete_conversation_hides_entry_but_keeps_messages(client):
    admin, leader = _admin(), _leader()
    login(client, 'admin', 'admin123')
    _send(client, leader.id, '会话保留测试')
    assert '张主管' in _conv_section(client.get('/chat/').get_data(as_text=True))

    token = get_csrf(client, '/chat/')
    resp = client.post('/chat/conversations/%d/delete' % leader.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert resp.status_code == 200
    assert '已从最近会话移除' in resp.get_data(as_text=True)
    assert '张主管' not in _conv_section(client.get('/chat/').get_data(as_text=True))
    # 消息本体保留，未删除
    assert ChatMessage.query.filter_by(sender_id=admin.id, receiver_id=leader.id,
                                       content='会话保留测试').first() is not None
    assert chat_service.conversation_list(admin.id) == []

    # 再次打开该会话会恢复显示
    client.get('/chat/?peer_id=%d' % leader.id)
    assert '张主管' in _conv_section(client.get('/chat/').get_data(as_text=True))


def test_hidden_conversation_reappears_on_new_unread(client):
    admin, leader = _admin(), _leader()
    login(client, 'admin', 'admin123')
    _send(client, leader.id, '第一条')
    token = get_csrf(client, '/chat/')
    client.post('/chat/conversations/%d/delete' % leader.id,
                data={'csrf_token': token})
    assert '张主管' not in _conv_section(client.get('/chat/').get_data(as_text=True))

    # 对方发来新消息：无需重新打开会话，未读会话自动重现
    client.get('/auth/logout')
    login(client, 'leader1', '123456')
    _send(client, admin.id, '新消息提醒')

    client.get('/auth/logout')
    login(client, 'admin', 'admin123')
    assert '张主管' in _conv_section(client.get('/chat/').get_data(as_text=True))


def test_delete_conversation_requires_csrf(client):
    leader = _leader()
    login(client, 'admin', 'admin123')
    resp = client.post('/chat/conversations/%d/delete' % leader.id, data={})
    assert resp.status_code == 400
