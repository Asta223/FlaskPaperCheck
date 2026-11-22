# -*- coding: utf-8 -*-
"""工单工序清单冻结 + 撤销开工增量测试。"""
from conftest import get_csrf

from app import db
from app.models import OperationLog, Process, User, WorkOrder, WorkOrderStep


def _order(order_no, status='pending'):
    admin = User.query.filter_by(username='admin').first()
    o = WorkOrder(order_no=order_no, product_name='冻结测试', quantity=1,
                  created_by=admin.id, status=status)
    db.session.add(o)
    db.session.commit()
    return o


def _login(client, username, password):
    """返回登录前从登录页取的 CSRF token（该 token 登录后继续通用）。"""
    client.get('/auth/logout')
    token = get_csrf(client, '/auth/login')
    client.post('/auth/login', data={'username': username, 'password': password,
                                     'csrf_token': token}, follow_redirects=True)
    return token


def _post_step(client, order, process_id, token, seq=1):
    return client.post('/production/orders/%d/steps/new' % order.id, data={
        'csrf_token': token, 'process_id': str(process_id), 'seq': str(seq),
        'operator_id': '0', 'remark': '',
    }, follow_redirects=True)


def _post_reopen(client, order, token):
    return client.post('/production/orders/%d/reopen' % order.id,
                       data={'csrf_token': token}, follow_redirects=True)


def _step_count(order_id):
    return WorkOrderStep.query.filter_by(work_order_id=order_id).count()


def test_non_pending_orders_reject_new_step(client):
    """进行中/已完成/已验收均不得添加工序。"""
    token = _login(client, 'admin', 'admin123')
    pid = Process.query.filter_by(code='OP01').first().id
    for status in ('in_progress', 'completed', 'accepted'):
        o = _order('FRZ-%s' % status, status=status)
        resp = _post_step(client, o, pid, token)
        assert resp.status_code == 200
        assert '工序清单已冻结'.encode() in resp.data
        assert _step_count(o.id) == 0, status


def test_pending_order_can_add_step(client):
    """待开始仍可正常添加工序（回归保护，防止守卫过严）。"""
    token = _login(client, 'admin', 'admin123')
    pid = Process.query.filter_by(code='OP01').first().id
    o = _order('FRZ-PENDING')
    resp = _post_step(client, o, pid, token)
    assert '已添加'.encode() in resp.data
    assert _step_count(o.id) == 1


def test_reopen_then_add_step_then_restart(client):
    """撤销开工回到待开始 → 调整工序 → 再流转回进行中的完整补救链路。"""
    token = _login(client, 'admin', 'admin123')
    pid = Process.query.filter_by(code='OP01').first().id
    o = _order('FRZ-REOPEN', status='in_progress')
    db.session.add(WorkOrderStep(work_order_id=o.id, name='已开工工序', seq=1,
                                 status='in_progress', labor_hours=2.0))
    db.session.commit()

    resp = _post_reopen(client, o, token)
    assert '已撤销开工'.encode() in resp.data
    db.session.expire_all()
    assert o.status == 'pending'
    # 已开工工序及其工时保留，不被重置
    kept = WorkOrderStep.query.filter_by(work_order_id=o.id).first()
    assert kept.status == 'in_progress' and kept.labor_hours == 2.0

    resp = _post_step(client, o, pid, token, seq=2)
    assert '已添加'.encode() in resp.data
    assert _step_count(o.id) == 2

    resp = client.post('/production/orders/%d/status' % o.id, data={
        'csrf_token': token, 'status': 'in_progress',
    }, follow_redirects=True)
    assert '已流转为「进行中」'.encode() in resp.data
    db.session.expire_all()
    assert o.status == 'in_progress'


def test_reopen_writes_log_and_rejects_wrong_status(client):
    """撤销开工写 transition 日志；非进行中状态调用被拒且状态不变。"""
    token = _login(client, 'admin', 'admin123')
    o = _order('FRZ-LOG', status='in_progress')
    _post_reopen(client, o, token)
    log = OperationLog.query.filter_by(target_type='work_order', target_id=o.id,
                                       action='transition').order_by(
                                           OperationLog.id.desc()).first()
    assert log is not None and '撤销开工' in log.summary

    o2 = _order('FRZ-NOPE', status='pending')
    resp = _post_reopen(client, o2, token)
    assert '只有「进行中」工单可以撤销开工'.encode() in resp.data
    db.session.expire_all()
    assert o2.status == 'pending'


def test_reopen_requires_manage_permission(client):
    """普通员工无 production.manage，撤销开工返回 403。"""
    token = _login(client, 'staff1', '123456')
    o = _order('FRZ-DENY', status='in_progress')
    assert client.post('/production/orders/%d/reopen' % o.id,
                       data={'csrf_token': token}).status_code == 403


def test_detail_shows_freeze_hint_and_reopen_button(client):
    """进行中详情页隐藏添加表单，展示冻结提示与撤销开工按钮；待开始相反。"""
    token = _login(client, 'admin', 'admin123')
    running = _order('FRZ-UI-RUN', status='in_progress')
    html = client.get('/production/orders/%d?tab=steps' % running.id).get_data(as_text=True)
    assert ('/production/orders/%d/steps/new' % running.id) not in html
    assert '工序清单已冻结' in html
    assert '/production/orders/%d/reopen' % running.id in html

    pending = _order('FRZ-UI-PENDING')
    html = client.get('/production/orders/%d?tab=steps' % pending.id).get_data(as_text=True)
    assert ('/production/orders/%d/steps/new' % pending.id) in html
    assert '/production/orders/%d/reopen' % pending.id not in html
