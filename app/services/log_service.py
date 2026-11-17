"""统一操作日志服务（P1-15/P1-06）：log_operation() 唯一写入口。

纪律：
- 调用方必须在业务事务内调用（不自行 commit），日志随业务同事务提交；
- 仅在校验通过、状态变更之后调用（失败操作不记成功日志）；
- operator_id / ip 省略时自动取当前用户与请求 IP。
"""
from flask import has_request_context, request
from flask_login import current_user

from app import db
from app.models.system import OperationLog
from app.utils.time_utils import now


def log_operation(module, action, target_type=None, target_id=None, summary='',
                  operator_id=None, ip=None, commit=False) -> OperationLog:
    """写入一条操作日志（默认不 commit，随业务事务提交）。

    Args:
        module: 模块/蓝图名（hr/attendance/production/warehouse/files/chat/system/auth）。
        action: 动作类型（login/create/update/transition/approve/issue/export/import）。
        target_type: 多态目标类型（如 work_order/leave_request），可空。
        target_id: 多态目标 ID（无 FK），可空。
        summary: 摘要。
        operator_id: 操作人 ID，省略取 current_user.id（未登录可为 None）。
        ip: 操作 IP，省略取 request.remote_addr。
        commit: 是否立即提交。默认 False（同事务）；仅极少数独立日志场景才设 True。

    Returns:
        已 add 到 session 的 OperationLog 实例。
    """
    if operator_id is None:
        try:
            if current_user is not None and current_user.is_authenticated:
                operator_id = current_user.id
        except Exception:
            operator_id = None
    if ip is None and has_request_context():
        try:
            ip = request.remote_addr
        except Exception:
            ip = None

    log = OperationLog(
        operator_id=operator_id,
        module=module or '',
        action=action or '',
        target_type=target_type,
        target_id=target_id,
        summary=summary or '',
        ip=(ip or '')[:64] or None,
        created_at=now(),
    )
    db.session.add(log)
    if commit:
        db.session.commit()
    return log
