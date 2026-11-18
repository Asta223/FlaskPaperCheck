"""统一时间工具：全项目一律通过 now() 取当前时间。

约定（架构文档共享知识 §4）：所有时间字段统一存本地时间
（Asia/Shanghai，naive datetime），禁止散落 datetime.now()/utcnow()。
展示用 Jinja 过滤器 fmt_dt / fmt_date（在应用工厂中注册）。
"""
import calendar
from datetime import date, datetime

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
