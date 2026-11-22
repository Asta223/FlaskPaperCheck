# -*- coding: utf-8 -*-
"""客户/供应商档案测试：CRUD、唯一性、权限、软删恢复、工单/入库单关联。"""
from datetime import date, timedelta

from conftest import get_csrf, login

from app import db
from app.models import (Customer, Inventory, Material, Product, Supplier, Warehouse,
                        WorkOrder, StockDocument)


def _partner_form(code, name, contact='联系人'):
    return {'code': code, 'name': name, 'contact': contact,
            'phone': '13800000000', 'address': '测试地址', 'tax_no': '', 'remark': ''}


def _new_product(code, name):
    p = Product(code=code, name=name, unit='个')
    db.session.add(p)
    db.session.commit()
    return p


# ---------------- 客户档案 ----------------

def test_customer_crud_unique_and_soft_delete(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/production/customers')
    data = _partner_form('CUS-T01', '测试客户甲')
    data['csrf_token'] = token
    resp = client.post('/production/customers/new', data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert '已创建'.encode() in resp.data
    c = Customer.query.filter_by(code='CUS-T01').first()
    assert c is not None and c.contact == '联系人'

    # 编码或名称重复被拒
    token = get_csrf(client, '/production/customers')
    dup = _partner_form('CUS-T01', '另一个名字')
    dup['csrf_token'] = token
    resp = client.post('/production/customers/new', data=dup, follow_redirects=True)
    assert '客户编号或名称已存在'.encode() in resp.data

    # 编辑
    token = get_csrf(client, '/production/customers?edit_id=%d' % c.id)
    edit = _partner_form('CUS-T01', '测试客户甲改名', '新联系人')
    edit['csrf_token'] = token
    resp = client.post('/production/customers/%d/edit' % c.id, data=edit, follow_redirects=True)
    assert '已保存'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(Customer, c.id).contact == '新联系人'

    # 软删 + 回收站恢复
    token = get_csrf(client, '/production/customers')
    resp = client.post('/production/customers/%d/delete' % c.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '已删除'.encode() in resp.data
    assert Customer.query.filter_by(code='CUS-T01').first() is None
    html = client.get('/system/recycle?type=customer').get_data(as_text=True)
    assert '测试客户甲改名' in html
    token = get_csrf(client, '/system/recycle?type=customer')
    resp = client.post('/system/recycle/customer/%d/restore' % c.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '已恢复'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(Customer, c.id).is_deleted is False


def test_customer_permission(client):
    # 登录前从登录页取 token（会话内通用），登录后 staff 无权限
    token = get_csrf(client, '/auth/login')
    login(client, 'staff1', '123456')
    assert client.get('/production/customers').status_code == 403
    assert client.post('/production/customers/new',
                       data={'csrf_token': token}).status_code == 403


# ---------------- 供应商档案 ----------------

def test_supplier_crud_and_permission(client):
    login(client, 'admin', 'admin123')
    token = get_csrf(client, '/warehouse/suppliers')
    data = _partner_form('SUP-T01', '测试供应商甲')
    data['csrf_token'] = token
    resp = client.post('/warehouse/suppliers/new', data=data, follow_redirects=True)
    assert resp.status_code == 200 and '已创建'.encode() in resp.data
    s = Supplier.query.filter_by(code='SUP-T01').first()
    assert s is not None

    # 软删后列表不可见、回收站可见
    token = get_csrf(client, '/warehouse/suppliers')
    client.post('/warehouse/suppliers/%d/delete' % s.id,
                data={'csrf_token': token}, follow_redirects=True)
    assert Supplier.query.filter_by(code='SUP-T01').first() is None
    assert '测试供应商甲' in client.get('/system/recycle?type=supplier').get_data(as_text=True)

    client.get('/auth/logout')
    login(client, 'staff1', '123456')
    assert client.get('/warehouse/suppliers').status_code == 403


# ---------------- 工单关联客户 ----------------

def test_order_links_customer_snapshot(client):
    login(client, 'admin', 'admin123')
    product = _new_product('PRD-PT-01', '关联客户产品')
    c = Customer(code='CUS-PT-01', name='快照客户')
    db.session.add(c)
    db.session.commit()

    due = (date.today() + timedelta(days=3)).isoformat()
    token = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new', data={
        'csrf_token': token, 'product_id': str(product.id), 'product_name': '',
        'customer_id': str(c.id), 'customer_name': '手输应被覆盖',
        'quantity': '3', 'due_date': due, 'priority': 'normal',
        'leader_id': '0', 'related_department_id': '0', 'route_id': '0',
        'plan_start_date': '', 'plan_end_date': '', 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    order = WorkOrder.query.filter_by(product_id=product.id).first()
    assert order is not None
    assert order.customer_id == c.id
    assert order.customer_name == '快照客户'  # 关联客户时名称自动带出，手输被覆盖

    # 详情页显示客户与编码
    html = client.get('/production/orders/%d' % order.id).get_data(as_text=True)
    assert '快照客户' in html and 'CUS-PT-01' in html

    # 客户改名后历史工单快照不变
    c.name = '改名后的客户'
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(WorkOrder, order.id).customer_name == '快照客户'


# ---------------- 入库单关联供应商 ----------------

def test_inbound_doc_links_supplier(client):
    from app.utils.time_utils import now
    login(client, 'admin', 'admin123')
    s = Supplier(code='SUP-PT-01', name='送货供应商')
    m = Material(code='PT-M01', name='来料', unit='个')
    w = Warehouse(name='PT测试仓', location='')
    db.session.add_all([s, m, w])
    db.session.commit()

    token = get_csrf(client, '/warehouse/docs/new')
    doc_no = 'IN%s0001' % now().strftime('%Y%m%d')
    resp = client.post('/warehouse/docs/new', data={
        'csrf_token': token, 'doc_type': 'in', 'warehouse_id': str(w.id),
        'material_id': str(m.id), 'quantity': '5', 'related_order_id': '0',
        'supplier_id': str(s.id), 'remark': '供应商送货',
    }, follow_redirects=True)
    assert resp.status_code == 200
    doc = StockDocument.query.filter_by(material_id=m.id).first()
    assert doc is not None and doc.supplier_id == s.id
    html = client.get('/warehouse/docs').get_data(as_text=True)
    assert '送货供应商' in html

    # 出库单即使传了 supplier_id 也不记录
    inv = Inventory.query.filter_by(warehouse_id=w.id, material_id=m.id).first()
    assert inv is not None and inv.quantity == 5
    token = get_csrf(client, '/warehouse/docs/new')
    client.post('/warehouse/docs/new', data={
        'csrf_token': token, 'doc_type': 'out', 'warehouse_id': str(w.id),
        'material_id': str(m.id), 'quantity': '2', 'related_order_id': '0',
        'supplier_id': str(s.id), 'remark': '',
    }, follow_redirects=True)
    out_doc = StockDocument.query.filter_by(doc_type='out', material_id=m.id).first()
    assert out_doc is not None and out_doc.supplier_id is None


def test_partner_menu_and_permissions_registered(client):
    login(client, 'admin', 'admin123')
    html = client.get('/production/customers').get_data(as_text=True)
    assert '客户档案' in html
    html = client.get('/warehouse/suppliers').get_data(as_text=True)
    assert '供应商档案' in html
    from app.utils.permissions import ALL_PERMISSION_CODES
    assert 'production.customer.manage' in ALL_PERMISSION_CODES
    assert 'warehouse.supplier.manage' in ALL_PERMISSION_CODES
