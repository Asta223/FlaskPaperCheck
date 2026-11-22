# -*- coding: utf-8 -*-
"""产品档案与 BOM 测试：主数据 CRUD、单位快照、软删恢复、工单/路线关联与用料展示。"""
from datetime import date, timedelta

from conftest import get_csrf, login

from app import db
from app.models import BomItem, Material, Process, Product, ProcessRoute, WorkOrder
from app.utils.delete_guard import find_references


def _material(code, name, unit='个'):
    m = Material(code=code, name=name, spec='测试规格', unit=unit)
    db.session.add(m)
    db.session.commit()
    return m


def _product_form_data(code, name, picked, spec='12cm', unit='个'):
    data = {'csrf_token': '', 'code': code, 'name': name, 'spec': spec,
            'unit': unit, 'remark': ''}
    for qty, material in picked:
        data.setdefault('material_ids', []).append(str(material.id))
        data['qty_%d' % material.id] = str(qty)
    return data


def test_product_crud_bom_and_unit_snapshot(client):
    login(client, 'admin', 'admin123')
    m = _material('PB-M01', '测试螺丝', '盒')

    token = get_csrf(client, '/production/products')
    data = _product_form_data('PRD90', '测试产品', [(0.5, m)])
    data['csrf_token'] = token
    resp = client.post('/production/products/new', data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert '已创建，含 1 条 BOM 用料'.encode() in resp.data

    p = Product.query.filter_by(code='PRD90').first()
    assert p is not None and p.spec == '12cm'
    assert len(p.bom_items) == 1
    assert p.bom_items[0].quantity == 0.5
    assert p.bom_items[0].unit == '盒'  # 单位取自物料档案快照

    # 重复编码/名称被拒
    token = get_csrf(client, '/production/products')
    dup = _product_form_data('PRD90', '另一个名字', [(1, m)])
    dup['csrf_token'] = token
    resp = client.post('/production/products/new', data=dup, follow_redirects=True)
    assert '编号或名称已存在'.encode() in resp.data

    # 物料改单位后，BOM 快照保持不变
    m.unit = '箱'
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(Product, p.id).bom_items[0].unit == '盒'

    # 编辑：物理替换明细，不留旧行
    m2 = _material('PB-M02', '测试轴承')
    token = get_csrf(client, '/production/products?edit_id=%d' % p.id)
    edit = _product_form_data('PRD90', '测试产品', [(2, m2)])
    edit['csrf_token'] = token
    resp = client.post('/production/products/%d/edit' % p.id,
                       data=edit, follow_redirects=True)
    assert '已保存'.encode() in resp.data
    db.session.expire_all()
    items = BomItem.query.filter_by(product_id=p.id).all()
    assert len(items) == 1 and items[0].material_id == m2.id
    assert items[0].quantity == 2 and items[0].unit == '个'

    # 单件用量必须为正
    token = get_csrf(client, '/production/products?edit_id=%d' % p.id)
    bad = _product_form_data('PRD90', '测试产品', [(0, m2)])
    bad['csrf_token'] = token
    resp = client.post('/production/products/%d/edit' % p.id,
                       data=bad, follow_redirects=True)
    assert '单件用量必须大于 0'.encode() in resp.data


def test_product_soft_delete_hides_bom_and_restore(client):
    login(client, 'admin', 'admin123')
    m = _material('PB-M03', '删除测试料')
    token = get_csrf(client, '/production/products')
    data = _product_form_data('PRD91', '待删产品', [(1, m)])
    data['csrf_token'] = token
    client.post('/production/products/new', data=data, follow_redirects=True)
    p = Product.query.filter_by(code='PRD91').first()
    assert 'bom_items' in find_references(m)

    token = get_csrf(client, '/production/products')
    resp = client.post('/production/products/%d/delete' % p.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '已删除'.encode() in resp.data
    assert Product.query.filter_by(code='PRD91').first() is None
    items = (BomItem.query.execution_options(include_deleted=True)
             .filter_by(product_id=p.id).all())
    assert len(items) == 1 and items[0].is_deleted is True
    assert find_references(m) == {}  # 软删明细不再占用物料引用

    token = get_csrf(client, '/system/recycle?type=product')
    resp = client.post('/system/recycle/product/%d/restore' % p.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '已恢复'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(Product, p.id).is_deleted is False
    assert all(not item.is_deleted for item in p.bom_items)


def test_order_links_product_and_shows_bom(client):
    login(client, 'admin', 'admin123')
    m = _material('PB-M04', '工单用料')
    token = get_csrf(client, '/production/products')
    data = _product_form_data('PRD92', '关联测试产品', [(3, m)])
    data['csrf_token'] = token
    client.post('/production/products/new', data=data, follow_redirects=True)
    p = Product.query.filter_by(code='PRD92').first()

    due = (date.today() + timedelta(days=3)).isoformat()
    token = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new', data={
        'csrf_token': token, 'product_id': str(p.id),
        'product_name': '随手乱输的名字', 'quantity': '5', 'due_date': due,
        'priority': 'normal', 'leader_id': '0', 'related_department_id': '0',
        'route_id': '0', 'plan_start_date': '', 'plan_end_date': '', 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200

    order = WorkOrder.query.filter_by(product_id=p.id).first()
    assert order is not None
    assert order.product_name == '关联测试产品'  # 产品名快照覆盖手输，避免同物多名

    html = client.get('/production/orders/%d' % order.id).get_data(as_text=True)
    assert '标准用料（BOM）' in html
    assert 'PRD92' in html
    assert 'PB-M04' in html
    assert '15.00' in html  # 单件用量 3 × 工单数量 5

    # 编辑工单可改为不关联产品，保留原有名称快照
    token = get_csrf(client, '/production/orders/%d/edit' % order.id)
    resp = client.post('/production/orders/%d/edit' % order.id, data={
        'csrf_token': token, 'product_id': '0', 'product_name': '历史自由文本',
        'quantity': '5', 'due_date': due, 'priority': 'normal',
        'leader_id': '0', 'related_department_id': '0',
        'plan_start_date': '', 'plan_end_date': '', 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire_all()
    order = db.session.get(WorkOrder, order.id)
    assert order.product_id is None and order.product_name == '历史自由文本'
    assert '工单未关联产品档案' in client.get(
        '/production/orders/%d' % order.id).get_data(as_text=True)


def test_route_links_product_and_order_form_recommends(client):
    login(client, 'admin', 'admin123')
    m = _material('PB-M05', '路线产品料')
    token = get_csrf(client, '/production/products')
    data = _product_form_data('PRD93', '路线产品', [(1, m)])
    data['csrf_token'] = token
    client.post('/production/products/new', data=data, follow_redirects=True)
    p = Product.query.filter_by(code='PRD93').first()

    process = Process(code='PB-OP', name='路线工序')
    db.session.add(process)
    db.session.commit()

    token = get_csrf(client, '/production/process-routes')
    resp = client.post('/production/process-routes/new', data={
        'csrf_token': token, 'code': 'PB-RT', 'name': '路线产品路线',
        'product_id': str(p.id), 'product_name': '手输名称',
        'process_ids': [str(process.id)], 'seq_%d' % process.id: '1', 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    route = ProcessRoute.query.filter_by(code='PB-RT').first()
    assert route is not None
    assert route.product_id == p.id
    assert route.product_name == '路线产品'  # 关联产品时名称自动带出

    # 新建工单页包含该路线及其关联产品，供前端按产品筛选推荐
    html = client.get('/production/orders/new').get_data(as_text=True)
    assert 'PB-RT' in html
    assert 'PRD93' in html
    assert 'routeMap' in html


def test_product_menu_and_permission(client):
    login(client, 'admin', 'admin123')
    html = client.get('/production/products').get_data(as_text=True)
    assert '产品档案' in html
    assert '标准用料' in html

    client.get('/auth/logout')
    token = get_csrf(client, '/auth/login')
    client.post('/auth/login', data={'csrf_token': token, 'username': 'staff1',
                                     'password': '123456'}, follow_redirects=True)
    assert client.get('/production/products').status_code == 403
    assert client.post('/production/products/new',
                       data={'csrf_token': token}).status_code == 403
