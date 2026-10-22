# -*- coding: utf-8 -*-
"""库存事务一致性测试（inventory_service + warehouse 路由）：
入库/出库增减、超量出库完全回滚、参数校验、单号唯一、UK 约束、重复提交防护。
"""
import pytest
from sqlalchemy.exc import IntegrityError

from conftest import get_csrf, login

from app import db
from app.models import Inventory, Material, StockDocument, Warehouse
from app.services.inventory_service import (InsufficientStockError,
                                            InventoryServiceError,
                                            apply_stock_document)


def _wh_mat():
    """种子数据中的仓库与物料。"""
    wh = Warehouse.query.filter_by(name='原材料仓').first()
    mat = Material.query.filter_by(code='M0001').first()
    return wh, mat


# ---------------- 服务层：入库/出库 ----------------

def test_in_creates_and_accumulates(app_ctx):
    wh, mat = _wh_mat()
    d1 = apply_stock_document('in', wh.id, mat.id, 50, handler_id=1, created_by=1)
    d2 = apply_stock_document('in', wh.id, mat.id, 30, handler_id=1, created_by=1)
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    assert inv is not None and inv.quantity == 80
    assert StockDocument.query.count() == 2
    assert d1.doc_no != d2.doc_no
    assert d1.doc_no.startswith('IN')


def test_out_reduces_quantity(app_ctx):
    wh, mat = _wh_mat()
    apply_stock_document('in', wh.id, mat.id, 100, handler_id=1, created_by=1)
    doc = apply_stock_document('out', wh.id, mat.id, 40, handler_id=1, created_by=1)
    assert doc.doc_no.startswith('OUT')
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    assert inv.quantity == 60


def test_out_insufficient_full_rollback(app_ctx):
    """出库超量：抛 InsufficientStockError，库存不变，单据完全不落库。"""
    wh, mat = _wh_mat()
    apply_stock_document('in', wh.id, mat.id, 50, handler_id=1, created_by=1)
    before_docs = StockDocument.query.count()
    with pytest.raises(InsufficientStockError) as excinfo:
        apply_stock_document('out', wh.id, mat.id, 51, handler_id=1, created_by=1)
    assert excinfo.value.available == 50
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    assert inv.quantity == 50                       # 库存不变
    assert StockDocument.query.count() == before_docs  # 单据未落库


def test_out_without_inventory_record_rejected(app_ctx):
    """无库存记录的物料出库：拒绝且不产生任何单据/库存行。"""
    wh, _ = _wh_mat()
    mat2 = Material(code='MXTEST', name='测试物料', unit='个')
    db.session.add(mat2)
    db.session.commit()
    with pytest.raises(InsufficientStockError) as excinfo:
        apply_stock_document('out', wh.id, mat2.id, 1, handler_id=1, created_by=1)
    assert excinfo.value.available == 0
    assert StockDocument.query.count() == 0
    assert Inventory.query.filter_by(material_id=mat2.id).first() is None


# ---------------- 服务层：参数校验 ----------------

def test_invalid_doc_type(app_ctx):
    wh, mat = _wh_mat()
    with pytest.raises(InventoryServiceError):
        apply_stock_document('transfer', wh.id, mat.id, 1, handler_id=1, created_by=1)


def test_invalid_quantity(app_ctx):
    wh, mat = _wh_mat()
    for bad_qty in (0, -5, 'abc', None):
        with pytest.raises(InventoryServiceError):
            apply_stock_document('in', wh.id, mat.id, bad_qty, handler_id=1, created_by=1)
    assert StockDocument.query.count() == 0


def test_invalid_warehouse_or_material(app_ctx):
    wh, mat = _wh_mat()
    with pytest.raises(InventoryServiceError):
        apply_stock_document('in', 99999, mat.id, 1, handler_id=1, created_by=1)
    with pytest.raises(InventoryServiceError):
        apply_stock_document('in', wh.id, 99999, 1, handler_id=1, created_by=1)
    # 停用的仓库/物料同样拒绝
    wh2 = Warehouse(name='停用仓', is_active=False)
    mat2 = Material(code='MSTOP', name='停用物料', unit='个', is_active=False)
    db.session.add_all([wh2, mat2])
    db.session.commit()
    with pytest.raises(InventoryServiceError):
        apply_stock_document('in', wh2.id, mat.id, 1, handler_id=1, created_by=1)
    with pytest.raises(InventoryServiceError):
        apply_stock_document('in', wh.id, mat2.id, 1, handler_id=1, created_by=1)


# ---------------- 单据号与约束 ----------------

def test_doc_no_sequential_and_unique(app_ctx):
    """连续提交单据：单号自增且唯一（重复提交防护的基础）。"""
    wh, mat = _wh_mat()
    docs = [apply_stock_document('in', wh.id, mat.id, 1, handler_id=1, created_by=1)
            for _ in range(5)]
    nos = [d.doc_no for d in docs]
    assert len(set(nos)) == 5, '单据号必须唯一：%s' % nos


def test_uk_constraint_same_warehouse_material(app_ctx):
    """UK 约束：同仓库同物料仅一条库存记录。"""
    wh, mat = _wh_mat()
    apply_stock_document('in', wh.id, mat.id, 10, handler_id=1, created_by=1)
    assert Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).count() == 1
    dup = Inventory(warehouse_id=wh.id, material_id=mat.id, quantity=5)
    db.session.add(dup)
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()


def test_related_order_id_zero_becomes_none(client):
    """路由层提交关联工单=0（-- 无 --）时单据应存 NULL 而非悬空外键 0。"""
    login(client, 'keeper1', '123456')
    wh, mat = _wh_mat()
    token = get_csrf(client, '/warehouse/docs/new')
    resp = client.post('/warehouse/docs/new', data={
        'csrf_token': token, 'doc_type': 'in', 'warehouse_id': wh.id,
        'material_id': mat.id, 'quantity': 3, 'related_order_id': 0, 'remark': ''},
        follow_redirects=True)
    assert resp.status_code == 200
    doc = StockDocument.query.order_by(StockDocument.id.desc()).first()
    assert doc is not None
    assert doc.related_order_id is None, 'related_order_id=0 应规范化为 NULL'


# ---------------- 路由层（仓管员身份） ----------------

def test_route_in_out_flow(client):
    login(client, 'keeper1', '123456')
    wh, mat = _wh_mat()
    # 入库 100
    token = get_csrf(client, '/warehouse/docs/new')
    resp = client.post('/warehouse/docs/new', data={
        'csrf_token': token, 'doc_type': 'in', 'warehouse_id': wh.id,
        'material_id': mat.id, 'quantity': 100, 'related_order_id': 0, 'remark': ''},
        follow_redirects=True)
    assert resp.status_code == 200
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    assert inv.quantity == 100
    # 超量出库被拒：库存不变、无新单据
    token = get_csrf(client, '/warehouse/docs/new')
    resp = client.post('/warehouse/docs/new', data={
        'csrf_token': token, 'doc_type': 'out', 'warehouse_id': wh.id,
        'material_id': mat.id, 'quantity': 999, 'remark': ''},
        follow_redirects=True)
    assert '库存不足'.encode() in resp.data
    db.session.expire_all()
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    assert inv.quantity == 100
    assert StockDocument.query.count() == 1
    # 正常出库 30
    token = get_csrf(client, '/warehouse/docs/new')
    resp = client.post('/warehouse/docs/new', data={
        'csrf_token': token, 'doc_type': 'out', 'warehouse_id': wh.id,
        'material_id': mat.id, 'quantity': 30, 'remark': ''},
        follow_redirects=True)
    db.session.expire_all()
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    assert inv.quantity == 70
    assert StockDocument.query.count() == 2


def test_route_inventory_warning_flag(client):
    """库存低于阈值时页面应出现预警标注。"""
    login(client, 'keeper1', '123456')
    wh, mat = _wh_mat()
    apply_stock_document('in', wh.id, mat.id, 5, handler_id=1, created_by=1)
    inv = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    inv.warn_threshold = 10
    db.session.commit()
    resp = client.get('/warehouse/inventory')
    assert resp.status_code == 200
    assert '低于阈值'.encode() in resp.data
