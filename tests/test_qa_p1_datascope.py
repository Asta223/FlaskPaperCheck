# -*- coding: utf-8 -*-
"""QA 独立验证：P1-04 部门数据权限隔离（不复用工程师用例）。

覆盖：递归子部门、篡改 dept_id/user_id 静默收窄、superadmin 全量、
工单归属 coalesce(related_department_id, 负责人部门)、跨部门审批 403。
"""
from datetime import datetime

from conftest import login

from app import db
from app.models import AttendanceRecord, Department, LeaveRequest, Role, User, WorkOrder
from app.utils.time_utils import now


def _make_user(username, name, dept_id, role_code):
    """创建带单一内置角色的测试员工。"""
    user = User(username=username, employee_no='QA-' + username, name=name,
                department_id=dept_id, hire_date=now().date())
    user.set_password('123456')
    role = Role.query.filter_by(code=role_code).first()
    if role:
        user.roles.append(role)
    db.session.add(user)
    db.session.commit()
    return user


def _dept(name, parent_id=None):
    dept = Department(name=name, parent_id=parent_id, sort_order=9)
    db.session.add(dept)
    db.session.commit()
    return dept


class TestQADepartmentScope:
    """部门数据收窄：只能缩小，绝不能放大。"""

    def test_leader_scope_includes_grandchildren_but_not_other_branches(self, client):
        """Arrange 三级子部门 + 仓储部员工 → Act leader 访问人员列表 → Assert 只含子孙部门。"""
        prod = Department.query.filter_by(name='生产部').first()
        child = _dept('QA装配车间', prod.id)
        grandchild = _dept('QA一组', child.id)
        wh = Department.query.filter_by(name='仓储部').first()
        _make_user('qa_child', 'QA车间员工', child.id, 'staff')
        _make_user('qa_grand', 'QA小组员工', grandchild.id, 'staff')
        _make_user('qa_wh', 'QA仓储员工', wh.id, 'staff')

        login(client, 'leader1', '123456')
        resp = client.get('/hr/employees')

        assert resp.status_code == 200
        body = resp.data.decode('utf-8')
        assert 'QA车间员工' in body and 'QA小组员工' in body
        assert 'QA仓储员工' not in body

    def test_tampered_dept_id_and_keyword_cannot_expand_scope(self, client):
        """篡改 dept_id + keyword 双重参数仍被静默收窄（200 但不返回越权数据）。"""
        wh = Department.query.filter_by(name='仓储部').first()
        _make_user('qa_secret', 'QA绝密仓储人员', wh.id, 'staff')

        login(client, 'leader1', '123456')
        resp = client.get('/hr/employees?dept_id=%d&keyword=QA绝密' % wh.id)

        assert resp.status_code == 200
        assert 'QA绝密仓储人员' not in resp.data.decode('utf-8')

    def test_superadmin_sees_all_departments(self, client):
        """superadmin 完全豁免，全量可见。"""
        wh = Department.query.filter_by(name='仓储部').first()
        _make_user('qa_wh2', 'QA仓储乙', wh.id, 'staff')

        login(client, 'admin', 'admin123')
        resp = client.get('/hr/employees')

        assert resp.status_code == 200
        assert 'QA仓储乙' in resp.data.decode('utf-8')

    def test_attendance_tampered_user_id_is_scoped(self, client):
        """leader 篡改 user_id 查他部门员工考勤 → 只见自己（空数据），不 500/不越权。"""
        wh = Department.query.filter_by(name='仓储部').first()
        outsider = _make_user('qa_att_out', 'QA考勤 outsiders', wh.id, 'staff')
        db.session.add(AttendanceRecord(
            user_id=outsider.id, work_date=datetime(2025, 1, 6).date(),
            check_in_at=datetime(2025, 1, 6, 8, 59),
            check_out_at=datetime(2025, 1, 6, 18, 1)))
        db.session.commit()

        login(client, 'leader1', '123456')
        resp = client.get('/attendance/records?user_id=%d' % outsider.id)

        assert resp.status_code == 200
        assert '08:59' not in resp.data.decode('utf-8')

    def test_workorder_coalesce_related_department_then_leader_department(self, client):
        """工单归属 = related_department_id，空值回退负责人部门；越权工单不出现。"""
        prod = Department.query.filter_by(name='生产部').first()
        wh = Department.query.filter_by(name='仓储部').first()
        producer = User.query.filter_by(username='producer1').first()
        db.session.add_all([
            WorkOrder(order_no='QA-WO-REL', product_name='QA归属显式生产', quantity=1,
                      related_department_id=prod.id, created_by=1),
            WorkOrder(order_no='QA-WO-FB', product_name='QA归属回退生产', quantity=1,
                      leader_id=producer.id, created_by=1),
            WorkOrder(order_no='QA-WO-OUT', product_name='QA归属仓储', quantity=1,
                      related_department_id=wh.id, leader_id=producer.id, created_by=1),
        ])
        db.session.commit()

        login(client, 'leader1', '123456')
        leader_body = client.get('/production/orders').data.decode('utf-8')
        assert 'QA归属显式生产' in leader_body
        assert 'QA归属回退生产' in leader_body
        assert 'QA归属仓储' not in leader_body

        login(client, 'admin', 'admin123')
        admin_body = client.get('/production/orders').data.decode('utf-8')
        assert 'QA归属仓储' in admin_body

    def test_leader_can_approve_child_department_leave(self, client):
        """子部门员工请假属于主管管辖范围，可审批并落审批人。"""
        prod = Department.query.filter_by(name='生产部').first()
        child = _dept('QA审批子部门', prod.id)
        applicant = _make_user('qa_leave_child', 'QA子部门请假人', child.id, 'staff')
        leave = LeaveRequest(applicant_id=applicant.id, department_id=child.id,
                             leave_type='事假', start_at=datetime(2025, 1, 6, 9, 0),
                             end_at=datetime(2025, 1, 6, 18, 0), days=1,
                             reason='QA', status='pending', created_at=now())
        db.session.add(leave)
        db.session.commit()

        login(client, 'leader1', '123456')
        resp = client.get('/attendance/leave/approvals')
        assert 'QA子部门请假人' in resp.data.decode('utf-8')

        from conftest import get_csrf
        token = get_csrf(client, '/attendance/leave/approvals')
        client.post('/attendance/leave/%d/approve' % leave.id, data={
            'csrf_token': token, 'decision': 'approve', 'approve_comment': 'QA批准',
        })
        db.session.expire_all()
        assert db.session.get(LeaveRequest, leave.id).status == 'approved'
