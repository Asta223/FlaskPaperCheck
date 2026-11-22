# -*- coding: utf-8 -*-
"""P3 生产工单优化：计划态锁定工序执行、质量记录、不良原因主数据。"""
from conftest import get_csrf, login

from app import db
from app.models import DefectReason, User, WorkOrder, WorkOrderStep

_SEQ = [0]


def _order(status='pending'):
    _SEQ[0] += 1
    order = WorkOrder(order_no='WQ3%04d' % _SEQ[0], product_name='质量测试产品',
                      quantity=10, created_by=1, status=status)
    db.session.add(order)
    db.session.commit()
    return order


def _step(order, status='pending'):
    step = WorkOrderStep(work_order_id=order.id, name='装配', seq=1, status=status)
    db.session.add(step)
    db.session.commit()
    return step


def _reason(code='DRQA01', name='尺寸超差', category='来料'):
    reason = DefectReason(code=code, name=name, category=category)
    db.session.add(reason)
    db.session.commit()
    return reason


def _csrf_detail(client, order):
    # 终态工单详情页已无添加工序表单，回退到新建工单页取同会话通用 token
    resp = client.get('/production/orders/%d' % order.id)
    if b'name="csrf_token"' in resp.data:
        return get_csrf(client, '/production/orders/%d' % order.id)
    return get_csrf(client, '/production/orders/new')


# ---------------- 状态守卫 ----------------

def test_pending_order_blocks_step_execution(client):
    """待开始是计划态：工序流转/工时修正在页面隐藏、直接 POST 也被拒。"""
    order = _order('pending')
    step = _step(order)
    login(client, 'producer1', '123456')
    html = client.get('/production/orders/%d' % order.id).get_data(as_text=True)
    assert '工序流转与工时修正已锁定' in html
    assert '/production/steps/%d/status' % step.id not in html

    token = _csrf_detail(client, order)
    resp = client.post('/production/steps/%d/status' % step.id,
                       data={'csrf_token': token, 'status': 'in_progress'},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert '只有「进行中」工单'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(WorkOrderStep, step.id).status == 'pending'

    resp = client.post('/production/steps/%d/status' % step.id,
                       data={'csrf_token': token, 'status': 'completed'},
                       follow_redirects=True)
    assert '只有「进行中」工单'.encode() in resp.data
    resp = client.post('/production/steps/%d/labor' % step.id,
                       data={'csrf_token': token, 'labor_hours': '5', 'remark': ''},
                       follow_redirects=True)
    assert '只有「进行中」工单才能修正工序工时'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(WorkOrderStep, step.id).labor_hours == 0


def test_in_progress_order_allows_step_flow(client):
    """工单流转到进行中后才允许执行工序；完成自动算工时。"""
    order = _order('in_progress')
    step = _step(order)
    login(client, 'producer1', '123456')
    token = _csrf_detail(client, order)
    client.post('/production/steps/%d/status' % step.id,
                data={'csrf_token': token, 'status': 'in_progress'}, follow_redirects=True)
    db.session.expire_all()
    started = db.session.get(WorkOrderStep, step.id)
    assert started.status == 'in_progress' and started.started_at is not None
    client.post('/production/steps/%d/status' % step.id,
                data={'csrf_token': token, 'status': 'completed'}, follow_redirects=True)
    db.session.expire_all()
    done = db.session.get(WorkOrderStep, step.id)
    assert done.status == 'completed' and done.finished_at is not None


def test_finished_order_blocks_step_execution(client):
    """已完成/已验收是终态，不能再执行工序。"""
    for status in ('completed', 'accepted'):
        order = _order(status)
        step = _step(order)
        login(client, 'producer1', '123456')
        token = _csrf_detail(client, order)
        resp = client.post('/production/steps/%d/status' % step.id,
                           data={'csrf_token': token, 'status': 'in_progress'},
                           follow_redirects=True)
        assert '只有「进行中」工单'.encode() in resp.data
        db.session.expire_all()
        assert db.session.get(WorkOrderStep, step.id).status == 'pending'


# ---------------- 质量记录 ----------------

def test_quality_record_calculates_rates_and_validates(client):
    """良率/不良率由服务端计算；不良品必须有主数据原因；数量必须自洽。"""
    order = _order('in_progress')
    reason = _reason()
    producer = User.query.filter_by(username='producer1').first()
    login(client, 'producer1', '123456')
    token = _csrf_detail(client, order)

    resp = client.post('/production/orders/%d/quality' % order.id, data={
        'csrf_token': token, 'output_qty': '10', 'good_qty': '8', 'defect_qty': '2',
        'defect_reason_id': str(reason.id), 'quality_remark': '来料批次异常',
    }, follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire_all()
    saved = db.session.get(WorkOrder, order.id)
    assert (saved.output_qty, saved.good_qty, saved.defect_qty) == (10, 8, 2)
    assert saved.yield_rate == 80.0 and saved.defect_rate == 20.0
    assert saved.defect_reason_id == reason.id
    assert saved.quality_remark == '来料批次异常'
    assert saved.quality_recorded_by == producer.id and saved.quality_recorded_at is not None

    # 修正后重新计算
    client.post('/production/orders/%d/quality' % order.id, data={
        'csrf_token': token, 'output_qty': '10', 'good_qty': '9', 'defect_qty': '1',
        'defect_reason_id': str(reason.id), 'quality_remark': '',
    }, follow_redirects=True)
    db.session.expire_all()
    saved = db.session.get(WorkOrder, order.id)
    assert saved.yield_rate == 90.0 and saved.defect_rate == 10.0

    # 有不良品但没选原因 → 拒绝且不覆盖原记录
    resp = client.post('/production/orders/%d/quality' % order.id, data={
        'csrf_token': token, 'output_qty': '10', 'good_qty': '9', 'defect_qty': '1',
        'defect_reason_id': '0', 'quality_remark': '',
    }, follow_redirects=True)
    assert '必须选择不良原因'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(WorkOrder, order.id).yield_rate == 90.0

    # 良品 + 不良 ≠ 成品 → 拒绝
    resp = client.post('/production/orders/%d/quality' % order.id, data={
        'csrf_token': token, 'output_qty': '20', 'good_qty': '9', 'defect_qty': '1',
        'defect_reason_id': str(reason.id), 'quality_remark': '',
    }, follow_redirects=True)
    assert '必须等于成品数量'.encode() in resp.data


def test_quality_record_only_for_active_orders(client):
    """待开始/已验收工单不能写质量记录。"""
    login(client, 'producer1', '123456')
    for status in ('pending', 'accepted'):
        order = _order(status)
        token = _csrf_detail(client, order)
        resp = client.post('/production/orders/%d/quality' % order.id, data={
            'csrf_token': token, 'output_qty': '5', 'good_qty': '5',
            'defect_qty': '0', 'defect_reason_id': '0', 'quality_remark': '',
        }, follow_redirects=True)
        assert '只有「进行中」或「已完成」工单'.encode() in resp.data
        db.session.expire_all()
        assert db.session.get(WorkOrder, order.id).output_qty == 0


# ---------------- 不良原因主数据 ----------------

def test_defect_reason_crud_toggle_soft_delete_and_restore(client):
    """主数据可增删改查/启停；被引用时拒绝删除；软删后可从回收站恢复。"""
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/defect-reasons')
    resp = client.post('/production/defect-reasons/new', data={
        'csrf_token': token, 'code': 'DRQA02', 'name': '焊接虚焊', 'category': '工艺',
        'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    reason = DefectReason.query.filter_by(code='DRQA02').first()
    assert reason is not None
    assert '焊接虚焊'.encode() in resp.data

    # 重复编码拒绝
    resp = client.post('/production/defect-reasons/new', data={
        'csrf_token': token, 'code': 'DRQA02', 'name': '另一个原因', 'category': '',
        'remark': '',
    }, follow_redirects=True)
    assert '编码或名称已存在'.encode() in resp.data

    # 编辑 + 停用
    client.post('/production/defect-reasons/%d/edit' % reason.id, data={
        'csrf_token': token, 'code': 'DRQA02', 'name': '焊接不良', 'category': '工艺',
        'remark': '已更新',
    }, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(DefectReason, reason.id).name == '焊接不良'
    client.post('/production/defect-reasons/%d/toggle' % reason.id,
                data={'csrf_token': token}, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(DefectReason, reason.id).is_active is False

    # 被质量记录引用 → 拒绝删除
    order = _order('in_progress')
    order.record_quality(2, 1, 1, reason.id, '', 1)
    db.session.commit()
    resp = client.post('/production/defect-reasons/%d/delete' % reason.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert '仍被'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(DefectReason, reason.id).is_deleted is False

    # 未引用的原因可软删，超管从回收站恢复
    spare = _reason('DRQA03', '包装破损', '物流')
    client.post('/production/defect-reasons/%d/delete' % spare.id,
                data={'csrf_token': token}, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(DefectReason, spare.id).is_deleted is True
    assert DefectReason.query.filter_by(code='DRQA03').count() == 0  # 全局过滤隐藏
    login(client, 'admin', 'admin123')
    recycle = client.get('/system/recycle?type=defect_reason').get_data(as_text=True)
    assert '包装破损' in recycle
    token = get_csrf(client, '/system/recycle?type=defect_reason')
    client.post('/system/recycle/defect_reason/%d/restore' % spare.id,
                data={'csrf_token': token}, follow_redirects=True)
    assert DefectReason.query.filter_by(code='DRQA03').first() is not None


def test_disabled_reason_not_selectable_and_permission_guarded(client):
    """停用原因不进下拉；普通员工无维护/记录权限。"""
    reason = _reason('DRQA04', '标签错误', '标识')
    reason.is_active = False
    db.session.commit()
    order = _order('in_progress')
    login(client, 'producer1', '123456')
    html = client.get('/production/orders/%d' % order.id).get_data(as_text=True)
    assert '标签错误' not in html

    client.get('/auth/logout')
    token = get_csrf(client, '/auth/login')  # 登录后同会话内通用 CSRF token
    client.post('/auth/login', data={'csrf_token': token, 'username': 'staff1',
                                     'password': '123456'}, follow_redirects=True)
    assert client.get('/production/defect-reasons').status_code == 403
    assert client.post('/production/defect-reasons/new',
                       data={'csrf_token': token}).status_code == 403
    assert client.post('/production/orders/%d/quality' % order.id,
                       data={'csrf_token': token}).status_code == 403


def test_quality_allows_zero_defect_and_zero_good(client):
    """0 是合法数量：全良品(不良=0)与全不良(良品=0)都要能上报，原因可空/必填按数量判定。"""
    order = _order('in_progress')
    reason = _reason('DRZERO01', '整批不良')
    login(client, 'producer1', '123456')
    token = _csrf_detail(client, order)

    # 良率 100%：不良数量=0，不良原因留空
    resp = client.post('/production/orders/%d/quality' % order.id, data={
        'csrf_token': token, 'output_qty': '10', 'good_qty': '10', 'defect_qty': '0',
        'defect_reason_id': '0', 'quality_remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert '校验失败'.encode() not in resp.data
    db.session.expire_all()
    saved = db.session.get(WorkOrder, order.id)
    assert (saved.output_qty, saved.good_qty, saved.defect_qty) == (10, 10, 0)
    assert saved.yield_rate == 100.0 and saved.defect_rate == 0.0
    assert saved.defect_reason_id is None

    # 不良率 100%：合格数量=0，此时必须选择不良原因
    resp = client.post('/production/orders/%d/quality' % order.id, data={
        'csrf_token': token, 'output_qty': '10', 'good_qty': '0', 'defect_qty': '10',
        'defect_reason_id': str(reason.id), 'quality_remark': '整批异常',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert '校验失败'.encode() not in resp.data
    db.session.expire_all()
    saved = db.session.get(WorkOrder, order.id)
    assert (saved.output_qty, saved.good_qty, saved.defect_qty) == (10, 0, 10)
    assert saved.yield_rate == 0.0 and saved.defect_rate == 100.0
    assert saved.defect_reason_id == reason.id

    # 真正没填的数量仍要被拒绝，且提示具体字段
    resp = client.post('/production/orders/%d/quality' % order.id, data={
        'csrf_token': token, 'output_qty': '', 'good_qty': '10', 'defect_qty': '0',
        'defect_reason_id': '0', 'quality_remark': '',
    }, follow_redirects=True)
    assert '校验失败'.encode() in resp.data
    assert '请输入成品数量'.encode() in resp.data
