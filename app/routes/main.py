"""工作台首页：统计卡片 + 进行中工单简表 + 快捷入口。"""
from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.models.material import Material
from app.models.production import WorkOrder
from app.models.user import User
from app.models.warehouse import Inventory
from app.services import chat_service
from app.utils.permissions import has_permission

bp = Blueprint('main', __name__)


@bp.route('/')
@login_required
def index():
    """工作台。"""
    my_orders = WorkOrder.query.filter_by(leader_id=current_user.id).count()
    open_orders = (WorkOrder.query
                   .filter(WorkOrder.status.in_(['pending', 'in_progress']))
                   .order_by(WorkOrder.created_at.desc())
                   .limit(6).all())
    open_orders_count = (WorkOrder.query
                         .filter(WorkOrder.status.in_(['pending', 'in_progress']))
                         .count())
    unread = chat_service.unread_count(current_user.id)

    # 库存预警数：仅有库存查看权限时展示
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
        employee_count=User.query.filter_by(is_active=True).count(),
        material_count=Material.query.filter_by(is_active=True).count(),
    )
