# -*- coding: utf-8 -*-
"""单位换算在出入库单与工单领料中的落地：折算入账、快照、守卫。"""
import pytest
from conftest import get_csrf, login

from app import db
from app.models import (Inventory, Material, StockDocument, Unit, UnitConversion,
                        Warehouse, WorkOrder)
from app.services.inventory_service import apply_stock_document
from app.services.unit_service import UnitConversionError


def _wh_mat_box():
    wh = Warehouse.query.filter_by(name='原材料仓').first()
    mat = Material.query.filter_by(code='M0001').first()
    box = Unit.query.filter_by(code='BOX').first()
    return wh, mat, box


def _inventory(wh, mat):
    row = Inventory.query.filter_by(warehouse_id=wh.id, material_id=mat.id).first()
    return row.quantity if row else 0


def test_service_converts_boxes_to_base_units(app_ctx):
    wh, mat, box = _wh_mat_box()

    doc_in = apply_stock_document('in', wh.id, mat.id, 1, handler_id=1, created_by=1,
                                  unit_id=box.id, input_quantity=2)
    assert _inventory(wh, mat) == 200
    assert doc_in.quantity == 200
    assert doc_in.input_quantity == 2
    assert doc_in.unit_name == '盒'
    assert doc_in.factor == 100

    doc_out = apply_stock_document('out', wh.id, mat.id, 1, handler_id=1, created_by=1,
                                   unit_id=box.id, input_quantity=1)
    assert _inventory(wh, mat) == 100
    assert doc_out.quantity == 100 and doc_out.input_quantity == 1

    # 按基本单位取 10 个：从“1盒”库存里拆出 10 个
    apply_stock_document('out', wh.id, mat.id, 10, handler_id=1, created_by=1)
    assert _inventory(wh, mat) == 90


def test_service_rejects_missing_or_invalid_conversion(app_ctx):
    wh, mat, box = _wh_mat_box()
    kg = Unit.query.filter_by(code='KG').first()
    other = Material.query.filter_by(code='M0002').first()

    # 未维护换算关系的物料
    with pytest.raises(UnitConversionError):
        apply_stock_document('in', wh.id, other.id, 1, handler_id=1, created_by=1,
                             unit_id=box.id, input_quantity=1)

    # 跨量纲：人为插一条 kg 换算，服务层按量纲拒绝
    db.session.add(UnitConversion(material_id=mat.id, unit_id=kg.id, factor=1))
    db.session.commit()
    with pytest.raises(UnitConversionError) as exc:
        apply_stock_document('in', wh.id, mat.id, 1, handler_id=1, created_by=1,
                             unit_id=kg.id, input_quantity=1)
    assert '量纲' in str(exc.value)

    # 折算非整数：0.5 基本单位/盒，取 1 盒
    half = UnitConversion(material_id=other.id, unit_id=box.id, factor=0.5)
    db.session.add(half)
    db.session.commit()
    with pytest.raises(UnitConversionError) as exc:
        apply_stock_document('in', wh.id, other.id, 1, handler_id=1, created_by=1,
                             unit_id=box.id, input_quantity=1)
    assert '不是整数' in str(exc.value)


def test_doc_form_applies_conversion_and_shows_snapshot(client):
    login(client, 'admin', 'admin123')
    wh, mat, box = _wh_mat_box()
    token = get_csrf(client, '/warehouse/docs/new')
    resp = client.post('/warehouse/docs/new', data={
        'csrf_token': token, 'doc_type': 'in', 'warehouse_id': wh.id,
        'material_id': mat.id, 'quantity': 1, 'unit_id': box.id,
        'related_order_id': 0, 'supplier_id': 0, 'remark': '按盒入库',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert _inventory(wh, mat) == 100
    doc = StockDocument.query.order_by(StockDocument.id.desc()).first()
    assert doc.quantity == 100 and doc.input_quantity == 1 and doc.unit_name == '盒'
    html = client.get('/warehouse/docs').get_data(as_text=True)
    assert '1 盒' in html and '折合 100' in html


def test_order_issue_supports_unit_conversion(client):
    login(client, 'admin', 'admin123')
    wh, mat, box = _wh_mat_box()
    apply_stock_document('in', wh.id, mat.id, 1, handler_id=1, created_by=1,
                         unit_id=box.id, input_quantity=1)  # 100 个

    order = WorkOrder(order_no='WO-UNIT-001', product_name='换算测试', quantity=10,
                      created_by=1, status='in_progress')
    db.session.add(order)
    db.session.commit()

    url = '/production/orders/%d?tab=info' % order.id
    token = get_csrf(client, url)
    # 以“个”领 10 个，等价于从一盒里拆出 10 个
    resp = client.post('/production/orders/%d/issue?tab=info' % order.id, data={
        'csrf_token': token, 'warehouse_id': wh.id, 'material_id': mat.id,
        'quantity': 10, 'unit_id': 0, 'remark': '拆箱领用',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert _inventory(wh, mat) == 90
    doc = StockDocument.query.filter_by(related_order_id=order.id).first()
    assert doc is not None and doc.quantity == 10

    # 再按“盒”领 1 盒，折算扣 100；当前仅 90，应被拒绝且不产生新单据
    before = StockDocument.query.count()
    token = get_csrf(client, url)
    client.post('/production/orders/%d/issue?tab=info' % order.id, data={
        'csrf_token': token, 'warehouse_id': wh.id, 'material_id': mat.id,
        'quantity': 1, 'unit_id': box.id, 'remark': '超量',
    }, follow_redirects=True)
    assert _inventory(wh, mat) == 90
    assert StockDocument.query.count() == before
