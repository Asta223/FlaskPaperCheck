# -*- coding: utf-8 -*-
"""QA 独立验证：P1-13/14 聊天未读位点与 before_id 历史分页（含 P0 is_read 兼容）。"""
from conftest import login

from app import db
from app.models import ChatMessage, ConversationRead, User
from app.services import chat_service


def _admin():
    return User.query.filter_by(username='admin').first()


def _leader():
    return User.query.filter_by(username='leader1').first()


def _send(sender_id, receiver_id, content):
    msg = ChatMessage(sender_id=sender_id, receiver_id=receiver_id, content=content)
    db.session.add(msg)
    db.session.commit()
    return msg


class TestQAUnreadSite:
    """P1-14：未读按消息 id 位点精确计数，is_read 兼容 P0。"""

    def test_unread_after_partial_read_with_interleaved_ids(self, client):
        """已读位点之后的新消息必须计未读：id 有间隔时不能拿条数当位点。"""
        admin, leader = _admin(), _leader()
        first = _send(admin.id, leader.id, 'QA旧消息')
        for i in range(5):  # 对方回复多个消息，拉开 message id 间隔
            _send(leader.id, admin.id, 'QA自己回复%d' % i)
        second = _send(admin.id, leader.id, 'QA已读边界消息')

        login(client, 'leader1', '123456')
        client.post('/chat/api/read', json={'peer_id': admin.id})
        third = _send(admin.id, leader.id, 'QA新消息')

        data = client.get('/chat/api/unread').get_json()['data']
        site = ConversationRead.query.filter_by(user_id=leader.id, peer_id=admin.id).one()
        assert site.last_read_message_id == second.id
        assert chat_service.unread_count(leader.id) == 1
        assert data['chat_unread'] == 1, '位点之后的新消息（id=%s）应计未读' % third.id
        assert first.id < second.id < third.id

    def test_mark_read_idempotent_across_tabs(self, client):
        """重复标记已读不重复计数，ConversationRead 唯一且 is_read 语义保留。"""
        admin, leader = _admin(), _leader()
        _send(admin.id, leader.id, 'QA多标签1')
        _send(admin.id, leader.id, 'QA多标签2')
        login(client, 'leader1', '123456')
        client.post('/chat/api/read', json={'peer_id': admin.id})
        client.post('/chat/api/read', json={'peer_id': admin.id})

        assert ConversationRead.query.filter_by(user_id=leader.id, peer_id=admin.id).count() == 1
        assert chat_service.unread_count(leader.id) == 0
        assert ChatMessage.query.filter_by(receiver_id=leader.id, sender_id=admin.id,
                                           is_read=False).count() == 0

    def test_old_is_read_data_initialized_by_migration_sql(self, app_ctx):
        """迁移 SQL 语义：is_read=True 的最大 id 作为旧会话位点。"""
        admin, leader = _admin(), _leader()
        _send(admin.id, leader.id, 'QA旧1')
        old2 = _send(admin.id, leader.id, 'QA旧2')
        old2.is_read = True
        db.session.commit()
        recent = _send(admin.id, leader.id, 'QA新未读')

        row = db.session.execute(db.text(
            'SELECT receiver_id, sender_id, MAX(id) FROM chat_messages '
            'WHERE is_read = 1 GROUP BY receiver_id, sender_id')).fetchone()
        assert row is not None and row[2] == old2.id
        assert recent.id > old2.id


class TestQAHistoryPagination:
    """P1-13：before_id 应返回紧邻上一页（最新 limit 条），与 after_id 互斥。"""

    def test_before_id_returns_immediately_preceding_page(self, client):
        """35 条消息按 before_id=36、limit=10 取上一页 → 应为 id 26..35 升序。"""
        admin, leader = _admin(), _leader()
        msgs = [_send(admin.id, leader.id, 'QA历史%02d' % i) for i in range(35)]
        expected_ids = [m.id for m in msgs[-10:]]
        login(client, 'leader1', '123456')

        resp = client.get('/chat/api/messages?peer_id=%d&before_id=%d&limit=10'
                          % (admin.id, msgs[-1].id + 1))
        payload = resp.get_json()['data']
        actual_ids = [m['id'] for m in payload['messages']]

        assert payload['has_more'] is True
        assert actual_ids == expected_ids
        assert payload['earliest_id'] == expected_ids[0]

    def test_before_id_last_page_and_after_id_mutual_exclusion(self, client):
        """最后一页无更多；before_id 与 after_id 同时给出时以前者为准；不串会话。"""
        admin, leader = _admin(), _leader()
        staff = User.query.filter_by(username='staff1').first()
        msgs = [_send(admin.id, leader.id, 'QA倒序%d' % i) for i in range(6)]
        _send(staff.id, leader.id, 'QA别的会话')
        login(client, 'leader1', '123456')

        last_page = client.get('/chat/api/messages?peer_id=%d&before_id=%d&limit=10'
                               % (admin.id, msgs[-1].id + 1)).get_json()['data']
        both = client.get('/chat/api/messages?peer_id=%d&before_id=%d&after_id=0&limit=10'
                          % (admin.id, msgs[-1].id + 1)).get_json()['data']
        contents = [m['content'] for m in last_page['messages']]

        assert last_page['has_more'] is False
        assert [m['id'] for m in last_page['messages']] == [m.id for m in msgs]
        assert [m['id'] for m in both['messages']] == [m.id for m in msgs]
        assert 'QA别的会话' not in contents

    def test_p0_after_id_semantics_preserved(self, app_ctx):
        """P0 红线：默认 pair_messages 升序，after_id 增量语义不变。"""
        admin, leader = _admin(), _leader()
        m1 = _send(admin.id, leader.id, 'QA-P0-1')
        m2 = _send(admin.id, leader.id, 'QA-P0-2')
        all_msgs = chat_service.pair_messages(leader.id, admin.id)
        inc = chat_service.pair_messages(leader.id, admin.id, after_id=m1.id)
        assert [m.id for m in all_msgs] == [m1.id, m2.id]
        assert [m.id for m in inc] == [m2.id]
