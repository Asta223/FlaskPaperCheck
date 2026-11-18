"""工作台首页：统计卡片 + 进行中工单简表 + 快捷入口。

P1 增量：纳入待审批请假数、库存预警未读消息数；统计卡片按数据权限收窄。
"""
from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.models.leave import LeaveRequest
from app.models.material import Material
from app.models.production import WorkOrder
from app.models.user import User
from app.models.warehouse import Inventory
from app.services import chat_service
from app.utils.data_scope import visible_department_ids
from app.utils.permissions import has_permission

bp = Blueprint('main', __name__)


def _scope_order_query():
    """工作台工单：复用生产数据权限口径（coalesce 归属部门）。"""
    from sqlalchemy import func
    from app import db
    query = WorkOrder.query
    scope = visible_department_ids(current_user)
    if scope is None:
        return query
    dept_col = func.coalesce(
        WorkOrder.related_department_id,
        db.session.query(User.department_id)
        .filter(User.id == WorkOrder.leader_id).scalar_subquery(),
    )
    return query.filter(dept_col.in_(scope or [-1]))


@bp.route('/')
@login_required
def index():
    """工作台。"""
    scoped_orders = _scope_order_query()
    my_orders = scoped_orders.filter_by(leader_id=current_user.id).count()
    open_orders = (scoped_orders
                   .filter(WorkOrder.status.in_(['pending', 'in_progress']))
                   .order_by(WorkOrder.created_at.desc())
                   .limit(6).all())
    open_orders_count = (scoped_orders
                         .filter(WorkOrder.status.in_(['pending', 'in_progress']))
                         .count())
    unread = chat_service.unread_count(current_user.id)

    # P1-09 库存预警未读消息数
    warning_unread = 0
    try:
        from app.services.notification_service import unread_warning_count
        warning_unread = unread_warning_count(current_user.id)
    except Exception:
        pass

    # P1-01 待审批请假数（主管可见：本部门 pending，数据权限收窄）
    pending_leaves = None
    if has_permission(current_user, 'attendance.leave.approve'):
        scope = visible_department_ids(current_user)
        q = LeaveRequest.query.filter_by(status='pending')
        if scope is not None:
            q = q.filter(LeaveRequest.department_id.in_(scope or [-1]))
        pending_leaves = q.count()

    # 库存预警数：仅有库存查看权限时展示（P0 保留）
    warn_count = None
    if has_permission(current_user, 'warehouse.view'):
        warn_count = (Inventory.query
                      .filter(Inventory.quantity <= Inventory.warn_threshold)
                      .count())

    return render_template(
        'main/index.html',
        my_orders=my_orders,
        open_orders=open_orders,
        open_orders_count=open_orders_count,
        warn_count=warn_count,
        unread=unread,
        warning_unread=warning_unread,
        pending_leaves=pending_leaves,
        employee_count=User.query.filter_by(is_active=True).count(),
        material_count=Material.query.filter_by(is_active=True).count(),
    )
