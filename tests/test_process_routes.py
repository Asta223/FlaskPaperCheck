# -*- coding: utf-8 -*-
"""工艺路线（工序组）测试：主数据 CRUD、顺序、权限、工单新建批量生成工序。"""
from datetime import date, timedelta

from conftest import get_csrf, login

from app import db
from app.models import Process, ProcessRoute, ProcessRouteItem, WorkOrder
from app.utils.delete_guard import find_references


def _process(code, name, hours=1.0):
    p = Process(code=code, name=name, standard_hours=hours)
    db.session.add(p)
    db.session.commit()
    return p


def _route(code='RT99', name='测试路线', product='圣诞树', processes=None):
    route = ProcessRoute(code=code, name=name, product_name=product)
    db.session.add(route)
    db.session.flush()
    for seq, process in enumerate(processes or [], 1):
        db.session.add(ProcessRouteItem(route_id=route.id, process_id=process.id, seq=seq))
    db.session.commit()
    return route


def _route_form_data(code, name, picked, product='圣诞树'):
    data = {'csrf_token': '', 'code': code, 'name': name,
            'product_name': product, 'remark': ''}
    for seq, process in picked:
        data.setdefault('process_ids', []).append(str(process.id))
        data['seq_%d' % process.id] = str(seq)
    return data


def test_route_create_edit_and_ordering(client):
    login(client, 'admin', 'admin123')
    p1 = _process('RTP01', '路线工序甲', 2)
    p2 = _process('RTP02', '路线工序乙', 3)

    token = get_csrf(client, '/production/process-routes')
    data = _route_form_data('RT90', '顺序测试路线', [(2, p1), (1, p2)])
    data['csrf_token'] = token
    resp = client.post('/production/process-routes/new', data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert '已创建，含 2 道工序'.encode() in resp.data

    route = ProcessRoute.query.filter_by(code='RT90').first()
    assert route is not None
    assert [(item.seq, item.process_id) for item in route.items] == [(1, p2.id), (2, p1.id)]

    # 重复编码被拒
    token = get_csrf(client, '/production/process-routes')
    dup = _route_form_data('RT90', '另一个名字', [(1, p1)])
    dup['csrf_token'] = token
    resp = client.post('/production/process-routes/new', data=dup, follow_redirects=True)
    assert '编码或名称已存在'.encode() in resp.data

    # 编辑：物理替换明细，不留旧的软删行
    token = get_csrf(client, '/production/process-routes?edit_id=%d' % route.id)
    edit = _route_form_data('RT90', '顺序测试路线', [(1, p1)])
    edit['csrf_token'] = token
    resp = client.post('/production/process-routes/%d/edit' % route.id,
                       data=edit, follow_redirects=True)
    assert '已保存'.encode() in resp.data
    db.session.expire_all()
    route = db.session.get(ProcessRoute, route.id)
    assert [item.process_id for item in route.items] == [p1.id]
    assert ProcessRouteItem.query.filter_by(route_id=route.id).count() == 1


def test_route_delete_hides_items_and_releases_process_reference(client):
    login(client, 'admin', 'admin123')
    p1 = _process('RTD01', '删除路线用工序')
    route = _route('RT91', '待删路线', processes=[p1])
    assert 'process_route_items' in find_references(p1)

    token = get_csrf(client, '/production/process-routes')
    resp = client.post('/production/process-routes/%d/delete' % route.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '已删除'.encode() in resp.data
    assert ProcessRoute.query.filter_by(code='RT91').first() is None
    # 明细随路线一起软删，不再占用工序引用
    items = (ProcessRouteItem.query.execution_options(include_deleted=True)
             .filter_by(route_id=route.id).all())
    assert len(items) == 1 and items[0].is_deleted is True
    assert find_references(p1) == {}

    # 回收站恢复：明细一并恢复
    token = get_csrf(client, '/system/recycle?type=process_route')
    resp = client.post('/system/recycle/process_route/%d/restore' % route.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '已恢复'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(ProcessRoute, route.id).is_deleted is False
    assert all(not item.is_deleted for item in route.items)


def test_order_new_batch_adds_steps_from_route(client):
    login(client, 'admin', 'admin123')
    p1 = _process('RTB01', '批量工序一', 2)
    p2 = _process('RTB02', '批量工序二', 3)
    route = _route('RT92', '批量路线', product='圣诞树', processes=[p1, p2])
    due = (date.today() + timedelta(days=3)).isoformat()

    token = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new', data={
        'csrf_token': token, 'product_name': '圣诞树', 'quantity': '10',
        'due_date': due, 'priority': 'normal', 'leader_id': '0',
        'related_department_id': '0', 'route_id': str(route.id),
        'plan_start_date': '', 'plan_end_date': '', 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert '批量添加 2 道工序'.encode() in resp.data

    order = WorkOrder.query.filter_by(product_name='圣诞树').first()
    assert order is not None
    assert [(s.seq, s.name, s.process_id) for s in order.steps] == [
        (1, p1.name, p1.id), (2, p2.name, p2.id)]
    # L1 倒排应在批量工序落库后生效
    assert order.plan_end_date == date.fromisoformat(due)
    assert order.plan_start_date is not None

    # 不选路线时保持逐个添加（无预置工序）
    token = get_csrf(client, '/production/orders/new')
    client.post('/production/orders/new', data={
        'csrf_token': token, 'product_name': '不选用路线工单', 'quantity': '1',
        'due_date': '', 'priority': 'normal', 'leader_id': '0',
        'related_department_id': '0', 'route_id': '0',
        'plan_start_date': '', 'plan_end_date': '', 'remark': '',
    }, follow_redirects=True)
    no_route = WorkOrder.query.filter_by(product_name='不选用路线工单').first()
    assert no_route is not None and no_route.steps == []


def test_route_menu_and_permission(client):
    login(client, 'admin', 'admin123')
    html = client.get('/production/process-routes').get_data(as_text=True)
    assert '工艺路线' in html

    client.get('/auth/logout')
    token = get_csrf(client, '/auth/login')
    client.post('/auth/login', data={'csrf_token': token, 'username': 'staff1',
                                     'password': '123456'}, follow_redirects=True)
    assert client.get('/production/process-routes').status_code == 403
    assert client.post('/production/process-routes/new',
                       data={'csrf_token': token}).status_code == 403
