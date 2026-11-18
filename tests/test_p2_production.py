# -*- coding: utf-8 -*-
"""P2 增量测试：工序主数据、工单工序下拉引用、消耗工时、领料余量校验。

覆盖需求：
1. 工序档案独立维护（新建/唯一性/停用/权限），工单只能下拉引用已维护工序；
2. 工序完成自动算工时 + 手动修正；
3. 领料前置余量校验（不足拒绝且库存不变）+ 余量查询 API；
4. 生产侧无审批流（无审批字段/路由），人事请假审批保持可用。
"""
from datetime import datetime, timedelta

from conftest import get_csrf, login

from app import db
from app.models import (Inventory, LeaveRequest, Material, Process, User, Warehouse,
                        WorkOrder, WorkOrderStep)


def _process(code='OP99', name='测试工序', hours=1.5):
    p = Process(code=code, name=name, standard_hours=hours)
    db.session.add(p)
    db.session.commit()
    return p


def _order():
    admin = User.query.filter_by(username='admin').first()
    o = WorkOrder(order_no='WOP2%03d' % (WorkOrder.query.count() + 1),
                  product_name='P2测试产品', quantity=1, created_by=admin.id)
    db.session.add(o)
    db.session.commit()
    return o


# ---------------- 工序档案 ----------------

def test_process_list_shows_seeded_processes(client):
    login(client, 'producer1', '123456')
    resp = client.get('/production/processes')
    assert resp.status_code == 200
    assert b'OP01' in resp.data and '下料'.encode() in resp.data


def test_process_create_duplicate_code_rejected(client):
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/processes')
    # 与种子 OP01 编码重复
    resp = client.post('/production/processes/new', data={
        'csrf_token': token, 'code': 'OP01', 'name': '全新工序',
        'standard_hours': '1', 'sort_order': '9', 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert '\u5df2\u5b58\u5728'.encode() in resp.data
    assert Process.query.filter_by(name='全新工序').first() is None


def test_process_create_and_toggle(client):
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/processes')
    resp = client.post('/production/processes/new', data={
        'csrf_token': token, 'code': 'OP98', 'name': '焊接',
        'standard_hours': '2.5', 'sort_order': '6', 'remark': '新增',
    }, follow_redirects=True)
    assert resp.status_code == 200
    p = Process.query.filter_by(code='OP98').first()
    assert p is not None and p.standard_hours == 2.5 and p.is_active
    # 停用
    token = get_csrf(client, '/production/processes')
    client.post('/production/processes/%d/toggle' % p.id,
                data={'csrf_token': token}, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(Process, p.id).is_active is False


def test_process_manage_permission_required(client):
    """普通员工无 production.process.manage，提交新增被 403 拒绝。"""
    login(client, 'staff1', '123456')
    # 员工无 production.view，工序档案页本身不可见；从员工有权限的请假页取 CSRF
    token = get_csrf(client, '/attendance/leave/new')
    resp = client.post('/production/processes/new', data={
        'csrf_token': token, 'code': 'OP97', 'name': '越权工序',
        'standard_hours': '1', 'sort_order': '9', 'remark': '',
    })
    assert resp.status_code == 403
    assert Process.query.filter_by(code='OP97').first() is None


# ---------------- 工单工序下拉引用 ----------------

def test_step_form_uses_process_dropdown(client):
    login(client, 'producer1', '123456')
    o = _order()
    html = client.get('/production/orders/%d' % o.id).get_data(as_text=True)
    assert 'name="process_id"' in html
    assert 'OP01' in html
    # 自由输入 name 字段已移除（表单片段定位）
    seg = html.split('添加工序')[1][:1500] if '添加工序' in html else ''
    assert 'name="name"' not in seg


def test_step_new_binds_process_and_snapshots_name(client):
    login(client, 'producer1', '123456')
    o = _order()
    p = _process()
    token = get_csrf(client, '/production/orders/%d' % o.id)
    resp = client.post('/production/orders/%d/steps/new' % o.id, data={
        'csrf_token': token, 'process_id': p.id, 'seq': 1,
        'operator_id': 0, 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    step = WorkOrderStep.query.filter_by(work_order_id=o.id).first()
    assert step is not None
    assert step.process_id == p.id
    assert step.name == p.name  # 快照带出
    # 工序档案改名后，历史步骤名称不变
    p.name = '改名后的工序'
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(WorkOrderStep, step.id).name == '测试工序'


def test_step_new_rejects_disabled_process(client):
    login(client, 'producer1', '123456')
    o = _order()
    p = _process(code='OP96', name='停用工序')
    p.is_active = False
    db.session.commit()
    token = get_csrf(client, '/production/orders/%d' % o.id)
    client.post('/production/orders/%d/steps/new' % o.id, data={
        'csrf_token': token, 'process_id': p.id, 'seq': 1,
        'operator_id': 0, 'remark': '',
    }, follow_redirects=True)
    assert WorkOrderStep.query.filter_by(work_order_id=o.id).count() == 0


# ---------------- 消耗工时 ----------------

def test_step_completion_auto_calculates_labor_hours(client):
    login(client, 'producer1', '123456')
    o = _order()
    o.status = 'in_progress'  # P2-6：只有进行中工单可执行工序流转
    db.session.commit()
    step = WorkOrderStep(work_order_id=o.id, name='工时测试', seq=1)
    db.session.add(step)
    db.session.commit()
    # 手工将开始时间回拨 2 小时，再流转到完成，验证自动工时 = 2h
    step.started_at = datetime.now() - timedelta(hours=2)
    step.status = 'in_progress'
    db.session.commit()
    token = get_csrf(client, '/production/orders/%d' % o.id)
    client.post('/production/steps/%d/status' % step.id,
                data={'csrf_token': token, 'status': 'completed'}, follow_redirects=True)
    db.session.expire_all()
    done = db.session.get(WorkOrderStep, step.id)
    assert done.status == 'completed'
    assert 1.9 <= done.labor_hours <= 2.1  # 允许细微时差


def test_step_labor_manual_correction(client):
    login(client, 'producer1', '123456')
    o = _order()
    o.status = 'in_progress'
    db.session.commit()
    step = WorkOrderStep(work_order_id=o.id, name='工时修正', seq=1,
                         status='completed', labor_hours=2.0)
    db.session.add(step)
    db.session.commit()
    token = get_csrf(client, '/production/orders/%d' % o.id)
    resp = client.post('/production/steps/%d/labor' % step.id, data={
        'csrf_token': token, 'labor_hours': '3.75', 'remark': '实际耗时',
    }, follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire_all()
    updated = db.session.get(WorkOrderStep, step.id)
    assert updated.labor_hours == 3.75 and updated.remark == '实际耗时'


def test_step_labor_rejects_negative(client):
    login(client, 'producer1', '123456')
    o = _order()
    o.status = 'in_progress'
    db.session.commit()
    step = WorkOrderStep(work_order_id=o.id, name='负工时', seq=1, labor_hours=1)
    db.session.add(step)
    db.session.commit()
    token = get_csrf(client, '/production/orders/%d' % o.id)
    client.post('/production/steps/%d/labor' % step.id, data={
        'csrf_token': token, 'labor_hours': '-1', 'remark': '',
    }, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(WorkOrderStep, step.id).labor_hours == 1


def test_order_detail_shows_total_hours(client):
    login(client, 'producer1', '123456')
    o = _order()
    for h in (1.5, 2.25):
        db.session.add(WorkOrderStep(work_order_id=o.id, name='合计工序', seq=1,
                                     labor_hours=h))
    db.session.commit()
    html = client.get('/production/orders/%d' % o.id).get_data(as_text=True)
    assert '3.75' in html  # 1.5 + 2.25


# ---------------- 领料余量与强校验 ----------------

def _ensure_inventory(qty=100):
    w = Warehouse.query.filter_by(is_active=True).first()
    m = Material.query.filter_by(is_active=True).first()
    row = Inventory.query.filter_by(warehouse_id=w.id, material_id=m.id).first()
    if row is None:
        row = Inventory(warehouse_id=w.id, material_id=m.id, quantity=0)
        db.session.add(row)
    row.quantity = qty
    db.session.commit()
    return w, m, row


def test_stock_api_returns_available(client):
    w, m, row = _ensure_inventory(66)
    login(client, 'keeper1', '123456')
    resp = client.get('/production/api/stock?warehouse_id=%d&material_id=%d' % (w.id, m.id))
    assert resp.status_code == 200
    assert resp.get_json()['available'] == 66


def test_issue_rejects_over_stock_without_mutation(client):
    w, m, row = _ensure_inventory(5)
    o = _order()
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % o.id)
    resp = client.post('/production/orders/%d/issue' % o.id, data={
        'csrf_token': token, 'warehouse_id': w.id, 'material_id': m.id,
        'quantity': 50, 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert '\u5e93\u5b58\u4e0d\u8db3'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(Inventory, row.id).quantity == 5  # 库存未变
    # 无出库单产生
    from app.models import StockDocument
    assert StockDocument.query.filter_by(related_order_id=o.id).count() == 0


def test_issue_succeeds_within_stock(client):
    w, m, row = _ensure_inventory(20)
    o = _order()
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % o.id)
    resp = client.post('/production/orders/%d/issue' % o.id, data={
        'csrf_token': token, 'warehouse_id': w.id, 'material_id': m.id,
        'quantity': 8, 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert '\u9886\u6599\u6210\u529f'.encode() in resp.data
    db.session.expire_all()
    assert db.session.get(Inventory, row.id).quantity == 12


# ---------------- 审批范围 ----------------

def test_production_has_no_approval_flow(client):
    """生产侧只有状态流转，不引入审批；人事请假审批保持。"""
    login(client, 'producer1', '123456')
    o = _order()
    html = client.get('/production/orders/%d' % o.id).get_data(as_text=True)
    assert '\u5ba1\u6279' not in html  # 工单详情无审批字样
    # 请假审批仍在
    login(client, 'leader1', '123456')
    assert client.get('/attendance/leave/approvals').status_code == 200
