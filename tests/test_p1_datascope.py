# -*- coding: utf-8 -*-
"""P1-04 部门数据权限测试：leader 本部门+子部门、superadmin 全量、篡改参数静默收窄。"""
from conftest import login

from app import db
from app.models import Department, User, WorkOrder
from app.utils.data_scope import is_scoped_leader, visible_department_ids


def _leader():
    return User.query.filter_by(username='leader1').first()


def _admin():
    return User.query.filter_by(username='admin').first()


def _staff():
    return User.query.filter_by(username='staff1').first()


def test_visible_dept_ids_leader_includes_children(app_ctx):
    """leader 可见部门 = 本部门 + 全部子孙（A5）。"""
    leader = _leader()
    prod = Department.query.filter_by(name='生产部').first()
    child = Department(name='装配二车间', parent_id=prod.id, sort_order=1)
    db.session.add(child)
    db.session.commit()
    with app_ctx.test_request_context('/'):
        ids = visible_department_ids(leader)
    assert prod.id in ids and child.id in ids


def test_visible_dept_ids_superadmin_none(app_ctx):
    """superadmin 返回 None（完全豁免）。"""
    with app_ctx.test_request_context('/'):
        assert visible_department_ids(_admin()) is None


def test_visible_dept_ids_staff_none(app_ctx):
    """普通员工（非 leader）返回 None（维持 P0，不因缺 view_all 而越权）。"""
    with app_ctx.test_request_context('/'):
        assert visible_department_ids(_staff()) is None


def test_is_scoped_leader(app_ctx):
    """只有 leader 角色且为部门负责人者为 scoped leader。"""
    assert is_scoped_leader(_leader()) is True
    assert is_scoped_leader(_admin()) is False
    assert is_scoped_leader(_staff()) is False


def test_employee_list_scoped_for_leader(client):
    """leader 访问人员列表只见本部门员工，不含仓储部 keeper1。"""
    login(client, 'leader1', '123456')
    resp = client.get('/hr/employees')
    assert resp.status_code == 200
    assert '王仓管'.encode() not in resp.data  # keeper1 属仓储部


def test_employee_list_tampered_dept_scoped(client):
    """leader 篡改 dept_id 到仓储部 → 静默收窄，不返回仓储部员工。"""
    login(client, 'leader1', '123456')
    wh_dept = Department.query.filter_by(name='仓储部').first()
    resp = client.get('/hr/employees?dept_id=%d' % wh_dept.id)
    assert resp.status_code == 200
    assert '王仓管'.encode() not in resp.data


def test_superadmin_sees_all_employees(client):
    """superadmin 全量：能看到仓储部 keeper1。"""
    login(client, 'admin', 'admin123')
    resp = client.get('/hr/employees')
    assert '王仓管'.encode() in resp.data


def test_order_list_scoped_by_department(client):
    """leader 工单列表：仅见归属本部门或负责人属本部门的工单。"""
    wh_dept = Department.query.filter_by(name='仓储部').first()
    outsider = WorkOrder(order_no='WO-SCOPE-001', product_name='越权工单', quantity=1,
                         related_department_id=wh_dept.id, created_by=1)
    db.session.add(outsider)
    db.session.commit()
    login(client, 'leader1', '123456')
    resp = client.get('/production/orders')
    assert resp.status_code == 200
    assert '越权工单'.encode() not in resp.data


def test_order_list_superadmin_sees_all(client):
    """superadmin 可见全部工单。"""
    outsider = WorkOrder(order_no='WO-SCOPE-002', product_name='全局工单', quantity=1,
                         created_by=1)
    db.session.add(outsider)
    db.session.commit()
    login(client, 'admin', 'admin123')
    resp = client.get('/production/orders')
    assert '全局工单'.encode() in resp.data
