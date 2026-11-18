# -*- coding: utf-8 -*-
"""生产工单状态机测试：非法流转被拒、合法链路、单号自增唯一、工序流转。"""
import pytest
from sqlalchemy.exc import IntegrityError

from conftest import get_csrf, login

from app import db
from app.models import User, WorkOrder, WorkOrderStep


def _producer():
    return User.query.filter_by(username='producer1').first()


_ORDER_SEQ = [0]


def _make_order(product='测试产品', status='pending', order_no=None):
    _ORDER_SEQ[0] += 1
    if order_no is None:
        order_no = 'WO20250109%03d' % _ORDER_SEQ[0]
    order = WorkOrder(order_no=order_no, product_name=product, quantity=5,
                      created_by=1, status=status)
    db.session.add(order)
    db.session.commit()
    return order


# ---------------- 创建与单号 ----------------

def test_create_order_via_route(client):
    login(client, 'producer1', '123456')
    leader = User.query.filter_by(username='leader1').first()
    token = get_csrf(client, '/production/orders/new')
    resp = client.post('/production/orders/new', data={
        'csrf_token': token, 'product_name': '路由创建产品', 'quantity': 8,
        'due_date': '2026-06-30', 'leader_id': leader.id, 'remark': ''},
        follow_redirects=True)
    assert resp.status_code == 200
    order = WorkOrder.query.filter_by(product_name='路由创建产品').first()
    assert order is not None
    assert order.order_no.startswith('WO')
    assert order.status == 'pending'
    assert order.leader_id == leader.id


def test_order_no_unique_constraint(app_ctx):
    """单号唯一约束：重复单号直接插入被数据库拒绝。"""
    _make_order('WO20250109001')
    dup = WorkOrder(order_no='WO20250109001', product_name='重复单号', quantity=1,
                    created_by=1)
    db.session.add(dup)
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()


def test_order_no_auto_increment(client):
    """同日连续生成单号不冲突（路由层通过查询找空位）。"""
    o1 = _make_order(order_no='WO20250109002')
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/new')
    client.post('/production/orders/new', data={
        'csrf_token': token, 'product_name': '单号递增产品', 'quantity': 1,
        'leader_id': 0, 'remark': ''}, follow_redirects=True)
    o2 = WorkOrder.query.filter_by(product_name='单号递增产品').first()
    assert o2 is not None and o2.order_no != o1.order_no


# ---------------- 工单状态机 ----------------

def test_invalid_transition_pending_to_completed_rejected(client):
    order = _make_order(status='pending')
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % order.id)
    resp = client.post('/production/orders/%d/status' % order.id,
                       data={'csrf_token': token, 'status': 'completed'},
                       follow_redirects=True)
    assert '非法的状态流转'.encode() in resp.data
    db.session.expire_all()
    assert WorkOrder.query.get(order.id).status == 'pending'


def test_invalid_transition_skip_accepted(client):
    order = _make_order(status='in_progress')
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % order.id)
    resp = client.post('/production/orders/%d/status' % order.id,
                       data={'csrf_token': token, 'status': 'accepted'},
                       follow_redirects=True)
    assert '非法的状态流转'.encode() in resp.data
    db.session.expire_all()
    assert WorkOrder.query.get(order.id).status == 'in_progress'


def test_full_valid_chain_then_terminal(client):
    """pending→in_progress→completed→accepted 全链路；accepted 后任何流转被拒。"""
    order = _make_order(status='pending')
    login(client, 'producer1', '123456')
    for target in ('in_progress', 'completed', 'accepted'):
        token = get_csrf(client, '/production/orders/%d' % order.id)
        resp = client.post('/production/orders/%d/status' % order.id,
                           data={'csrf_token': token, 'status': target},
                           follow_redirects=True)
        assert resp.status_code == 200
        db.session.expire_all()
        assert WorkOrder.query.get(order.id).status == target
    # 终态：无下一状态
    assert WorkOrder.query.get(order.id).next_status() is None
    token = get_csrf(client, '/production/orders/%d' % order.id)
    resp = client.post('/production/orders/%d/status' % order.id,
                       data={'csrf_token': token, 'status': 'pending'},
                       follow_redirects=True)
    assert '非法的状态流转'.encode() in resp.data
    db.session.expire_all()
    assert WorkOrder.query.get(order.id).status == 'accepted'


def test_invalid_status_value_rejected(client):
    order = _make_order(status='pending')
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % order.id)
    resp = client.post('/production/orders/%d/status' % order.id,
                       data={'csrf_token': token, 'status': 'hacked'},
                       follow_redirects=True)
    assert '非法的状态流转'.encode() in resp.data
    db.session.expire_all()
    assert WorkOrder.query.get(order.id).status == 'pending'


# ---------------- 工序状态机 ----------------

def _make_step(order, name='下料', seq=1, status='pending'):
    step = WorkOrderStep(work_order_id=order.id, name=name, seq=seq, status=status)
    db.session.add(step)
    db.session.commit()
    return step


def test_step_invalid_jump_rejected(client):
    order = _make_order(status='in_progress')
    step = _make_step(order)
    login(client, 'producer1', '123456')
    token = get_csrf(client, '/production/orders/%d' % order.id)
    resp = client.post('/production/steps/%d/status' % step.id,
                       data={'csrf_token': token, 'status': 'completed'},
                       follow_redirects=True)
    assert '非法的工序状态流转'.encode() in resp.data
    db.session.expire_all()
    assert WorkOrderStep.query.get(step.id).status == 'pending'


def test_step_valid_flow_sets_timestamps(client):
    order = _make_order(status='in_progress')
    step = _make_step(order)
    login(client, 'producer1', '123456')
    # pending → in_progress
    token = get_csrf(client, '/production/orders/%d' % order.id)
    client.post('/production/steps/%d/status' % step.id,
                data={'csrf_token': token, 'status': 'in_progress'},
                follow_redirects=True)
    db.session.expire_all()
    step = WorkOrderStep.query.get(step.id)
    assert step.status == 'in_progress' and step.started_at is not None
    # in_progress → completed
    token = get_csrf(client, '/production/orders/%d' % order.id)
    client.post('/production/steps/%d/status' % step.id,
                data={'csrf_token': token, 'status': 'completed'},
                follow_redirects=True)
    db.session.expire_all()
    step = WorkOrderStep.query.get(step.id)
    assert step.status == 'completed' and step.finished_at is not None


def test_step_delete_only_pending(client):
    order = _make_order()
    done = _make_step(order, name='已完成工序', seq=1, status='completed')
    todo = _make_step(order, name='待开始工序', seq=2)
    login(client, 'producer1', '123456')
    # 已完成工序不可删
    token = get_csrf(client, '/production/orders/%d' % order.id)
    client.post('/production/steps/%d/delete' % done.id,
                data={'csrf_token': token}, follow_redirects=True)
    assert WorkOrderStep.query.get(done.id) is not None
    # 待开始工序可删
    token = get_csrf(client, '/production/orders/%d' % order.id)
    client.post('/production/steps/%d/delete' % todo.id,
                data={'csrf_token': token}, follow_redirects=True)
    assert WorkOrderStep.query.get(todo.id).is_deleted is True


# ---------------- 看板 ----------------

def test_board_groups_by_status(client):
    _make_order('WO20250109001', status='pending')
    _make_order('WO20250109002', status='in_progress')
    _make_order('WO20250109003', status='completed')
    login(client, 'producer1', '123456')
    resp = client.get('/production/board')
    assert resp.status_code == 200
    for label in ['待开始', '进行中', '已完成', '已验收']:
        assert label.encode() in resp.data
