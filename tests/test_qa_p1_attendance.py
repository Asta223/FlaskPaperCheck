# -*- coding: utf-8 -*-
"""QA 独立验证：P1-01/02/03 请假审批、迟到早退边界、月度统计。"""
from datetime import date, datetime

import pytest
from conftest import get_csrf, login

from app import db
from app.models import AttendanceRecord, LeaveRequest, OperationLog, User
from app.services import attendance_service
from app.utils.time_utils import now


def _staff():
    return User.query.filter_by(username='staff1').first()


def _leader():
    return User.query.filter_by(username='leader1').first()


def _make_leave(status='pending', start=None, end=None, applicant=None, department_id=None):
    """构造请假记录（默认 2025-01-06 生产部 staff1）。"""
    applicant = applicant or _staff()
    leave = LeaveRequest(
        applicant_id=applicant.id,
        department_id=department_id if department_id is not None else applicant.department_id,
        leave_type='事假',
        start_at=start or datetime(2025, 1, 6, 9, 0),
        end_at=end or datetime(2025, 1, 6, 18, 0),
        days=1, reason='QA请假', status=status, created_at=now())
    db.session.add(leave)
    db.session.commit()
    return leave


class TestQALateEarlyBoundary:
    """P1-02：宽限阈值 09:15 / 17:45 的精确边界与落库语义。"""

    @pytest.mark.parametrize('check_in,expected_late', [
        (datetime(2025, 1, 6, 9, 15), 0),
        (datetime(2025, 1, 6, 9, 16), 16),  # 分钟数按超过 09:00 班次起点计（架构 §③）
        (datetime(2025, 1, 6, 9, 0), 0),
    ])
    def test_check_in_boundary(self, app_ctx, check_in, expected_late):
        rec = AttendanceRecord(user_id=_staff().id, work_date=date(2025, 1, 6),
                               check_in_at=check_in)
        attendance_service.evaluate_record(rec)
        assert rec.late_minutes == expected_late

    @pytest.mark.parametrize('check_out,expected_early', [
        (datetime(2025, 1, 6, 17, 45), 0),
        (datetime(2025, 1, 6, 17, 44), 16),  # 分钟数按早于 18:00 班次终点计
        (datetime(2025, 1, 6, 18, 0), 0),
    ])
    def test_check_out_boundary(self, app_ctx, check_out, expected_early):
        rec = AttendanceRecord(user_id=_staff().id, work_date=date(2025, 1, 6),
                               check_out_at=check_out)
        attendance_service.evaluate_record(rec)
        assert rec.early_leave_minutes == expected_early

    def test_combined_status_codes_and_chinese_labels(self, app_ctx):
        """迟到+早退同日用逗号短码并存，UI/CSV 展示应为中文标签。"""
        rec = AttendanceRecord(user_id=_staff().id, work_date=date(2025, 1, 6),
                               check_in_at=datetime(2025, 1, 6, 9, 20),
                               check_out_at=datetime(2025, 1, 6, 17, 30))
        attendance_service.evaluate_record(rec)
        assert rec.day_status == 'late,early'
        assert rec.day_status_labels == '迟到,早退'

        normal = AttendanceRecord(user_id=_staff().id, work_date=date(2025, 1, 7),
                                  check_in_at=datetime(2025, 1, 7, 9, 0),
                                  check_out_at=datetime(2025, 1, 7, 18, 0))
        attendance_service.evaluate_record(normal)
        assert normal.day_status == 'normal'
        assert normal.day_status_labels == '正常'

    def test_weekend_and_leave_do_not_rewrite_raw_record(self, app_ctx):
        """周末不判；请假豁免只作用于统计，原始打卡分钟数不被改写。"""
        staff = _staff()
        staff.hire_date = date(2025, 1, 1)
        weekend = AttendanceRecord(user_id=staff.id, work_date=date(2025, 1, 4),
                                   check_in_at=datetime(2025, 1, 4, 10, 0),
                                   check_out_at=datetime(2025, 1, 4, 16, 0))
        attendance_service.evaluate_record(weekend)
        db.session.add(weekend)
        db.session.add(AttendanceRecord(
            user_id=staff.id, work_date=date(2025, 1, 6),
            check_in_at=datetime(2025, 1, 6, 9, 30),
            check_out_at=datetime(2025, 1, 6, 18, 0),
            late_minutes=30, early_leave_minutes=0, day_status='late'))
        db.session.add(_make_leave(status='approved',
                                   start=datetime(2025, 1, 6, 0, 0),
                                   end=datetime(2025, 1, 6, 23, 59)))
        db.session.commit()

        stats = attendance_service.monthly_stats(staff, 2025, 1)
        db.session.expire_all()
        raw = AttendanceRecord.query.filter_by(user_id=staff.id,
                                               work_date=date(2025, 1, 6)).first()
        assert weekend.late_minutes == 0 and weekend.early_leave_minutes == 0
        assert raw.late_minutes == 30  # 原始判定未被请假审批改写
        assert stats['late_days'] == 0  # 统计层豁免
        assert stats['leave_days'] == 1


class TestQALeaveApproval:
    """P1-01：审批状态机终态、越权 403、审批字段与日志落库。"""

    def test_illegal_state_transition_rejected(self, client):
        """终态不可二次审批；非法 decision 被拒；状态不被改写。"""
        pending = _make_leave(status='pending')
        approved = _make_leave(status='approved')
        leader = _leader()
        login(client, 'leader1', '123456')
        token = get_csrf(client, '/attendance/leave/new')

        bad = client.post('/attendance/leave/%d/approve' % pending.id, data={
            'csrf_token': token, 'decision': 'pending', 'approve_comment': '非法',
        })
        repeat = client.post('/attendance/leave/%d/approve' % approved.id, data={
            'csrf_token': token, 'decision': 'approve', 'approve_comment': '重复',
        }, follow_redirects=True)

        db.session.expire_all()
        assert bad.status_code == 400
        assert db.session.get(LeaveRequest, pending.id).status == 'pending'
        stored = db.session.get(LeaveRequest, approved.id)
        assert repeat.status_code == 200
        assert stored.status == 'approved'
        assert stored.approver_id != leader.id or stored.approve_comment != '重复'

    def test_approval_fields_and_operation_log_persisted(self, client):
        """审批人/时间/意见 + OperationLog 同事务落库。"""
        leave = _make_leave()
        login(client, 'leader1', '123456')
        token = get_csrf(client, '/attendance/leave/new')
        client.post('/attendance/leave/%d/approve' % leave.id, data={
            'csrf_token': token, 'decision': 'reject', 'approve_comment': 'QA驳回意见',
        })
        db.session.expire_all()
        stored = db.session.get(LeaveRequest, leave.id)
        log = OperationLog.query.filter_by(module='attendance', action='approve',
                                           target_type='leave_request',
                                           target_id=leave.id).first()
        assert stored.status == 'rejected'
        assert stored.approver_id == _leader().id
        assert stored.approved_at is not None
        assert stored.approve_comment == 'QA驳回意见'
        assert log is not None and 'QA驳回意见' not in (log.summary or '')
        assert log.summary and '驳回' in log.summary
