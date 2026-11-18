# -*- coding: utf-8 -*-
"""P1 仓库—生产联动测试：库存流水、领料三步原子、单据关联工单、工单日志、预警去重。"""
from conftest import get_csrf, login

from app import db
from app.models import (Inventory, Material, Notification, OperationLog, StockDocument,
                        StockLedger, StockWarningState, User, Warehouse, WorkOrder)
from app.services.inventory_service import InsufficientStockError, apply_stock_document


def _wh_mat():
    return (Warehouse.query.filter_by(name='原材料仓').first(),
            Material.query.filter_by(code='M0001').first())


def _admin():
    return User.query.filter_by(username='admin').first()


def _producer():
    return User.query.filter_by(username='producer1').first()


def _find_order():
    return WorkOrder.query.first()


# ---------------- P1-07 库存流水 ----------------

def test_ledger_created_with_document(app_ctx):
    """出入库单据提交时同事务生成流水，含变动前后余额。"""
    wh, mat = _wh_mat()
    d1 = apply_stock_document('in', wh.id, mat.id, 50, 1, 1)
    led1 = StockLedger.query.filter_by(doc_no=d1.doc_no).first()
    assert led1 is not None and led1.doc_type == 'in'
    assert led1.before_balance == 0 and led1.after_balance == 50
    d2 = apply_stock_document('out', wh.id, mat.id, 20, 1, 1)
    led2 = StockLedger.query.filter_by(doc_no=d2.doc_no).first()
    assert led2.before_balance == 50 and led2.after_balance == 30


def test_ledger_rolled_back_on_insufficient(app_ctx):
    """出库失败：库存/单据/流水三者同时回滚。"""
    wh, mat = _wh_mat()
    apply_stock_document('in', wh.id, mat.id, 10, 1, 1)
    before_ledgers = StockLedger.query.count()
    before_docs = StockDocument.query.count()
    try:
        apply_stock_document('out', wh.id, mat.id, 999, 1, 1)
    except InsufficientStockError:
        pass
    assert StockLedger.query.count() == before_ledgers
    assert StockDocument.query.count() == before_docs


def test_ledger_page_200(client):
    login(client, 'keeper1', '123456')
    resp = client.get('/warehouse/ledger')
    assert resp.status_code == 200


# ---------------- P1-05 领料 + P1-06 工单日志 ----------------

def test_issue_creates_out_doc_ledger_and_log(client):
    """领料：出库单(related_order_id)+流水+工单日志三步原子。"""
    wh, mat = _wh_mat()
    apply_stock_document('in', wh.id, mat.id, 100, 1, 1)
    order = _find_order()
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % order.id)
    resp = client.post('/production/orders/%d/issue' % order.id, data={
        'csrf_token': token, 'warehouse_id': wh.id, 'material_id': mat.id,
        'quantity': 15, 'remark': '领料测试',
    }, follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire_all()
    doc = StockDocument.query.filter_by(related_order_id=order.id, doc_type='out').first()
    assert doc is not None and doc.quantity == 15
    led = StockLedger.query.filter_by(doc_no=doc.doc_no).first()
    assert led is not None and led.related_order_id == order.id and led.after_balance == 85
    oplog = OperationLog.query.filter_by(target_type='work_order', target_id=order.id,
                                         action='issue').first()
    assert oplog is not None


def test_issue_insufficient_no_side_effects(client):
    """库存不足领料：单据/流水/日志都不产生。"""
    wh, mat = _wh_mat()
    order = _find_order()
    apply_stock_document('in', wh.id, mat.id, 2, 1, 1)
    before_docs = StockDocument.query.count()
    before_logs = OperationLog.query.filter_by(target_type='work_order',
                                               target_id=order.id).count()
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % order.id)
    resp = client.post('/production/orders/%d/issue' % order.id, data={
        'csrf_token': token, 'warehouse_id': wh.id, 'material_id': mat.id,
        'quantity': 999, 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert '库存不足'.encode() in resp.data
    db.session.expire_all()
    assert StockDocument.query.count() == before_docs
    assert OperationLog.query.filter_by(target_type='work_order', target_id=order.id).count() == before_logs


def test_issue_forbidden_on_completed_order(client):
    """已完成工单禁止领料。"""
    order = _find_order()
    order.status = 'completed'
    db.session.commit()
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % order.id)
    resp = client.post('/production/orders/%d/issue' % order.id, data={
        'csrf_token': token, 'warehouse_id': 1, 'material_id': 1, 'quantity': 1,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert StockDocument.query.filter_by(related_order_id=order.id).count() == 0


# ---------------- P1-08 单据关联工单 ----------------

def test_related_order_stored(client):
    """出库单选择关联工单 → related_order_id 保存；NULL 兼容。"""
    wh, mat = _wh_mat()
    order = _find_order()
    apply_stock_document('in', wh.id, mat.id, 20, 1, 1)  # 先补库存
    login(client, 'keeper1', '123456')
    token = get_csrf(client, '/warehouse/docs/new')
    client.post('/warehouse/docs/new', data={
        'csrf_token': token, 'doc_type': 'out', 'warehouse_id': wh.id,
        'material_id': mat.id, 'quantity': 1, 'related_order_id': order.id, 'remark': '',
    }, follow_redirects=True)
    db.session.expire_all()
    doc = StockDocument.query.filter_by(related_order_id=order.id, doc_type='out').first()
    assert doc is not None, '出库单应保存 related_order_id'


# ---------------- P1-09 预警去重 + 失败隔离 ----------------

def test_warning_dedup_and_reset(app_ctx):
    """低位只推一次；回升复位；再跌破可再推。"""
    from app.services.notification_service import push_stock_warning
    wh, mat = _wh_mat()
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    inv.quantity = 5
    inv.warn_threshold = 10
    db.session.commit()
    assert push_stock_warning(wh.id, mat.id) > 0  # 首次跌破推送
    assert push_stock_warning(wh.id, mat.id) == 0  # 仍低位不重复
    keepers = Notification.query.filter_by(notif_type='stock_warning').count()
    assert keepers >= 1
    first_count = Notification.query.filter_by(notif_type='stock_warning').count()
    # 回升
    inv.quantity = 100
    db.session.commit()
    push_stock_warning(wh.id, mat.id)
    state = StockWarningState.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    assert state.is_low is False
    # 再跌破
    inv.quantity = 5
    db.session.commit()
    assert push_stock_warning(wh.id, mat.id) > 0
    assert Notification.query.filter_by(notif_type='stock_warning').count() > first_count


def test_warning_does_not_block_document(client):
    """预警推送失败不影响单据主流程（单据已成功则流程成功）。"""
    wh, mat = _wh_mat()
    login(client, 'keeper1', '123456')
    token = get_csrf(client, '/warehouse/docs/new')
    resp = client.post('/warehouse/docs/new', data={
        'csrf_token': token, 'doc_type': 'in', 'warehouse_id': wh.id,
        'material_id': mat.id, 'quantity': 7, 'related_order_id': 0, 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert StockDocument.query.count() >= 1


# ---------------- QA Bug4 回归：流水关联工单可查 ----------------

def test_issue_is_atomic_and_bidirectionally_queryable(client):
    """QA-Bug4：领料流水 related_order 关系可读，页面显示工单号链接。"""
    wh, mat = _wh_mat()
    apply_stock_document('in', wh.id, mat.id, 100, 1, 1)
    order = _find_order()
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % order.id)
    client.post('/production/orders/%d/issue' % order.id, data={
        'csrf_token': token, 'warehouse_id': wh.id, 'material_id': mat.id,
        'quantity': 5, 'remark': '',
    }, follow_redirects=True)
    db.session.expire_all()
    led = StockLedger.query.filter_by(related_order_id=order.id).first()
    assert led is not None and led.related_order is not None
    assert led.related_order.order_no == order.order_no
    assert led in order.stock_ledgers  # 双向关系：order.stock_ledgers 含该流水
    # 流水页渲染工单号
    login(client, 'admin', 'admin123')
    resp = client.get('/warehouse/ledger')
    assert resp.status_code == 200
    assert order.order_no.encode() in resp.data
