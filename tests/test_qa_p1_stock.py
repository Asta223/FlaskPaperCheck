# -*- coding: utf-8 -*-
"""QA 独立验证：P1-05/06/07/08/09 库存流水、领料原子性、关联与预警。"""
from conftest import get_csrf, login

from app import db
from app.models import (Inventory, Material, Notification, OperationLog, StockDocument,
                        StockLedger, StockWarningState, User, Warehouse, WorkOrder)
from app.services.inventory_service import apply_stock_document
from app.utils.time_utils import now


def _wh_mat():
    return (Warehouse.query.filter_by(name='原材料仓').first(),
            Material.query.filter_by(code='M0001').first())


def _keeper():
    return User.query.filter_by(username='keeper1').first()


class TestQAStockLedger:
    """P1-07：流水前后余额、不可变、失败零落库。"""

    def test_ledger_balances_and_no_mutating_routes(self, client):
        wh, mat = _wh_mat()
        doc_in = apply_stock_document('in', wh.id, mat.id, 100, _keeper().id, _keeper().id)
        doc_out = apply_stock_document('out', wh.id, mat.id, 30, _keeper().id, _keeper().id)
        led_in = StockLedger.query.filter_by(doc_no=doc_in.doc_no).one()
        led_out = StockLedger.query.filter_by(doc_no=doc_out.doc_no).one()

        assert (led_in.before_balance, led_in.after_balance) == (0, 100)
        assert (led_out.before_balance, led_out.after_balance) == (100, 70)
        assert led_out.handler_id == _keeper().id

        login(client, 'admin', 'admin123')
        assert client.post('/warehouse/ledger/%d/delete' % led_in.id).status_code in (404, 405)
        assert client.post('/warehouse/ledger/%d/edit' % led_in.id).status_code in (404, 405)
        assert client.get('/warehouse/ledger/%d/edit' % led_in.id).status_code in (404, 405)

    def test_failed_out_has_zero_side_effects_through_route(self, client):
        """余量不足：库存/单据/流水/日志全部零落库，并提示当前余量。"""
        wh, mat = _wh_mat()
        apply_stock_document('in', wh.id, mat.id, 10, _keeper().id, _keeper().id)
        inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).one()
        before = (inv.quantity, StockDocument.query.count(), StockLedger.query.count(),
                  Notification.query.count())

        login(client, 'keeper1', '123456')
        token = get_csrf(client, '/warehouse/docs/new')
        resp = client.post('/warehouse/docs/new', data={
            'csrf_token': token, 'doc_type': 'out', 'warehouse_id': wh.id,
            'material_id': mat.id, 'quantity': 999, 'related_order_id': 0, 'remark': 'QA不足',
        }, follow_redirects=True)

        db.session.expire_all()
        after = (inv.quantity, StockDocument.query.count(), StockLedger.query.count(),
                 Notification.query.count())
        assert resp.status_code == 200
        assert '库存不足' in resp.data.decode('utf-8')
        assert '10' in resp.data.decode('utf-8')
        assert before == after

    def test_related_order_zero_normalized_to_none(self, app_ctx):
        """related_order_id=0 规范化为 None，不产生悬空外键；单据/流水一致。"""
        wh, mat = _wh_mat()
        doc = apply_stock_document('in', wh.id, mat.id, 5, _keeper().id, _keeper().id,
                                   related_order_id=0)
        led = StockLedger.query.filter_by(doc_no=doc.doc_no).one()
        assert doc.related_order_id is None
        assert led.related_order_id is None


class TestQAIssueLink:
    """P1-05/06/08：领料三步原子 + 工单/单据双向可查。"""

    def test_issue_is_atomic_and_bidirectionally_queryable(self, client):
        wh, mat = _wh_mat()
        apply_stock_document('in', wh.id, mat.id, 50, _keeper().id, _keeper().id)
        order = WorkOrder.query.first()
        login(client, 'producer1', '123456')
        token = get_csrf(client, '/production/orders/%d' % order.id)
        resp = client.post('/production/orders/%d/issue' % order.id, data={
            'csrf_token': token, 'warehouse_id': wh.id, 'material_id': mat.id,
            'quantity': 12, 'remark': 'QA领料',
        }, follow_redirects=True)

        db.session.expire_all()
        doc = StockDocument.query.filter_by(related_order_id=order.id, doc_type='out').one()
        led = StockLedger.query.filter_by(doc_no=doc.doc_no).one()
        logs = OperationLog.query.filter_by(target_type='work_order', target_id=order.id,
                                            action='issue').all()
        detail = client.get('/production/orders/%d' % order.id).data.decode('utf-8')
        login(client, 'admin', 'admin123')  # 流水页需 warehouse.ledger.view
        ledger_page = client.get('/warehouse/ledger').data.decode('utf-8')

        assert resp.status_code == 200
        assert doc.quantity == 12 and led.related_order_id == order.id
        assert led.before_balance == 50 and led.after_balance == 38
        assert len(logs) == 1
        assert '物料领用' in detail and doc.doc_no in detail
        assert '操作日志' in detail and doc.doc_no in ledger_page
        assert order.order_no in ledger_page

    def test_failed_issue_leaves_no_work_order_log(self, client):
        """库存不足领料：工单日志也不产生。"""
        wh, mat = _wh_mat()
        order = WorkOrder.query.first()
        before = OperationLog.query.filter_by(target_type='work_order',
                                              target_id=order.id).count()
        login(client, 'producer1', '123456')
        token = get_csrf(client, '/production/orders/%d' % order.id)
        client.post('/production/orders/%d/issue' % order.id, data={
            'csrf_token': token, 'warehouse_id': wh.id, 'material_id': mat.id,
            'quantity': 999, 'remark': '',
        }, follow_redirects=True)
        db.session.expire_all()
        assert OperationLog.query.filter_by(target_type='work_order',
                                            target_id=order.id).count() == before


class TestQAStockWarning:
    """P1-09：去重状态机、失败隔离、角标聚合。"""

    def test_low_high_low_cycle_via_real_documents(self, app_ctx):
        wh, mat = _wh_mat()
        inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).one()
        inv.warn_threshold = 10
        db.session.commit()
        keeper_id = _keeper().id
        apply_stock_document('in', wh.id, mat.id, 15, keeper_id, keeper_id)  # 15 > 10 不推
        first = Notification.query.filter_by(receiver_id=keeper_id,
                                             notif_type='stock_warning').count()
        assert first == 0

        apply_stock_document('out', wh.id, mat.id, 10, keeper_id, keeper_id)  # 5 <= 10 推一次
        after_drop = Notification.query.filter_by(receiver_id=keeper_id,
                                                  notif_type='stock_warning').count()
        apply_stock_document('out', wh.id, mat.id, 1, keeper_id, keeper_id)  # 仍低位不重复
        after_more_out = Notification.query.filter_by(receiver_id=keeper_id,
                                                      notif_type='stock_warning').count()
        apply_stock_document('in', wh.id, mat.id, 20, keeper_id, keeper_id)  # 回升复位
        state = StockWarningState.query.filter_by(warehouse_id=wh.id, material_id=mat.id).one()
        assert state.is_low is False
        apply_stock_document('out', wh.id, mat.id, 19, keeper_id, keeper_id)  # 再跌破可再推
        after_second_drop = Notification.query.filter_by(receiver_id=keeper_id,
                                                         notif_type='stock_warning').count()
        assert after_drop >= 1
        assert after_more_out == after_drop
        assert after_second_drop > after_drop

    def test_warning_failure_does_not_roll_back_document(self, app_ctx, monkeypatch):
        """monkeypatch 推送抛错：单据/库存/流水已提交，不受影响。"""
        import app.services.notification_service as notif_mod

        def boom(*_args, **_kwargs):
            raise RuntimeError('QA simulated push failure')

        monkeypatch.setattr(notif_mod, 'push_stock_warning', boom)
        wh, mat = _wh_mat()
        keeper_id = _keeper().id
        before_docs = StockDocument.query.count()

        doc = apply_stock_document('in', wh.id, mat.id, 33, keeper_id, keeper_id)

        db.session.expire_all()
        inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).one()
        assert StockDocument.query.count() == before_docs + 1
        assert StockLedger.query.filter_by(doc_no=doc.doc_no).count() == 1
        assert inv.quantity == 33

    def test_badge_aggregates_chat_and_warning_unread(self, client):
        """角标 total = 聊天未读 + 库存预警未读，互不串号。"""
        from app.models import ChatMessage
        from app.services.notification_service import unread_warning_count

        keeper = _keeper()
        leader = User.query.filter_by(username='leader1').first()
        db.session.add_all([
            ChatMessage(sender_id=keeper.id, receiver_id=leader.id, content='QA聊天1'),
            ChatMessage(sender_id=keeper.id, receiver_id=leader.id, content='QA聊天2'),
            Notification(receiver_id=leader.id, notif_type='stock_warning',
                         title='QA预警', content='QA低库存', link_url='/warehouse/inventory',
                         is_read=False, created_at=now()),
        ])
        db.session.commit()

        login(client, 'leader1', '123456')
        data = client.get('/chat/api/unread').get_json()['data']

        assert data['chat_unread'] == 2
        assert data['warning_unread'] == unread_warning_count(leader.id) == 1
        assert data['total'] == 3
        assert data['count'] == 2
