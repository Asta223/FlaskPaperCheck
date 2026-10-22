"""考勤统计服务：月度出勤/缺卡聚合。

P0 简化：周一~周五为工作日（无节假日表）；
缺卡 = 应出勤工作日无打卡记录（排除入职前、离职后、未来日期）。
"""
from app import db
from app.models.attendance import AttendanceRecord
from app.utils.time_utils import today, workdays_in_month


def monthly_stats(user, year: int, month: int) -> dict:
    """某用户某月统计。

    返回 {'user','year','month','attend_days','absent_days','records'}：
    - attend_days：有签到记录的工作日数；
    - absent_days：应出勤但无记录的工作日数（缺卡）；
    - records：该月打卡记录（按日期倒序）。
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

    current = today()
    hire = user.hire_date
    leave = user.leave_date if not user.is_active else None

    attend_days = 0
    absent_days = 0
    for day in workdays:
        if hire and day < hire:
            continue  # 入职前
        if leave and day > leave:
            continue  # 离职后
        if day > current:
            continue  # 未来日期不算缺卡
        record = by_date.get(day)
        if record is not None and record.check_in_at:
            attend_days += 1
        elif record is None:
            absent_days += 1
        # 有记录但缺签退：仍算出勤（P0 从简）

    return {
        'user': user,
        'year': year,
        'month': month,
        'attend_days': attend_days,
        'absent_days': absent_days,
        'records': records,
        'by_date': by_date,
    }
