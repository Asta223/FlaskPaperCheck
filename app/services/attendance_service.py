"""考勤统计服务：迟到/早退判定落库、请假豁免、月度与部门汇总聚合。

P0 基线：周一~周五为工作日（无节假日表）；缺卡=应出勤工作日无打卡记录。
P1 增量：
- evaluate_record()：打卡落库那一刻判定迟到/早退（读 config 阈值），历史不回溯；
- 请假豁免：统计时按「已批准请假区间覆盖工作日」排除缺卡/迟到早退判定，不改写原始打卡；
- department_summary()：部门（含子部门）成员月度汇总，数据权限在路由层收窄。
"""
from datetime import date, datetime, time, timedelta

from flask import current_app

from app import db
from app.models.attendance import AttendanceRecord
from app.models.leave import LeaveRequest
from app.utils.time_utils import today, workdays_in_month


def _parse_hhmm(value: str) -> time:
    """解析 'HH:MM' 配置字符串为 time。"""
    try:
        hour, minute = str(value).split(':')
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        return time(9, 0)


def _thresholds() -> tuple:
    """返回 (shift_start, late_cutoff, shift_end, early_cutoff) 四个 time。"""
    cfg = current_app.config
    shift_start = _parse_hhmm(cfg.get('SHIFT_START', '09:00'))
    shift_end = _parse_hhmm(cfg.get('SHIFT_END', '18:00'))
    late_grace = int(cfg.get('LATE_GRACE_MIN', 15))
    early_grace = int(cfg.get('EARLY_GRACE_MIN', 15))
    late_cutoff = (datetime.combine(today(), shift_start) + timedelta(minutes=late_grace)).time()
    early_cutoff = (datetime.combine(today(), shift_end) - timedelta(minutes=early_grace)).time()
    return shift_start, late_cutoff, shift_end, early_cutoff


def is_workday(day) -> bool:
    """是否工作日（周一~周五，读 config.WORKDAYS）。"""
    workdays = current_app.config.get('WORKDAYS', (0, 1, 2, 3, 4))
    return day.weekday() in tuple(workdays)


def evaluate_record(record: AttendanceRecord) -> AttendanceRecord:
    """在打卡写入时判定迟到/早退并落库（不 commit，由调用方随业务提交）。

    规则（A2）：工作日签到晚于 09:15 → late_minutes>0；签退早于 17:45 → early_leave_minutes>0；
    非工作日不判。day_status 用逗号分隔短码（可组合 late,early）。
    """
    late_minutes = 0
    early_minutes = 0
    codes = []

    if is_workday(record.work_date):
        shift_start, late_cutoff, shift_end, early_cutoff = _thresholds()
        if record.check_in_at:
            check_in = record.check_in_at.time()
            if check_in > late_cutoff:
                late_minutes = max(0, int(
                    (datetime.combine(record.work_date, check_in)
                     - datetime.combine(record.work_date, shift_start)).total_seconds() // 60))
                codes.append(AttendanceRecord.DAY_LATE)
        if record.check_out_at:
            check_out = record.check_out_at.time()
            if check_out < early_cutoff:
                early_minutes = max(0, int(
                    (datetime.combine(record.work_date, shift_end)
                     - datetime.combine(record.work_date, check_out)).total_seconds() // 60))
                codes.append(AttendanceRecord.DAY_EARLY)

    record.late_minutes = late_minutes
    record.early_leave_minutes = early_minutes
    record.day_status = ','.join(codes) if codes else AttendanceRecord.DAY_NORMAL
    return record


def approved_leave_dates(user_id: int, year: int, month: int) -> set:
    """该用户当月全部「已批准」请假覆盖的日期集合（含首尾，按天展开）。"""
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    result = set()
    leaves = (LeaveRequest.query
              .filter(LeaveRequest.applicant_id == user_id,
                      LeaveRequest.status == 'approved',
                      LeaveRequest.start_at <= datetime.combine(last_day, time(23, 59, 59)),
                      LeaveRequest.end_at >= datetime.combine(first_day, time(0, 0)))
              .all())
    for leave in leaves:
        cur = leave.start_at.date()
        end = leave.end_at.date()
        while cur <= end:
            if first_day <= cur <= last_day:
                result.add(cur)
            cur += timedelta(days=1)
    return result


def monthly_stats(user, year: int, month: int) -> dict:
    """某用户某月统计（保留 P0 返回键，新增 P1 计数键）。

    返回额外键：
    - late_days / early_days：迟到/早退次数（按分钟字段计数，排除已批准请假日）；
    - leave_days：已批准请假覆盖的工作日天数。
    请假豁免仅作用于统计层，不改写 AttendanceRecord 原始判定。
    """
    workdays = workdays_in_month(year, month)
    first_day = workdays[0]
    last_day = workdays[-1]

    records = (AttendanceRecord.query
               .filter(AttendanceRecord.user_id == user.id,
                       AttendanceRecord.work_date >= first_day,
                       AttendanceRecord.work_date <= last_day)
               .order_by(AttendanceRecord.work_date.desc())
               .all())
    by_date = {r.work_date: r for r in records}

    leave_dates = approved_leave_dates(user.id, year, month)
    leave_days = sum(1 for d in workdays if d in leave_dates)

    current = today()
    hire = user.hire_date
    leave = user.leave_date if not getattr(user, 'is_active', True) else None

    attend_days = 0
    absent_days = 0
    late_days = 0
    early_days = 0
    for day in workdays:
        if hire and day < hire:
            continue
        if leave and day > leave:
            continue
        if day > current:
            continue
        # 已批准请假：不计缺卡、不判迟到早退（豁免仅统计层）
        if day in leave_dates:
            continue
        record = by_date.get(day)
        if record is not None and record.check_in_at:
            attend_days += 1
            if (record.late_minutes or 0) > 0:
                late_days += 1
            if (record.early_leave_minutes or 0) > 0:
                early_days += 1
        elif record is None:
            absent_days += 1
        # 有记录但缺签退：仍算出勤（P0 从简）

    return {
        'user': user,
        'year': year,
        'month': month,
        'attend_days': attend_days,
        'absent_days': absent_days,
        'late_days': late_days,
        'early_days': early_days,
        'leave_days': leave_days,
        'records': records,
        'by_date': by_date,
    }


def department_summary(members, year: int, month: int) -> list:
    """部门成员月度汇总：每位成员一行 stats（数据权限由路由层传入已收窄的 members）。"""
    rows = []
    for member in members:
        rows.append({'user': member, 'stats': monthly_stats(member, year, month)})
    return rows
