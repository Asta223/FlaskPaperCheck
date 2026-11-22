"""统一时间工具：全项目一律通过 now() 取当前时间。

约定（架构文档共享知识 §4）：所有时间字段统一存本地时间
（Asia/Shanghai，naive datetime），禁止散落 datetime.now()/utcnow()。
展示用 Jinja 过滤器 fmt_dt / fmt_date（在应用工厂中注册）。
"""
import calendar
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    try:
        _LOCAL_TZ = ZoneInfo('Asia/Shanghai')
    except Exception:  # 时区库缺失时退回系统本地时间
        _LOCAL_TZ = None
except ImportError:  # Python < 3.9
    _LOCAL_TZ = None


def now() -> datetime:
    """当前本地时间（Asia/Shanghai，naive）。全项目统一取时入口。"""
    if _LOCAL_TZ is not None:
        return datetime.now(_LOCAL_TZ).replace(tzinfo=None)
    return datetime.now()


def today() -> date:
    """当前本地日期。"""
    return now().date()


def fmt_dt(value, fmt: str = '%Y-%m-%d %H:%M') -> str:
    """Jinja 过滤器：格式化 datetime/date，空值显示 '-'。"""
    if value in (None, ''):
        return '-'
    if isinstance(value, (datetime, date)):
        return value.strftime(fmt)
    return str(value)


def fmt_date(value) -> str:
    """Jinja 过滤器：格式化日期为 YYYY-MM-DD。"""
    return fmt_dt(value, '%Y-%m-%d')


def month_range(year: int, month: int):
    """返回 (该月第一天, 下月第一天)。"""
    first = date(year, month, 1)
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    return first, next_first


def workdays_in_month(year: int, month: int) -> list:
    """该月全部工作日（P0 简化：周一~周五，无节假日表）。"""
    first, _ = month_range(year, month)
    days_in_month = calendar.monthrange(year, month)[1]
    days = [date(year, month, d) for d in range(1, days_in_month + 1)]
    return [d for d in days if d.weekday() < 5]


# ---------------- L1 轻量排产：工作日工具（纯函数，无 app context）----------------
# 口径（架构 §3.3）：仅周一~周五为工作日，不引入节假日/调休；
# 全部只依赖 date/timedelta，便于直接单测。

def is_workday(d: date) -> bool:
    """是否工作日：周一~周五（weekday < 5），无节假日表。"""
    return d.weekday() < 5


def prev_workday(d: date) -> date:
    """严格向前最近的工作日（不含 d）。"""
    cursor = d - timedelta(days=1)
    while not is_workday(cursor):
        cursor -= timedelta(days=1)
    return cursor


def prev_workday_incl(d: date) -> date:
    """向前最近的工作日（含 d）：d 本身是工作日则原样返回。"""
    return d if is_workday(d) else prev_workday(d)


def next_workday(d: date) -> date:
    """严格向后最近的工作日（不含 d）。"""
    cursor = d + timedelta(days=1)
    while not is_workday(cursor):
        cursor += timedelta(days=1)
    return cursor


def workdays_between(a: date, b: date) -> int:
    """闭区间 [a, b] 内的工作日数；a > b 时返回负值（负的 [b, a] 闭区间工作日数）。

    交期落在周末时该周末不计工作日；a == b 且为工作日返回 1、为周末返回 0。
    """
    if a > b:
        return -workdays_between(b, a)
    count = 0
    cursor = a
    while cursor <= b:
        if is_workday(cursor):
            count += 1
        cursor += timedelta(days=1)
    return count


def workday_diff(a: date, b: date) -> int:
    """b 相对 a 的工作日差：同日=0，b 在 a 之后为正、之前为负。

    a 落在周末时先按 prev_workday_incl 锚定到前一工作日（与倒排工作日历一致），
    因此周末调用 days_remaining 时不会出现"多算/少算一天"的歧义。
    """
    anchor = prev_workday_incl(a)
    if anchor <= b:
        return workdays_between(anchor, b) - 1
    return -(workdays_between(b, anchor) - 1)
