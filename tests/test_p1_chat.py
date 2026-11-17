# -*- coding: utf-8 -*-
"""P1 聊天测试：ConversationRead 位点精确未读、before_id 历史分页、与 after_id 共存。"""
from conftest import get_csrf, login

from app import db
from app.models import ChatMessage, ConversationRead, User
from app.services import chat_service


def _admin():
    return User.query.filter_by(username='admin').first()


def _leader():
    return User.query.filter_by(username='leader1').first()


def _send(admin_id, leader_id, content):
    db.session.add(ChatMessage(sender_id=admin_id, receiver_id=leader_id, content=content))
    db.session.commit()


# ---------------- P1-14 未读位点精确计数 ----------------

def test_unread_by_message_count_not_conversation(client):
    """离线收到 N 条 → 角标精确 N（按条数，非会话数）。"""
    admin, leader = _admin(), _leader()
    _send(admin.id, leader.id, 'm1')
    _send(admin.id, leader.id, 'm2')
    _send(admin.id, leader.id, 'm3')
    login(client, 'leader1', '123456')
    data = client.get('/chat/api/unread').get_json()
    item = next(i for i in data['data']['items'] if i['partner_id'] == admin.id)
    assert data['data']['count'] == 3 and item['count'] == 3
    assert data['data']['chat_unread'] == 3
    assert data['data']['total'] >= 3


def test_mark_read_upserts_site(client):
    """标记已读 → 位点=最大 id，未读清零；位点持久化到 ConversationRead。"""
    admin, leader = _admin(), _leader()
    _send(admin.id, leader.id, 'a')
    _send(admin.id, leader.id, 'b')
    login(client, 'leader1', '123456')
    client.post('/chat/api/read', json={'peer_id': admin.id})
    db.session.expire_all()
    site = ConversationRead.query.filter_by(user_id=leader.id, peer_id=admin.id).first()
    assert site is not None and site.last_read_message_id > 0
    assert chat_service.unread_count(leader.id) == 0
    # is_read 语义保留兼容 P0
    assert ChatMessage.query.filter_by(receiver_id=leader.id, is_read=False).count() == 0


def test_site_survives_new_messages(client):
    """已读位点之后的新消息才计未读；旧消息不再计入。"""
    admin, leader = _admin(), _leader()
    _send(admin.id, leader.id, 'old1')
    login(client, 'leader1', '123456')
    client.post('/chat/api/read', json={'peer_id': admin.id})
    client.get('/auth/logout')
    _send(admin.id, leader.id, 'new1')
    _send(admin.id, leader.id, 'new2')
    login(client, 'leader1', '123456')
    assert chat_service.unread_count(leader.id) == 2


def test_multi_peer_unread_grouped(client):
    """多会话未读按 peer 分组，互不干扰。"""
    admin, leader = _admin(), _leader()
    staff = User.query.filter_by(username='staff1').first()
    _send(admin.id, leader.id, 'from admin')
    _send(staff.id, leader.id, 'from staff')
    login(client, 'leader1', '123456')
    um = chat_service.unread_by_peer(leader.id)
    assert um.get(admin.id) == 1 and um.get(staff.id) == 1


# ---------------- P1-13 before_id 历史分页 ----------------

def test_before_id_loads_earlier_page(app_ctx):
    """before_id 取更早一页（id 升序），不含等于/大于 before_id 的消息。"""
    admin, leader = _admin(), _leader()
    for i in range(35):
        _send(admin.id, leader.id, 'msg%d' % i)
    all_msgs = chat_service.pair_messages(leader.id, admin.id, limit=100000)
    assert len(all_msgs) == 35
    earliest_on_first_page = all_msgs[-20].id  # 首页是最后20条，其最小 id
    page2 = chat_service.pair_messages(leader.id, admin.id, before_id=earliest_on_first_page,
                                       limit=20)
    assert len(page2) == 15
    assert page2[-1].id < earliest_on_first_page
    assert [m.id for m in page2] == sorted(m.id for m in page2)  # 升序


def test_before_id_api_and_has_more(client):
    """API before_id 返回 data.earliest_id/has_more，且不串会话。"""
    admin, leader = _admin(), _leader()
    for i in range(25):
        _send(admin.id, leader.id, 'm%d' % i)
    login(client, 'leader1', '123456')
    all_msgs = chat_service.pair_messages(leader.id, admin.id, limit=100000)
    earliest = all_msgs[-20].id
    resp = client.get('/chat/api/messages?peer_id=%d&before_id=%d&limit=20' % (admin.id, earliest))
    data = resp.get_json()
    assert data['code'] == 0
    assert len(data['data']['messages']) == 5
    assert data['data']['has_more'] is False


def test_after_id_default_behavior_preserved(app_ctx):
    """P0 红线：pair_messages 默认返回全部（升序），after_id 增量不变。"""
    admin, leader = _admin(), _leader()
    _send(admin.id, leader.id, 'x1')
    _send(admin.id, leader.id, 'x2')
    msgs = chat_service.pair_messages(leader.id, admin.id)
    assert len(msgs) == 2 and msgs[0].id < msgs[1].id
    inc = chat_service.pair_messages(leader.id, admin.id, after_id=msgs[0].id)
    assert len(inc) == 1 and inc[0].content == 'x2'


def test_before_id_not_mix_other_peer(client):
    """before_id 分页仅加载当前会话双方消息，不串其他会话。"""
    admin, leader = _admin(), _leader()
    staff = User.query.filter_by(username='staff1').first()
    for i in range(3):
        _send(admin.id, leader.id, 'a%d' % i)
    _send(staff.id, leader.id, 'from staff')
    login(client, 'leader1', '123456')
    all_msgs = chat_service.pair_messages(leader.id, admin.id, limit=100000)
    before = all_msgs[1].id
    resp = client.get('/chat/api/messages?peer_id=%d&before_id=%d' % (admin.id, before))
    contents = [m['content'] for m in resp.get_json()['data']['messages']]
    assert 'from staff' not in contents
