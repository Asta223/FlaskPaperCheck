# -*- coding: utf-8 -*-
"""P2-2 增量测试：仓库档案完整 CRUD、物料档案库位字段。

覆盖需求：
1. 仓库档案增删查改可逆（停用/启用、严格条件下彻底删除、搜索）；
2. 物料档案记录存放位置（仓位/货位），列表/筛选/下拉/库存导出可见。
"""
from conftest import get_csrf, login

from app import db
from app.models import (Inventory, Material, Process, StockDocument, User, Warehouse,
                        WorkOrder)


def _new_warehouse(name='测试新仓', location='3号厂房'):
    w = Warehouse(name=name, location=location)
    db.session.add(w)
    db.session.commit()
    return w


# ---------------- 仓库档案 CRUD ----------------

def test_warehouse_create_edit_toggle_delete(client):
    login(client, 'keeper1', '123456')
    token = get_csrf(client, '/warehouse/warehouses')
    resp = client.post('/warehouse/warehouses/new', data={
        'csrf_token': token, 'name': 'CRUD测试仓', 'location': '4号库房',
    }, follow_redirects=True)
    assert resp.status_code == 200
    w = Warehouse.query.filter_by(name='CRUD测试仓').first()
    assert w is not None and w.location == '4号库房'

    # 编辑
    token = get_csrf(client, '/warehouse/warehouses')
    client.post('/warehouse/warehouses/%d/edit' % w.id, data={
        'csrf_token': token, 'name': 'CRUD测试仓2', 'location': '5号库房',
    }, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(Warehouse, w.id).name == 'CRUD测试仓2'

    # 停用（可逆）
    token = get_csrf(client, '/warehouse/warehouses')
    client.post('/warehouse/warehouses/%d/toggle' % w.id,
                data={'csrf_token': token}, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(Warehouse, w.id).is_active is False
    # 恢复
    token = get_csrf(client, '/warehouse/warehouses')
    client.post('/warehouse/warehouses/%d/toggle' % w.id,
                data={'csrf_token': token}, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(Warehouse, w.id).is_active is True

    # 无关联 → 彻底删除
    token = get_csrf(client, '/warehouse/warehouses')
    client.post('/warehouse/warehouses/%d/delete' % w.id,
                data={'csrf_token': token}, follow_redirects=True)
    assert db.session.get(Warehouse, w.id) is None


def test_warehouse_toggle_reject_when_has_stock(client):
    w = _new_warehouse('有库存仓')
    m = Material.query.first()
    db.session.add(Inventory(warehouse_id=w.id, material_id=m.id, quantity=10))
    db.session.commit()
    login(client, 'keeper1', '123456')
    token = get_csrf(client, '/warehouse/warehouses')
    client.post('/warehouse/warehouses/%d/toggle' % w.id,
                data={'csrf_token': token}, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(Warehouse, w.id).is_active is True  # 有库存不可停用


def test_warehouse_delete_reject_when_has_document(client):
    w = _new_warehouse('有单据仓')
    admin = User.query.filter_by(username='admin').first()
    m = Material.query.first()
    db.session.add(StockDocument(doc_no='OUTTEST01', doc_type='out', warehouse_id=w.id,
                                 material_id=m.id, quantity=1, handler_id=admin.id,
                                 created_by=admin.id))
    db.session.commit()
    login(client, 'keeper1', '123456')
    token = get_csrf(client, '/warehouse/warehouses')
    client.post('/warehouse/warehouses/%d/delete' % w.id,
                data={'csrf_token': token}, follow_redirects=True)
    assert db.session.get(Warehouse, w.id) is not None  # 有单据历史不可彻底删


def test_warehouse_search(client):
    _new_warehouse('搜索关键词仓XYZ', '特殊位置ABC')
    login(client, 'keeper1', '123456')
    resp = client.get('/warehouse/warehouses?keyword=' + '关键词仓XYZ'.encode().decode())
    assert resp.status_code == 200
    assert '搜索关键词仓XYZ'.encode() in resp.data


# ---------------- 物料库位 ----------------

def test_material_create_with_storage_location(client):
    login(client, 'keeper1', '123456')
    token = get_csrf(client, '/material/new')
    resp = client.post('/material/new', data={
        'csrf_token': token, 'code': 'MLOC1', 'name': '库位测试物料',
        'spec': 'S', 'unit': '个', 'category_id': 0,
        'storage_location': '原材料仓 A区-05排-1层',
    }, follow_redirects=True)
    assert resp.status_code == 200
    m = Material.query.filter_by(code='MLOC1').first()
    assert m is not None and m.storage_location == '原材料仓 A区-05排-1层'


def test_material_edit_storage_location(client):
    m = Material.query.filter_by(code='M0001').first()
    login(client, 'keeper1', '123456')
    token = get_csrf(client, '/material/%d/edit' % m.id)
    client.post('/material/%d/edit' % m.id, data={
        'csrf_token': token, 'code': m.code, 'name': m.name, 'spec': m.spec,
        'unit': m.unit, 'category_id': 0, 'storage_location': '新库位 B-02',
    }, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(Material, m.id).storage_location == '新库位 B-02'


def test_material_list_shows_and_filters_storage_location(client):
    m = Material.query.filter_by(code='M0002').first()
    m.storage_location = '过滤定位仓 ZZ-99'
    db.session.commit()
    login(client, 'keeper1', '123456')
    html = client.get('/material/list').get_data(as_text=True)
    assert '过滤定位仓 ZZ-99' in html
    # 按库位关键词筛选
    resp = client.get('/material/list?keyword=' + 'ZZ-99')
    assert resp.status_code == 200
    assert '轴承'.encode() in resp.data


def test_material_dropdown_shows_storage_location(client):
    """出入库单据的物料下拉应带出库位提示，便于人员定位。"""
    m = Material.query.filter_by(code='M0003').first()
    m.storage_location = '带出提示仓 Q-07'
    db.session.commit()
    login(client, 'keeper1', '123456')
    html = client.get('/warehouse/docs/new').get_data(as_text=True)
    assert '带出提示仓 Q-07' in html or '库位：带出提示仓 Q-07' in html


def test_issue_material_dropdown_shows_storage_location(client):
    """工单领料弹窗的物料下拉也应带出库位。"""
    m = Material.query.filter_by(code='M0003').first()
    m.storage_location = '领料提示仓 P-08'
    db.session.commit()
    admin = User.query.filter_by(username='admin').first()
    o = WorkOrder(order_no='WOP2LOC001', product_name='库位工单', quantity=1, created_by=admin.id)
    db.session.add(o)
    db.session.commit()
    login(client, 'producer1', '123456')
    html = client.get('/production/orders/%d' % o.id).get_data(as_text=True)
    assert '领料提示仓 P-08' in html


def test_inventory_export_contains_storage_location(client):
    m = Material.query.first()
    m.storage_location = '导出库位 X-11'
    db.session.commit()
    login(client, 'admin', 'admin123')
    resp = client.get('/warehouse/inventory/export.csv')
    text = resp.data.decode('utf-8-sig')
    assert '存放位置' in text
    assert '导出库位 X-11' in text
