# -*- coding: utf-8 -*-
"""L1 轻量排产专项测试：倒排算法 / 服务集成 / 路由与展示 / 边界配置。

测试口径来自 docs/PRD-L1-Scheduling.md 与 docs/ARCHITECTURE-L1-Scheduling.md：
- 纯算法部分零 app context，直接 import 函数并显式注入 capacity/today；
- 服务集成用真实 ORM 模型，验证 duck typing 与 apply_plan 不 commit；
- 路由部分用 client 夹具走真实表单/权限/数据权限链路，断言精确到日期值与标记；
- 软删一律用 is_deleted 判断，不用 WorkOrder.query.get 区分。
"""
import re
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from conftest import get_csrf, login

from app import db
from app.models import Department, Process, Role, User, WorkOrder, WorkOrderStep
from app.services import scheduling_service as svc
from app.utils import time_utils

# 固定锚点：2025-01-10 是周五，便于精确验证跨周末回退
FRI = date(2025, 1, 10)
SAT = date(2025, 1, 11)
SUN = date(2025, 1, 12)
MON = date(2025, 1, 13)
TODAY = date(2025, 1, 15)  # 周三


# ====================================================================
# 一、纯算法（零 app context）
# ====================================================================

def test_workday_helpers():
    """工作日判定与严格/含当日前驱后继。"""
    assert time_utils.is_workday(FRI) is True
    assert time_utils.is_workday(SAT) is False
    assert time_utils.is_workday(SUN) is False
    assert time_utils.prev_workday(SAT) == FRI
    assert time_utils.prev_workday(FRI) == date(2025, 1, 9)
    assert time_utils.prev_workday_incl(SAT) == FRI
    assert time_utils.prev_workday_incl(FRI) == FRI
    assert time_utils.next_workday(FRI) == MON
    assert time_utils.next_workday(SAT) == MON


def test_workdays_between_closed_interval_and_sign():
    """闭区间工作日计数，a>b 返回负值且对称。"""
    assert time_utils.workdays_between(FRI, MON) == 2       # 周五 + 周一
    assert time_utils.workdays_between(SAT, SUN) == 0
    assert time_utils.workdays_between(SUN, FRI) == -1
    assert time_utils.workdays_between(FRI, FRI) == 1
    assert time_utils.workdays_between(SUN, SUN) == 0


@pytest.mark.parametrize('a,b,expected', [
    (FRI, FRI, 0),
    (date(2025, 1, 6), date(2025, 1, 8), 2),
    (date(2025, 1, 8), date(2025, 1, 6), -2),
    (FRI, date(2025, 1, 17), 5),          # 跨周：5 个工作日
    (SUN, MON, 1),                        # a 为周日：锚定到周五后再算
    (SUN, FRI, 0),
])
def test_workday_diff(a, b, expected):
    """工作日差：同日 0、正负方向、周末锚定、跨周。"""
    assert time_utils.workday_diff(a, b) == expected


@pytest.mark.parametrize('hours,days,expected_start', [
    (8, 1, FRI),
    (16, 2, date(2025, 1, 9)),
    (40, 5, date(2025, 1, 6)),
    (80, 10, date(2024, 12, 30)),
])
def test_calculate_plan_durations(hours, days, expected_start):
    """D=1/2/5/10 的起止日精确匹配，开工日必为工作日。"""
    start, end = svc.calculate_plan(FRI, hours, capacity=8)
    assert (start, end) == (expected_start, FRI)
    assert time_utils.is_workday(start)
    assert (FRI - expected_start).days >= days - 1  # 至少跨 days-1 个自然日回退


def test_calculate_plan_crosses_weekend():
    """交期为周一时，2 天工期开工日回退到上周五。"""
    assert svc.calculate_plan(MON, 16, capacity=8) == (FRI, MON)


@pytest.mark.parametrize('due,expected_start', [
    (SAT, FRI),
    (SUN, FRI),
])
def test_calculate_plan_due_on_weekend_keeps_end(due, expected_start):
    """交期落周末：end 保留周末原值，start 回退到最近工作日。"""
    assert svc.calculate_plan(due, 8, capacity=8) == (expected_start, due)
    assert svc.calculate_plan(due, 16, capacity=8) == (date(2025, 1, 9), due)


@pytest.mark.parametrize('due,hours', [
    (FRI, 0),
    (FRI, None),
    (FRI, -1),
    (None, 16),
])
def test_calculate_plan_unavailable(due, hours):
    """无交期 / 工时为空或非正 → (None, None)，不伪造 1 天。"""
    assert svc.calculate_plan(due, hours, capacity=8) == (None, None)


@pytest.mark.parametrize('capacity', [0, -1, -0.01])
def test_calculate_plan_rejects_nonpositive_capacity(capacity):
    """配置错误必须显式抛错，不静默吞掉。"""
    with pytest.raises(ValueError, match='DAILY_CAPACITY_HOURS'):
        svc.calculate_plan(FRI, 8, capacity=capacity)


@pytest.mark.parametrize('hours,expected_start', [
    (8, FRI),                        # 恰好整除：D=1
    (8.01, date(2025, 1, 9)),        # 多 0.01h：D=2
    (16, date(2025, 1, 9)),
    (16.01, date(2025, 1, 8)),       # 多 0.01h：D=3
])
def test_calculate_plan_ceil_boundary(hours, expected_start):
    """ceil 边界：恰好整除不多算，多 0.01h 天数 +1。"""
    assert svc.calculate_plan(FRI, hours, capacity=8)[0] == expected_start


def test_calculate_plan_explicit_capacity_overrides_default():
    """显式 capacity 覆盖全局默认：16h 分别得到 D=1/2/4。"""
    assert svc.calculate_plan(FRI, 16, capacity=16)[0] == FRI
    assert svc.calculate_plan(FRI, 16, capacity=8)[0] == date(2025, 1, 9)
    assert svc.calculate_plan(FRI, 16, capacity=4)[0] == date(2025, 1, 7)


def _fake_step(hours=None, deleted=False, process_deleted=False, labor_hours=999):
    """duck typing 假工序行：可模拟无工序/软删工序/空工时。"""
    process = None
    if hours is not None:
        process = SimpleNamespace(standard_hours=hours, is_deleted=process_deleted)
    return SimpleNamespace(is_deleted=deleted, process=process, labor_hours=labor_hours)


def test_sum_standard_hours_duck_typing_and_rounding():
    """Σ×quantity、孤立/软删/空工时按 0、非数字工时忽略、结果保留 2 位。"""
    order = SimpleNamespace(quantity=3, steps=[
        _fake_step(1.5),
        _fake_step(2.0),
        _fake_step(None),                        # process=None 孤立行
        _fake_step(100, deleted=True),           # 已删除工序行
        _fake_step(100, process_deleted=True),   # 工序档案已软删
        _fake_step(None),                        # standard_hours 为空
        _fake_step('abc'),                       # 非法工时按 0
    ])
    assert svc.sum_standard_hours(order) == 10.5  # (1.5+2.0) × 3

    rounded = SimpleNamespace(quantity=1, steps=[_fake_step(0.1), _fake_step(0.2)])
    assert svc.sum_standard_hours(rounded) == 0.3  # 浮点毛刺被 round(2) 抹平
    assert svc.sum_standard_hours(SimpleNamespace(quantity=2, steps=[])) == 0.0
    assert svc.sum_standard_hours(SimpleNamespace(quantity=2)) == 0.0
    # labor_hours 是完工实耗，不能作为计划输入
    assert svc.sum_standard_hours(SimpleNamespace(quantity=1, steps=[_fake_step(1.0)])) == 1.0
    # quantity 为空按 1 计
    assert svc.sum_standard_hours(SimpleNamespace(quantity=None,
                                                  steps=[_fake_step(1.5)])) == 1.5


def _fake_order(status='pending', due=FRI, start=date(2025, 1, 9), manual=False,
                priority='normal'):
    return SimpleNamespace(status=status, due_date=due, plan_start_date=start,
                           plan_end_date=due, plan_manual=manual, priority=priority)


def test_overdue_priority_over_warning():
    """交期已过：已超期优先展示，不再标开工预警；天数仍按工作日差给出。"""
    order = _fake_order(due=date(2025, 1, 14), start=date(2025, 1, 13))
    assert svc.is_overdue(order, TODAY) is True
    assert svc.is_start_warning(order, TODAY) is False
    status = svc.plan_status(order, TODAY)
    assert status['overdue'] is True
    assert status['warning'] is False
    assert status['label'] == '已超期'
    assert status['days'] == -2  # 最晚开工日已过 2 个工作日


@pytest.mark.parametrize('start,due,expected_label', [
    (TODAY, date(2025, 1, 17), '开工预警'),   # 今天最晚开工
    (date(2025, 1, 13), date(2025, 1, 17), '开工预警'),  # 开工日已过，交期未过
    (date(2025, 1, 17), date(2025, 1, 20), ''),          # 尚未到开工日
])
def test_warning_and_future_status(start, due, expected_label):
    """开工预警 / 正常两种状态的标签与天数。"""
    order = _fake_order(due=due, start=start)
    assert svc.is_overdue(order, TODAY) is False
    assert svc.is_start_warning(order, TODAY) == (expected_label == '开工预警')
    status = svc.plan_status(order, TODAY)
    assert status['label'] == expected_label
    assert status['days'] == time_utils.workday_diff(TODAY, start)
    assert status['manual'] is False and status['priority'] == 'normal'


@pytest.mark.parametrize('terminal', ['completed', 'accepted'])
def test_terminal_status_never_flags(terminal):
    """终态（已完成/已验收）一律不标红、不预警、空标签。"""
    order = _fake_order(status=terminal, due=date(2025, 1, 10), start=date(2025, 1, 8))
    assert svc.is_overdue(order, TODAY) is False
    assert svc.is_start_warning(order, TODAY) is False
    status = svc.plan_status(order, TODAY)
    assert status['overdue'] is False and status['warning'] is False
    assert status['label'] == ''
    assert status['days'] == -5  # 保留快照供追溯，仍按工作日差计算


def test_none_dates_are_safe():
    """无交期/无计划开工日不报错，剩余天数为 None。"""
    order = _fake_order(due=None, start=None)
    assert svc.is_overdue(order, TODAY) is False
    assert svc.is_start_warning(order, TODAY) is False
    assert svc.days_remaining(order, TODAY) is None
    status = svc.plan_status(order, TODAY)
    assert status['days'] is None and status['label'] == ''
    assert svc.plan_status(_fake_order(manual=True, priority='high'),
                           TODAY)['manual'] is True


# ====================================================================
# 二、服务集成（真实模型，app context）
# ====================================================================

def _process(code, hours):
    p = Process(code=code, name='L1-' + code, standard_hours=hours)
    db.session.add(p)
    db.session.commit()
    return p


def _order(order_no, quantity=1, due=None, status='pending', department=None, leader=None):
    admin = User.query.filter_by(username='admin').first()
    o = WorkOrder(order_no=order_no, product_name='L1集成测试品', quantity=quantity,
                  due_date=due, status=status, created_by=admin.id,
                  leader_id=leader.id if leader else None,
                  related_department_id=department.id if department else None)
    db.session.add(o)
    db.session.commit()
    return o


def _step(order, process=None, seq=1, name='L1工序'):
    s = WorkOrderStep(work_order_id=order.id, process_id=process.id if process else None,
                      name=name, seq=seq, labor_hours=999)  # 实耗工时不得参与计算
    db.session.add(s)
    db.session.commit()
    return s


def test_service_sum_and_apply_with_real_models(app_ctx):
    """真实 Process/WorkOrderStep：Σ×quantity 正确；改数量后开工日按公式前移。"""
    p1, p2 = _process('L1S1', 1.5), _process('L1S2', 2.0)
    o = _order('L1-SVC-001', quantity=3, due=FRI)
    _step(o, p1, 1)
    _step(o, p2, 2)
    _step(o, None, 3, '孤立历史工序')
    deleted = _step(o, _process('L1S0', 100.0), 4)
    deleted.is_deleted = True
    db.session.commit()
    db.session.expire_all()

    assert svc.sum_standard_hours(o) == 10.5  # (1.5+2.0)×3，孤立/软删/实耗不计
    assert svc.apply_plan(o) == 'auto'
    assert (o.plan_start_date, o.plan_end_date) == (date(2025, 1, 9), FRI)
    assert o.plan_manual is False

    o.quantity = 5  # 17.5h → D=3
    assert svc.apply_plan(o) == 'auto'
    assert (o.plan_start_date, o.plan_end_date) == (date(2025, 1, 8), FRI)


def test_service_apply_manual_vs_auto(app_ctx):
    """人工模式原样写入并置标记；自动模式按公式刷新并清标记。"""
    p = _process('L1M1', 2.0)
    manual_order = _order('L1-SVC-002', quantity=1, due=FRI)
    _step(manual_order, p)
    assert svc.apply_plan(manual_order, date(2025, 1, 2), date(2025, 1, 3)) == 'manual'
    assert (manual_order.plan_start_date, manual_order.plan_end_date) == (
        date(2025, 1, 2), date(2025, 1, 3))
    assert manual_order.plan_manual is True

    auto_order = _order('L1-SVC-003', quantity=1, due=FRI)
    _step(auto_order, p)
    assert svc.apply_plan(auto_order) == 'auto'
    assert (auto_order.plan_start_date, auto_order.plan_end_date) == (FRI, FRI)
    assert auto_order.plan_manual is False


@pytest.mark.parametrize('with_step,process_hours', [
    (False, None),
    (True, None),      # 孤立 process_id
    (True, 0.0),       # 参考工时为 0
])
def test_service_apply_unavailable(app_ctx, with_step, process_hours):
    """无工序 / 孤立工序 / 零工时：unavailable 且字段置空。"""
    o = _order('L1-SVC-U%s%s' % (with_step, process_hours), quantity=2, due=FRI)
    o.plan_start_date, o.plan_end_date, o.plan_manual = FRI, FRI, True
    if with_step:
        process = _process('L1U%s' % process_hours, process_hours) \
            if process_hours is not None else None
        _step(o, process)
    assert svc.apply_plan(o) == 'unavailable'
    assert (o.plan_start_date, o.plan_end_date) == (None, None)
    assert o.plan_manual is False


def test_apply_plan_does_not_commit(app_ctx, monkeypatch):
    """apply_plan 只写字段，不自行 commit（事务由调用方统一提交）。"""
    p = _process('L1NC', 2.0)
    o = _order('L1-SVC-004', quantity=1, due=FRI)
    _step(o, p)

    def _forbidden_commit(*args, **kwargs):
        raise AssertionError('apply_plan 不应调用 db.session.commit()')

    monkeypatch.setattr(db.session, 'commit', _forbidden_commit)
    assert svc.apply_plan(o) == 'auto'
    assert o.plan_start_date == FRI


# ====================================================================
# 三、路由 / 端到端
# ====================================================================

def _order_payload(product='L1表单工单', quantity=5, due='2025-01-10', priority='normal',
                   start='', end='', leader='0', department='0'):
    return {
        'product_name': product, 'quantity': str(quantity), 'due_date': due,
        'priority': priority, 'plan_start_date': start, 'plan_end_date': end,
        'leader_id': leader, 'related_department_id': department, 'remark': '',
    }


def _create_order_via_form(client, **kwargs):
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new',
                       data=dict(_order_payload(**kwargs), csrf_token=token),
                       follow_redirects=True)
    assert resp.status_code == 200
    order = WorkOrder.query.order_by(WorkOrder.id.desc()).first()
    db.session.expire_all()
    return order


def _add_step_via_form(client, order, code='OP02', seq=1):
    login(client, 'producer1', '123456')
    process = Process.query.filter_by(code=code).first()
    # CSRF 从新单页取：详情/列表 GET 会渲染 order.steps，在本测试共享的会话里
    # 造成关系缓存；expire_all 让被测路由像真实新请求一样重新加载关系
    token = get_csrf(client, '/production/orders/new')
    db.session.expire_all()
    resp = client.post('/production/orders/%d/steps/new' % order.id, data={
        'csrf_token': token, 'process_id': str(process.id), 'seq': str(seq),
        'operator_id': '0', 'remark': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire_all()
    return process


def _edit_order_via_form(client, order, **kwargs):
    login(client, 'producer1', '123456')
    # 测试辅助层的 start/end 别名对应表单的 plan_start_date / plan_end_date
    if 'start' in kwargs:
        kwargs['plan_start_date'] = kwargs.pop('start')
    if 'end' in kwargs:
        kwargs['plan_end_date'] = kwargs.pop('end')
    payload = _order_payload(product=order.product_name, quantity=order.quantity,
                             due=order.due_date.isoformat() if order.due_date else '',
                             priority=order.priority)
    payload.update(kwargs)
    token = get_csrf(client, '/production/orders/new')
    db.session.expire_all()
    resp = client.post('/production/orders/%d/edit' % order.id,
                       data=dict(payload, csrf_token=token), follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire_all()
    return resp


def _recalculate(client, order_id, csrf=True, follow=False):
    # 新单页必有 CSRF 表单；即使当前用户数据权限内无工单也可取到 token
    data = {'csrf_token': get_csrf(client, '/production/orders/new')} if csrf else {}
    return client.post('/production/orders/%d/plan/recalculate' % order_id,
                       data=data, follow_redirects=follow)


def test_new_order_then_step_writes_auto_plan(client):
    """新建时无工序→留空；通过 step_new 加 OP02(2h)×5=10h→D=2，日期精确落工作日。"""
    order = _create_order_via_form(client, quantity=5, due='2025-01-10')
    assert (order.plan_start_date, order.plan_end_date) == (None, None)
    assert order.plan_manual is False
    assert '未维护工序参考工时或无交期，计划日期留空'.encode() in client.get(
        '/production/orders/%d' % order.id).data

    _add_step_via_form(client, order, code='OP02')
    db.session.expire_all()
    assert order.plan_end_date == FRI
    assert order.plan_start_date == date(2025, 1, 9)
    assert time_utils.is_workday(order.plan_start_date)
    assert order.plan_manual is False
    detail = client.get('/production/orders/%d' % order.id).get_data(as_text=True)
    assert '计划来源：按交期自动倒排' in detail


def test_manual_override_preserved_then_cleared_by_blank(client):
    """人工日期写入→再次编辑按表单回填不改写→清空两日期解除覆盖回自动。"""
    order = _create_order_via_form(client, quantity=5, due='2025-01-10')
    _add_step_via_form(client, order, code='OP02')

    resp = _edit_order_via_form(client, order, start='2025-01-06', end='2025-01-07')
    assert '已保存人工计划日期'.encode() in resp.data
    assert order.plan_manual is True
    assert (order.plan_start_date, order.plan_end_date) == (
        date(2025, 1, 6), date(2025, 1, 7))
    # 人工工单编辑页回填原值（自动工单才显示只读占位）
    login(client, 'producer1', '123456')
    edit_html = client.get('/production/orders/%d/edit' % order.id).get_data(as_text=True)
    assert 'value="2025-01-06"' in edit_html and 'value="2025-01-07"' in edit_html

    # 再次编辑（表单回填的人工日期原样提交）并改数量：人工值不被改写
    _edit_order_via_form(client, order, quantity=10, start='2025-01-06', end='2025-01-07')
    assert order.quantity == 10
    assert (order.plan_start_date, order.plan_end_date) == (
        date(2025, 1, 6), date(2025, 1, 7))
    assert order.plan_manual is True
    detail = client.get('/production/orders/%d' % order.id).get_data(as_text=True)
    assert '人工指定（重新倒排可解除）' in detail and '人工' in detail

    # 清空两个日期 → 回到自动：20h / 8h = D=3
    _edit_order_via_form(client, order, start='', end='')
    assert order.plan_manual is False
    assert (order.plan_start_date, order.plan_end_date) == (date(2025, 1, 8), FRI)


def test_partial_manual_dates_rejected(client):
    """只填一个计划日期 → 校验失败并中止保存，原子段保持原值。"""
    order = _create_order_via_form(client, quantity=5, due='2025-01-10')
    _add_step_via_form(client, order, code='OP02')
    resp = _edit_order_via_form(client, order, start='2025-01-06', end='')
    assert '必须同时填写'.encode() in resp.data
    assert (order.plan_start_date, order.plan_end_date) == (date(2025, 1, 9), FRI)
    assert order.plan_manual is False


def test_step_new_recalculates_auto_plan(client):
    """自动工单加第二道工序后，总工时 7.5→17.5h，开工日 01-10→01-08。"""
    order = _create_order_via_form(client, quantity=5, due='2025-01-10')
    _add_step_via_form(client, order, code='OP03', seq=1)  # 1.5h×5=7.5h → D=1
    assert order.plan_start_date == FRI
    _add_step_via_form(client, order, code='OP02', seq=2)  # +2h×5=10h → 17.5h → D=3
    db.session.expire_all()
    assert (order.plan_start_date, order.plan_end_date) == (date(2025, 1, 8), FRI)
    assert order.plan_manual is False


def test_step_changes_respect_manual_plan(client):
    """人工覆盖工单在 step_new / step_delete 后都不改写计划日期。"""
    order = _create_order_via_form(client, quantity=5, due='2025-01-10')
    _add_step_via_form(client, order, code='OP03', seq=1)
    _edit_order_via_form(client, order, start='2025-01-02', end='2025-01-03')

    _add_step_via_form(client, order, code='OP02', seq=2)
    db.session.expire_all()
    assert (order.plan_start_date, order.plan_end_date) == (
        date(2025, 1, 2), date(2025, 1, 3))
    assert order.plan_manual is True

    op2 = Process.query.filter_by(code='OP02').first()
    step = WorkOrderStep.query.filter_by(work_order_id=order.id, process_id=op2.id).first()
    assert step is not None and step.is_deleted is False
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/new')
    db.session.expire_all()
    client.post('/production/steps/%d/delete' % step.id,
                data={'csrf_token': token}, follow_redirects=True)
    db.session.expire_all()
    assert step.is_deleted is True
    assert (order.plan_start_date, order.plan_end_date) == (
        date(2025, 1, 2), date(2025, 1, 3))


def test_step_delete_recalculates_auto_plan(client):
    """仅 pending 工序可删：删除 OP02 后 17.5h→7.5h，开工日 01-08→01-10。"""
    order = _create_order_via_form(client, quantity=5, due='2025-01-10')
    _add_step_via_form(client, order, code='OP03', seq=1)
    _add_step_via_form(client, order, code='OP02', seq=2)
    db.session.expire_all()
    assert order.plan_start_date == date(2025, 1, 8)

    op2 = Process.query.filter_by(code='OP02').first()
    step = WorkOrderStep.query.filter_by(work_order_id=order.id, process_id=op2.id).first()
    assert step.status == 'pending'
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/new')
    db.session.expire_all()
    resp = client.post('/production/steps/%d/delete' % step.id,
                       data={'csrf_token': token}, follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire_all()
    assert step.is_deleted is True
    assert (order.plan_start_date, order.plan_end_date) == (FRI, FRI)
    assert order.plan_manual is False


def test_recalculate_clears_manual_and_refreshes(client):
    """重新倒排：清除人工标记，按当前数量/工时刷新；审计日志留痕。"""
    from app.models import OperationLog

    order = _create_order_via_form(client, quantity=5, due='2025-01-10')
    _add_step_via_form(client, order, code='OP02')
    _edit_order_via_form(client, order, start='2025-01-01', end='2025-01-02')
    _edit_order_via_form(client, order, quantity=10)  # 人工日期保持

    login(client, 'producer1', '123456')
    resp = _recalculate(client, order.id, follow=True)
    assert resp.status_code == 200
    assert '已重新倒排'.encode() in resp.data
    db.session.expire_all()
    assert order.plan_manual is False
    assert (order.plan_start_date, order.plan_end_date) == (date(2025, 1, 8), FRI)
    assert OperationLog.query.filter_by(target_type='work_order', target_id=order.id,
                                        action='update').count() >= 3


def test_recalculate_cross_department_order_404(client):
    """仓储部主管 post 生产部工单：base_order_query 收窄 → 404 且日期不变。"""
    prod_dept = Department.query.filter_by(name='生产部').first()
    wh_dept = Department.query.filter_by(name='仓储部').first()
    leader_role = Role.query.filter_by(code='leader').first()
    outsider = User(username='leader_wh', employee_no='EMP9911', name='仓储主管',
                    department_id=wh_dept.id, hire_date=time_utils.today())
    outsider.set_password('123456')
    outsider.roles.append(leader_role)
    db.session.add(outsider)
    db.session.flush()
    wh_dept.leader_id = outsider.id
    db.session.commit()

    producer = User.query.filter_by(username='producer1').first()
    order = _order('L1-SCOPE-404', quantity=5, due=FRI, department=prod_dept,
                   leader=producer)
    _step(order, _process('L1SCOPE', 2.0))
    assert svc.apply_plan(order) == 'auto'
    before = (order.plan_start_date, order.plan_end_date, order.plan_manual)

    login(client, 'leader_wh', '123456')
    assert client.get('/production/orders').status_code == 200
    assert _recalculate(client, order.id).status_code == 404
    db.session.expire_all()
    assert (order.plan_start_date, order.plan_end_date, order.plan_manual) == before

    # 对照组：超管不受数据权限收窄，同一路由可成功
    login(client, 'admin', 'admin123')
    assert _recalculate(client, order.id).status_code == 302


def test_recalculate_requires_manage_permission_403(client):
    """staff1 无 production.manage：即使持合法 CSRF 也 403。"""
    order = WorkOrder.query.filter_by(order_no='WO20250101001').first()
    login(client, 'staff1', '123456')
    token = get_csrf(client, '/attendance/clock')
    resp = client.post('/production/orders/%d/plan/recalculate' % order.id,
                       data={'csrf_token': token})
    assert resp.status_code == 403


def test_recalculate_requires_csrf_token_400(client):
    """全局 CSRFProtect：不带 token 的 POST 被 400 拒绝且日期不变。"""
    order = WorkOrder.query.filter_by(order_no='WO20250101001').first()
    login(client, 'producer1', '123456')
    resp = _recalculate(client, order.id, csrf=False)
    assert resp.status_code == 400
    assert (order.plan_start_date, order.plan_end_date) == (None, None)


def test_recalculate_rejects_terminal_order(client):
    """已完结工单拒绝重算：flash 提示，人工日期快照保持不变。"""
    order = _order('L1-TERMINAL', quantity=5, due=FRI, status='accepted')
    _step(order, _process('L1TERM', 2.0))
    order.plan_start_date = date(2025, 1, 2)
    order.plan_end_date = date(2025, 1, 3)
    order.plan_manual = True
    db.session.commit()

    login(client, 'producer1', '123456')
    resp = _recalculate(client, order.id, follow=True)
    assert resp.status_code == 200
    assert '已完结工单不参与重新倒排'.encode() in resp.data
    db.session.expire_all()
    assert (order.plan_start_date, order.plan_end_date) == (
        date(2025, 1, 2), date(2025, 1, 3))
    assert order.plan_manual is True


# ====================================================================
# 四、展示 / 边界 / 配置
# ====================================================================

def _display_orders():
    """构造超期 / 开工预警 / 未来三种展示状态（today 动态注入）。"""
    today = time_utils.today()
    overdue = _order('L1-DISP-OVER', quantity=1, due=today - timedelta(days=3))
    overdue.plan_start_date, overdue.plan_end_date = today - timedelta(days=5), \
        today - timedelta(days=3)
    warning = _order('L1-DISP-WARN', quantity=1, due=today + timedelta(days=5))
    warning.plan_start_date, warning.plan_end_date = today, today + timedelta(days=5)
    warning.plan_manual = True
    warning.priority = 'high'
    future = _order('L1-DISP-FUT', quantity=1, due=today + timedelta(days=12))
    future.plan_start_date, future.plan_end_date = today + timedelta(days=7), \
        today + timedelta(days=12)
    terminal = _order('L1-DISP-TERM', quantity=1, due=today - timedelta(days=3),
                      status='completed')
    terminal.plan_start_date, terminal.plan_end_date = today - timedelta(days=5), \
        today - timedelta(days=3)
    db.session.commit()
    return today, overdue, warning, future, terminal


def _block_containing(html, needle, separator):
    """按 <tr / border 卡片分段，定位包含单号的 HTML 片段。"""
    for block in re.split(separator, html)[1:]:
        if needle in block:
            return block
    pytest.fail('页面未找到目标记录: %s' % needle)


def test_order_list_displays_plan_columns_and_warnings(client):
    """列表列头、三种剩余天数文案、超期行标红与优先级/人工标记。"""
    today, overdue, warning, future, terminal = _display_orders()
    login(client, 'admin', 'admin123')
    html = client.get('/production/orders').get_data(as_text=True)
    assert '计划开工日' in html and '倒排剩余天数' in html

    over_row = _block_containing(html, overdue.order_no, r'<tr\b')
    assert 'table-danger' in over_row and '已超期' in over_row
    assert ('已过 %d 个工作日' % -svc.days_remaining(overdue, today)) in over_row

    warn_row = _block_containing(html, warning.order_no, r'<tr\b')
    assert 'table-danger' not in warn_row and '开工预警' in warn_row
    assert '今天最晚开工' in warn_row and '人工' in warn_row and '高' in warn_row

    fut_row = _block_containing(html, future.order_no, r'<tr\b')
    assert 'table-danger' not in fut_row
    assert ('还剩 %d 个工作日' % svc.days_remaining(future, today)) in fut_row

    term_row = _block_containing(html, terminal.order_no, r'<tr\b')
    assert 'table-danger' not in term_row and '已超期' not in term_row
    assert ('已过 %d 个工作日' % -svc.days_remaining(terminal, today)) in term_row


def test_board_displays_plan_hints_and_danger_border(client):
    """看板卡片同口径：超期/预警边框标红、剩余天数文案、人工标记。"""
    today, overdue, warning, future, _terminal = _display_orders()
    login(client, 'admin', 'admin123')
    html = client.get('/production/board').get_data(as_text=True)
    sep = r'<div class="border rounded'

    over_card = _block_containing(html, overdue.order_no, sep)
    assert 'border-danger' in over_card and '已超期' in over_card
    assert ('已过 %d 个工作日' % -svc.days_remaining(overdue, today)) in over_card

    warn_card = _block_containing(html, warning.order_no, sep)
    assert 'border-danger' in warn_card and '开工预警' in warn_card
    assert '今天最晚开工' in warn_card and '人工' in warn_card

    fut_card = _block_containing(html, future.order_no, sep)
    assert 'border-danger' not in fut_card
    assert ('还剩 %d 个工作日' % svc.days_remaining(future, today)) in fut_card


def test_no_due_date_and_zero_hours_are_unavailable(client):
    """无交期 / 零工时：计划字段留空、不误标红、详情给出可读提示。"""
    zero = _process('L1ZERO', 0.0)
    no_due = _order('L1-NO-DUE', quantity=2, due=None)
    _step(no_due, zero)
    assert svc.apply_plan(no_due) == 'unavailable'
    zero_hours = _order('L1-ZERO-H', quantity=2, due=time_utils.today() + timedelta(days=10))
    _step(zero_hours, zero)
    assert svc.apply_plan(zero_hours) == 'unavailable'
    db.session.commit()

    login(client, 'admin', 'admin123')
    no_due_html = client.get('/production/orders/%d' % no_due.id).get_data(as_text=True)
    zero_html = client.get('/production/orders/%d' % zero_hours.id).get_data(as_text=True)
    assert '未填写交期，无法倒排' in no_due_html
    assert '未维护工序参考工时，无法倒排' in zero_html
    assert svc.plan_status(no_due)['days'] is None
    assert svc.plan_status(zero_hours)['label'] == ''

    list_html = client.get('/production/orders').get_data(as_text=True)
    for order in (no_due, zero_hours):
        row = _block_containing(list_html, order.order_no, r'<tr\b')
        assert 'table-danger' not in row and '已超期' not in row
        assert '倒排剩余天数' in list_html


def test_daily_capacity_config_change_affects_plan(app_ctx, monkeypatch):
    """config 中 DAILY_CAPACITY_HOURS 改为 4/20 时，同一工单倒排结果随之变化。"""
    from config import Config

    assert Config.DAILY_CAPACITY_HOURS == 8.0
    assert app_ctx.config['DAILY_CAPACITY_HOURS'] == 8.0
    p = _process('L1CAP', 2.0)
    o = _order('L1-CAP-001', quantity=5, due=FRI)  # 10h
    _step(o, p)
    assert svc.apply_plan(o) == 'auto' and o.plan_start_date == date(2025, 1, 9)

    monkeypatch.setitem(app_ctx.config, 'DAILY_CAPACITY_HOURS', 4.0)
    assert svc.calculate_plan(FRI, 10) == (date(2025, 1, 8), FRI)  # D=3
    assert svc.apply_plan(o) == 'auto' and o.plan_start_date == date(2025, 1, 8)

    monkeypatch.setitem(app_ctx.config, 'DAILY_CAPACITY_HOURS', 20.0)
    assert svc.apply_plan(o) == 'auto' and (o.plan_start_date, o.plan_end_date) == (FRI, FRI)


def test_legacy_order_defaults(app_ctx):
    """迁移后的历史行口径：priority=normal、plan_manual=False、日期 NULL。"""
    row = db.session.execute(db.text(
        "SELECT priority, plan_manual, plan_start_date, plan_end_date "
        "FROM work_orders WHERE order_no='WO20250101001'")).fetchone()
    assert row is not None
    assert row.priority == 'normal'
    assert bool(row.plan_manual) is False
    assert row.plan_start_date is None and row.plan_end_date is None
