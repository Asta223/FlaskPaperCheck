"""L1 轻量排产服务：倒排计算、人工覆盖与超期/开工预警判定。

设计约束（架构文档 §4）：
- 全部为模块级函数，显式传参、today 可注入；
- 不 import 任何 app.models，通过 duck typing 读取 order/step 属性，
  保证零 app context 亦可单测；
- apply_plan 是唯一写库入口，且不 commit（由调用方统一提交事务）。
"""
import math

from flask import current_app

from app.utils import time_utils

# 终态：不参与自动重算与标红，保留计划日期快照供追溯
TERMINAL_STATUSES = ('completed', 'accepted')


def sum_standard_hours(order) -> float:
    """汇总工单参考工时总量（小时）：Σ 未删除工序行的 standard_hours × 工单数量。

    口径见架构 §3.1 / §10：Process.standard_hours 为"单件单工序"参考工时，
    总量必须与产量成正比；WorkOrderStep.labor_hours 是完工实耗，不作计划输入。

    采用 duck typing：order.steps / step.process / order.quantity 均通过 getattr
    读取；孤立工序行（process 为空/已软删）或工时为空按 0 计。
    """
    total = 0.0
    for step in (getattr(order, 'steps', None) or []):
        if getattr(step, 'is_deleted', False):
            continue
        process = getattr(step, 'process', None)
        if process is None or getattr(process, 'is_deleted', False):
            continue
        hours = getattr(process, 'standard_hours', 0) or 0
        try:
            total += float(hours)
        except (TypeError, ValueError):
            continue
    quantity = getattr(order, 'quantity', 1) or 1
    return round(total * quantity, 2)


def calculate_plan(due_date, hours_total, capacity=None):
    """按交期与总工时倒排，返回 (计划开工日, 计划完工日)。

    Args:
        due_date: 交期；为空直接返回 (None, None)。
        hours_total: 总参考工时（小时）；<=0 返回 (None, None)，不伪造 1 天。
        capacity: 日产能（小时/工作日）；省略时读 current_app.config。

    Returns:
        tuple: (plan_start_date, plan_end_date)；plan_end_date 保留交期原值
        （含落在周末的情况），plan_start_date 必为工作日。

    Raises:
        ValueError: capacity <= 0 时抛出，不静默吞掉配置错误。
    """
    if due_date is None or hours_total is None or hours_total <= 0:
        return (None, None)
    if capacity is None:
        capacity = current_app.config['DAILY_CAPACITY_HOURS']
    if capacity <= 0:
        raise ValueError('DAILY_CAPACITY_HOURS 必须大于 0')

    days = max(1, int(math.ceil(hours_total / capacity)))
    cursor = time_utils.prev_workday_incl(due_date)  # 第 1 个工作日（含交期当天）
    for _ in range(days - 1):
        cursor = time_utils.prev_workday(cursor)
    return (cursor, due_date)


def apply_plan(order, manual_start=None, manual_end=None) -> str:
    """唯一写库入口：按自动/人工模式写入计划字段（不 commit）。

    人工/自动判定采用架构 §5 口径：两个日期任一非空即视为人工覆盖。
    路由层负责"人工必须两个都填"的校验与本函数之前的 flash 中止。

    Returns:
        str: 'manual'（人工写入）/'auto'（自动倒排成功）/'unavailable'（无交期或无工时）。
    """
    if manual_start is not None or manual_end is not None:
        order.plan_start_date = manual_start
        order.plan_end_date = manual_end
        order.plan_manual = True
        return 'manual'

    start, end = calculate_plan(getattr(order, 'due_date', None), sum_standard_hours(order))
    if start is None or end is None:
        order.plan_start_date = None
        order.plan_end_date = None
        order.plan_manual = False
        return 'unavailable'

    order.plan_start_date = start
    order.plan_end_date = end
    order.plan_manual = False
    return 'auto'


def is_overdue(order, today=None) -> bool:
    """未完工且交期已过（due_date < today）→ 已超期。"""
    if getattr(order, 'status', None) in TERMINAL_STATUSES:
        return False
    current = today or time_utils.today()
    due = getattr(order, 'due_date', None)
    if due is None:
        return False
    return due < current


def is_start_warning(order, today=None) -> bool:
    """未完工且最晚开工日已到/已过、交期未过（start <= today <= due）→ 开工预警。"""
    if getattr(order, 'status', None) in TERMINAL_STATUSES:
        return False
    current = today or time_utils.today()
    start = getattr(order, 'plan_start_date', None)
    due = getattr(order, 'due_date', None)
    if start is None or due is None:
        return False
    return start <= current <= due


def days_remaining(order, today=None):
    """倒排剩余工作日：>0 还剩 N 个工作日，=0 今天最晚开工，<0 已过 N 个工作日。

    today 可注入；无计划开工日返回 None（禁止 None 参与日期比较）。
    """
    start = getattr(order, 'plan_start_date', None)
    if start is None:
        return None
    current = today or time_utils.today()
    return time_utils.workday_diff(current, start)


def plan_status(order, today=None) -> dict:
    """聚合展示状态，供模板一次取值（避免在模板内调用 Python 函数）。

    Returns:
        dict: {overdue, warning, label, days, manual, priority}。
        已超期优先于开工预警；终态 overdue/warning 均为 False 且 label 为空。
    """
    current = today or time_utils.today()
    terminal = getattr(order, 'status', None) in TERMINAL_STATUSES
    overdue = False if terminal else is_overdue(order, current)
    warning = False if terminal else is_start_warning(order, current)
    if overdue:
        label = '已超期'
    elif warning:
        label = '开工预警'
    else:
        label = ''
    return {
        'overdue': overdue,
        'warning': warning,
        'label': label,
        'days': days_remaining(order, current),
        'manual': bool(getattr(order, 'plan_manual', False)),
        'priority': getattr(order, 'priority', None) or 'normal',
    }
