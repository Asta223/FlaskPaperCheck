# -*- coding: utf-8 -*-
"""P4 增量测试：回收站硬删除、工序表单 action、工序占用锁、进行中工序禁删。"""
from conftest import get_csrf, login

from app import db
from app.models import (OperationLog, Process, User, Warehouse, WorkOrder,
                        WorkOrderStep)
from app.models.system import OperationLog as Log


def _process(code, name):
    p = Process(code=code, name=name)
    db.session.add(p)
    db.session.commit()
    return p


def _order(order_no, status='pending'):
    admin = User.query.filter_by(username='admin').first()
    o = WorkOrder(order_no=order_no, product_name='P4产品', quantity=1,
                  created_by=admin.id, status=status)
    db.session.add(o)
    db.session.commit()
    return o


# ---------------- 回收站硬删除 ----------------

def test_recycle_purge_physically_deletes_and_logs(client):
    """管理员回收站彻底删除：数据库物理移除 + purge 操作日志。"""
    login(client, 'admin', 'admin123')
    w = Warehouse(name='P4待清空仓', location='测试')
    db.session.add(w)
    db.session.commit()
    token = get_csrf(client, '/warehouse/warehouses')
    client.post('/warehouse/warehouses/%d/delete' % w.id, data={'csrf_token': token})
    assert db.session.get(Warehouse, w.id).is_deleted is True

    token2 = get_csrf(client, '/system/recycle?type=warehouse')
    resp = client.post('/system/recycle/warehouse/%d/purge' % w.id,
                       data={'csrf_token': token2}, follow_redirects=True)
    assert resp.status_code == 200
    assert '已彻底删除'.encode() in resp.data
    assert db.session.get(Warehouse, w.id) is None  # 物理删除
    assert Log.query.filter_by(action='purge', target_type='warehouse',
                               target_id=w.id).count() == 1


def test_recycle_purge_rejects_referenced_record(client):
    """仍被未删除工单引用的工序禁止彻底删除。"""
    login(client, 'admin', 'admin123')
    p = _process('OPP4R', '占用工序')
    o = _order('WOP4PURGE')
    db.session.add(WorkOrderStep(work_order_id=o.id, process_id=p.id,
                                 name=p.name, seq=1))
    db.session.commit()
    token = get_csrf(client, '/production/processes')
    client.post('/production/processes/%d/delete' % p.id, data={'csrf_token': token})
    # 该工序被未完结工单占用，软删本身会被拒绝；直接测硬删守卫需在回收站中
    p.is_deleted = True
    db.session.commit()
    token2 = get_csrf(client, '/system/recycle?type=process')
    resp = client.post('/system/recycle/process/%d/purge' % p.id,
                       data={'csrf_token': token2}, follow_redirects=True)
    assert '无法彻底删除'.encode() in resp.data
    assert db.session.get(Process, p.id).is_deleted is True  # 仍在回收站


def test_recycle_purge_requires_permission(client):
    """普通员工无法使用回收站彻底删除。"""
    p = _process('OPP4NP', '无权删除工序')
    p.is_deleted = True
    db.session.commit()
    login(client, 'staff1', '123456')
    token = get_csrf(client, '/attendance/leave/new')
    resp = client.post('/system/recycle/process/%d/purge' % p.id,
                       data={'csrf_token': token})
    assert resp.status_code == 403


# ---------------- 工序表单 ----------------

def test_process_form_posts_to_correct_route(client):
    """新增/编辑表单的 action 指向各自 POST 路由，不再 405。"""
    login(client, 'producer1', '123456')
    html = client.get('/production/processes').get_data(as_text=True)
    assert '/production/processes/new' in html
    p = _process('OPP4F', '表单工序')
    edit_html = client.get('/production/processes?edit_id=%d' % p.id).get_data(as_text=True)
    assert '/production/processes/%d/edit' % p.id in edit_html

    token = get_csrf(client, '/production/processes')
    resp = client.post('/production/processes/new', data={
        'csrf_token': token, 'code': 'OPP4N', 'name': '新建成功',
        'standard_hours': '1', 'sort_order': '9', 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert '新建成功'.encode() in resp.data
    assert Process.query.filter_by(code='OPP4N').first() is not None

    token2 = get_csrf(client, '/production/processes')
    resp2 = client.post('/production/processes/%d/edit' % p.id, data={
        'csrf_token': token2, 'code': 'OPP4F', 'name': '编辑成功',
        'standard_hours': '2', 'sort_order': '1', 'remark': '',
    }, follow_redirects=True)
    assert resp2.status_code == 200
    assert '编辑成功'.encode() in resp2.data


# ---------------- 工序占用锁 ----------------

def test_process_locked_by_unfinished_order(client):
    """未完结工单引用的工序禁止编辑、停用、删除；完结后解锁。"""
    login(client, 'producer1', '123456')
    p = _process('OPP4L', '被占用工序')
    o = _order('WOP4LOCK')
    db.session.add(WorkOrderStep(work_order_id=o.id, process_id=p.id,
                                 name=p.name, seq=1))
    db.session.commit()

    token = get_csrf(client, '/production/processes')
    resp = client.post('/production/processes/%d/edit' % p.id, data={
        'csrf_token': token, 'code': 'OPP4L', 'name': '改名被拒',
        'standard_hours': '1', 'sort_order': '1', 'remark': '',
    }, follow_redirects=True)
    assert '禁止编辑'.encode() in resp.data
    assert db.session.get(Process, p.id).name == '被占用工序'

    client.post('/production/processes/%d/toggle' % p.id,
                data={'csrf_token': token}, follow_redirects=True)
    assert db.session.get(Process, p.id).is_active is True

    client.post('/production/processes/%d/delete' % p.id,
                data={'csrf_token': token}, follow_redirects=True)
    assert db.session.get(Process, p.id).is_deleted is False

    # 完结后解锁
    o.status = 'accepted'
    db.session.commit()
    resp2 = client.post('/production/processes/%d/edit' % p.id, data={
        'csrf_token': token, 'code': 'OPP4L', 'name': '完结后可改',
        'standard_hours': '1', 'sort_order': '1', 'remark': '',
    }, follow_redirects=True)
    assert '完结后可改'.encode() in resp2.data


# ---------------- 进行中工单工序禁删 ----------------

def test_in_progress_order_steps_cannot_delete(client):
    """进行中工单的工序（即使待开始）也不允许删除。"""
    login(client, 'producer1', '123456')
    o = _order('WOP4STEP', status='in_progress')
    step = WorkOrderStep(work_order_id=o.id, name='进行中工序', seq=1,
                         status='pending')
    db.session.add(step)
    db.session.commit()
    token = get_csrf(client, '/production/orders/%d' % o.id)
    resp = client.post('/production/steps/%d/delete' % step.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '不允许删除'.encode() in resp.data
    assert db.session.get(WorkOrderStep, step.id).is_deleted is False

    # 回到待开始后可删
    o.status = 'pending'
    db.session.commit()
    client.post('/production/steps/%d/delete' % step.id,
                data={'csrf_token': token}, follow_redirects=True)
    assert db.session.get(WorkOrderStep, step.id).is_deleted is True
