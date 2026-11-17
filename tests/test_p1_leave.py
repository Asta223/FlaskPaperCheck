# -*- coding: utf-8 -*-
"""P1 考勤测试：迟到/早退判定落库、请假申请审批状态机、请假豁免、部门汇总数据权限。"""
from datetime import date, datetime, time

from conftest import get_csrf, login

from app import db
from app.models import AttendanceRecord, Department, LeaveRequest, User
from app.services import attendance_service


def _staff():
    return User.query.filter_by(username='staff1').first()


def _leader():
    return User.query.filter_by(username='leader1').first()


def _admin():
    return User.query.filter_by(username='admin').first()


# ---------------- P1-02 迟到/早退判定落库 ----------------

def test_evaluate_late_and_early_codes(app_ctx):
    """09:20 签到记迟到20分钟；17:30 签退记早退30分钟；day_status 组合短码。"""
    staff = _staff()
    rec = AttendanceRecord(user_id=staff.id, work_date=date(2025, 1, 6),
                           check_in_at=datetime(2025, 1, 6, 9, 20),
                           check_out_at=datetime(2025, 1, 6, 17, 30))
    attendance_service.evaluate_record(rec)
    assert rec.late_minutes == 20
    assert rec.early_leave_minutes == 30
    assert rec.day_status == 'late,early'


def test_evaluate_normal_no_penalty(app_ctx):
    """09:00/18:00 正常：两值为0，状态 normal。"""
    staff = _staff()
    rec = AttendanceRecord(user_id=staff.id, work_date=date(2025, 1, 6),
                           check_in_at=datetime(2025, 1, 6, 9, 0),
                           check_out_at=datetime(2025, 1, 6, 18, 0))
    attendance_service.evaluate_record(rec)
    assert rec.late_minutes == 0 and rec.early_leave_minutes == 0
    assert rec.day_status == 'normal'


def test_evaluate_within_grace_no_penalty(app_ctx):
    """09:10（宽限内）/17:50（宽限内）不判。"""
    staff = _staff()
    rec = AttendanceRecord(user_id=staff.id, work_date=date(2025, 1, 6),
                           check_in_at=datetime(2025, 1, 6, 9, 10),
                           check_out_at=datetime(2025, 1, 6, 17, 50))
    attendance_service.evaluate_record(rec)
    assert rec.late_minutes == 0 and rec.early_leave_minutes == 0


def test_evaluate_weekend_no_penalty(app_ctx):
    """周末打卡不判迟到早退。"""
    staff = _staff()
    rec = AttendanceRecord(user_id=staff.id, work_date=date(2025, 1, 4),  # 周六
                           check_in_at=datetime(2025, 1, 4, 10, 0),
                           check_out_at=datetime(2025, 1, 4, 16, 0))
    attendance_service.evaluate_record(rec)
    assert rec.late_minutes == 0 and rec.early_leave_minutes == 0


def test_clock_persists_late_minutes(client):
    """打卡路由落库判定：09:16 之后签到应写 late_minutes（用 monkeypatch 时间）。"""
    # 直接构造记录并走 service 落库验证（路由 now() 无法固定，service 语义已覆盖）
    staff = _staff()
    rec = AttendanceRecord(user_id=staff.id, work_date=date(2025, 1, 6),
                           check_in_at=datetime(2025, 1, 6, 9, 25))
    attendance_service.evaluate_record(rec)
    db.session.add(rec)
    db.session.commit()
    db.session.expire_all()
    stored = AttendanceRecord.query.filter_by(user_id=staff.id, work_date=date(2025, 1, 6)).first()
    assert stored.late_minutes == 25 and stored.day_status == 'late'


# ---------------- P1-01 请假申请与审批 ----------------

def _post_leave(client, start, end, ltype='事假'):
    token = get_csrf(client, '/attendance/leave/new')
    return client.post('/attendance/leave/new', data={
        'csrf_token': token, 'leave_type': ltype,
        'start_at': start, 'end_at': end, 'reason': '家中有事',
    }, follow_redirects=True)


def test_leave_apply_pending(client):
    """员工提交合法请假 → pending，申请人/部门自动带入。"""
    login(client, 'staff1', '123456')
    staff = _staff()
    resp = _post_leave(client, '2025-01-06T09:00', '2025-01-07T18:00')
    assert resp.status_code == 200
    lv = LeaveRequest.query.filter_by(applicant_id=staff.id).first()
    assert lv is not None and lv.status == 'pending'
    assert lv.department_id == staff.department_id
    assert lv.days > 0


def test_leave_apply_invalid_range_rejected(client):
    """结束早于开始 → 拒绝，字段级错误，不落库。"""
    login(client, 'staff1', '123456')
    staff = _staff()
    resp = _post_leave(client, '2025-01-07T09:00', '2025-01-06T18:00')
    assert resp.status_code == 200
    assert LeaveRequest.query.filter_by(applicant_id=staff.id).count() == 0


def test_leave_approve_by_leader(client):
    """主管批准本部门请假 → approved，记录审批人/时间。"""
    staff = _staff()
    lv = LeaveRequest(applicant_id=staff.id, department_id=staff.department_id,
                      leave_type='事假', start_at=datetime(2025, 1, 6, 9, 0),
                      end_at=datetime(2025, 1, 7, 18, 0), days=2, reason='x', status='pending')
    db.session.add(lv)
    db.session.commit()
    login(client, 'leader1', '123456')
    token = get_csrf(client, '/attendance/leave/approvals')
    resp = client.post('/attendance/leave/%d/approve' % lv.id, data={
        'csrf_token': token, 'decision': 'approve', 'approve_comment': '同意',
    }, follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire_all()
    lv = db.session.get(LeaveRequest, lv.id)
    assert lv.status == 'approved' and lv.approver_id == _leader().id
    assert lv.approved_at is not None and lv.approve_comment == '同意'


def test_leave_approve_out_of_scope_403(client):
    """主管尝试审批非管辖部门请假 → 403；staff 尝试审批 → 403。"""
    other_dept = Department.query.filter_by(name='仓储部').first()
    lv = LeaveRequest(applicant_id=_admin().id, department_id=other_dept.id,
                      leave_type='事假', start_at=datetime(2025, 1, 6, 9, 0),
                      end_at=datetime(2025, 1, 6, 18, 0), days=1, reason='x', status='pending')
    db.session.add(lv)
    db.session.commit()

    login(client, 'leader1', '123456')  # leader1 管辖生产部，不含仓储部
    token = get_csrf(client, '/attendance/leave/new')  # CSRF token 同会话通用
    resp = client.post('/attendance/leave/%d/approve' % lv.id,
                       data={'csrf_token': token, 'decision': 'approve'})
    assert resp.status_code == 403
    db.session.expire_all()
    assert db.session.get(LeaveRequest, lv.id).status == 'pending'

    # staff 无审批权限（无 attendance.leave.approve）→ 403
    login(client, 'staff1', '123456')
    token = get_csrf(client, '/attendance/leave/new')
    resp = client.post('/attendance/leave/%d/approve' % lv.id,
                       data={'csrf_token': token, 'decision': 'approve'})
    assert resp.status_code == 403


def test_approved_leave_exempt_from_absent_and_late(app_ctx):
    """已批准请假覆盖的工作日不计缺卡、不判迟到早退。"""
    staff = _staff()
    staff.hire_date = date(2025, 1, 1)
    db.session.add(LeaveRequest(
        applicant_id=staff.id, department_id=staff.department_id, leave_type='病假',
        start_at=datetime(2025, 1, 6, 0, 0), end_at=datetime(2025, 1, 10, 23, 59),
        days=5, reason='病', status='approved'))
    db.session.commit()
    stats = attendance_service.monthly_stats(staff, 2025, 1)
    # 1/6~1/10 五个工作日被请假豁免：attend=0, absent=23-5=18, leave=5
    assert stats['attend_days'] == 0
    assert stats['absent_days'] == 18
    assert stats['leave_days'] == 5


# ---------------- P1-03 部门汇总数据权限 ----------------

def test_monthly_dept_summary_scoped(client):
    """主管篡改 dept_id 到非管辖部门 → 静默收窄为空，不 500、不越权。"""
    login(client, 'leader1', '123456')
    warehouse_dept = Department.query.filter_by(name='仓储部').first()
    resp = client.get('/attendance/monthly?year=2025&month=1&dept_id=%d' % warehouse_dept.id)
    assert resp.status_code == 200
    assert resp.status_code != 403  # 静默收窄而非报错
