# -*- coding: utf-8 -*-
"""考勤模块测试：签到幂等、签退依赖签到、月度统计（跨天数据构造）。"""
from datetime import date, datetime

from conftest import get_csrf, login

from app import db
from app.models import AttendanceRecord, User
from app.services import attendance_service


def _staff():
    return User.query.filter_by(username='staff1').first()


# ---------------- 打卡路由 ----------------

def test_all_roles_can_clock(client):
    """全员打卡：admin + 五种内置业务角色均可访问打卡页并成功签到。"""
    accounts = [('admin', 'admin123'), ('leader1', '123456'), ('keeper1', '123456'),
                ('producer1', '123456'), ('staff1', '123456'), ('arch1', '123456')]
    for username, password in accounts:
        login(client, username, password)
        assert client.get('/attendance/clock').status_code == 200, username
        token = get_csrf(client, '/attendance/clock')
        resp = client.post('/attendance/clock', data={'csrf_token': token, 'action': 'in'},
                           follow_redirects=True)
        assert '签到成功'.encode() in resp.data, username


def test_clock_in_idempotent(client):
    """重复点签到：仅一条记录、签到时间不变。"""
    login(client, 'staff1', '123456')
    token = get_csrf(client, '/attendance/clock')
    resp = client.post('/attendance/clock', data={'csrf_token': token, 'action': 'in'},
                       follow_redirects=True)
    assert resp.status_code == 200
    staff = _staff()
    recs = AttendanceRecord.query.filter_by(user_id=staff.id).all()
    assert len(recs) == 1 and recs[0].check_in_at is not None
    first_in = recs[0].check_in_at
    # 第二次签到
    token = get_csrf(client, '/attendance/clock')
    resp = client.post('/attendance/clock', data={'csrf_token': token, 'action': 'in'},
                       follow_redirects=True)
    assert '今日已签到'.encode() in resp.data
    recs = AttendanceRecord.query.filter_by(user_id=staff.id).all()
    assert len(recs) == 1
    assert recs[0].check_in_at == first_in, '重复签到不应更新签到时间'


def test_checkout_requires_checkin(client):
    login(client, 'staff1', '123456')
    token = get_csrf(client, '/attendance/clock')
    resp = client.post('/attendance/clock', data={'csrf_token': token, 'action': 'out'},
                       follow_redirects=True)
    assert '请先签到再签退'.encode() in resp.data
    assert AttendanceRecord.query.count() == 0


def test_checkout_after_checkin_and_repeat(client):
    login(client, 'staff1', '123456')
    token = get_csrf(client, '/attendance/clock')
    client.post('/attendance/clock', data={'csrf_token': token, 'action': 'in'})
    token = get_csrf(client, '/attendance/clock')
    resp = client.post('/attendance/clock', data={'csrf_token': token, 'action': 'out'},
                       follow_redirects=True)
    assert '签退成功'.encode() in resp.data
    staff = _staff()
    rec = AttendanceRecord.query.filter_by(user_id=staff.id).first()
    assert rec.check_in_at is not None and rec.check_out_at is not None
    # 重复签退
    token = get_csrf(client, '/attendance/clock')
    resp = client.post('/attendance/clock', data={'csrf_token': token, 'action': 'out'},
                       follow_redirects=True)
    assert '今日已签退'.encode() in resp.data


# ---------------- 月度统计（2025-01 共 23 个工作日） ----------------

def _set_user(user, hire_date=None, leave_date=None, is_active=True):
    user.hire_date = hire_date
    user.leave_date = leave_date
    user.is_active = is_active
    db.session.commit()


def _add_records(user, days, year=2025, month=1, with_checkout=True):
    for d in days:
        db.session.add(AttendanceRecord(
            user_id=user.id, work_date=date(year, month, d),
            check_in_at=datetime(year, month, d, 9, 0),
            check_out_at=datetime(year, month, d, 18, 0) if with_checkout else None))
    db.session.commit()


def test_monthly_stats_basic(app_ctx):
    """跨天构造：当月多个工作日的打卡/缺卡混合。"""
    user = _staff()
    _set_user(user, hire_date=date(2025, 1, 1))
    _add_records(user, [6, 7, 8])  # 打卡 3 天
    stats = attendance_service.monthly_stats(user, 2025, 1)
    assert stats['attend_days'] == 3
    assert stats['absent_days'] == 20  # 23 个工作日 - 3


def test_monthly_stats_records_span_weeks(app_ctx):
    """记录分布在多个自然周（跨天、跨周末），周末不计数。"""
    user = _staff()
    _set_user(user, hire_date=date(2025, 1, 1))
    # 1/4(六)、1/5(日) 为周末，不应计入出勤；1/3(五)、1/13(一) 打卡
    _add_records(user, [3, 4, 5, 13])
    stats = attendance_service.monthly_stats(user, 2025, 1)
    assert stats['attend_days'] == 2
    assert stats['absent_days'] == 21


def test_monthly_stats_hire_mid_month(app_ctx):
    """入职前的工作日不算缺卡。"""
    user = _staff()
    _set_user(user, hire_date=date(2025, 1, 20))
    stats = attendance_service.monthly_stats(user, 2025, 1)
    assert stats['attend_days'] == 0
    # 1/20(一)~1/31(五) 的工作日数 = 10
    assert stats['absent_days'] == 10


def test_monthly_stats_leave_after_not_absent(app_ctx):
    """离职后（leave_date 之后）的工作日不算缺卡。"""
    user = _staff()
    _set_user(user, hire_date=date(2025, 1, 1), leave_date=date(2025, 1, 10),
              is_active=False)
    stats = attendance_service.monthly_stats(user, 2025, 1)
    # 1/1~1/10 的工作日：1,2,3,6,7,8,9,10 = 8 天
    assert stats['absent_days'] == 8
    assert stats['attend_days'] == 0


def test_monthly_stats_record_without_checkin_neither_attend_nor_absent(app_ctx):
    """存在记录但无签到时间：不算出勤也不算缺卡（边界语义）。"""
    user = _staff()
    _set_user(user, hire_date=date(2025, 1, 1))
    db.session.add(AttendanceRecord(user_id=user.id, work_date=date(2025, 1, 6),
                                    check_in_at=None, check_out_at=None))
    db.session.commit()
    stats = attendance_service.monthly_stats(user, 2025, 1)
    assert stats['attend_days'] == 0
    assert stats['absent_days'] == 22  # 23 - 1（该日有记录）


# ---------------- 数据权限边界 ----------------

def test_records_user_id_ignored_without_view_all(client):
    """无 view_all 权限的员工传 user_id 应被忽略（防 IDOR），只看自己。"""
    login(client, 'staff1', '123456')
    admin = User.query.filter_by(username='admin').first()
    resp = client.get('/attendance/records?user_id=%d' % admin.id)
    assert resp.status_code == 200
    assert '赵员工'.encode() in resp.data  # staff1 姓名


def test_leader_view_all_can_view_others(client):
    login(client, 'leader1', '123456')
    staff = _staff()
    resp = client.get('/attendance/records?user_id=%d' % staff.id)
    assert resp.status_code == 200
    assert '赵员工'.encode() in resp.data
