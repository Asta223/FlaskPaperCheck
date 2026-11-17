"""系统通用路由（第 11 蓝图）：操作日志（P1-15，四维筛选只读分页）。"""
from flask import Blueprint, render_template, request
from flask_login import login_required

from app import db
from app.models.system import OperationLog
from app.models.user import User
from app.utils.permissions import permission_required
from app.utils.time_utils import today

bp = Blueprint('system', __name__, url_prefix='/system')


@bp.route('/logs')
@login_required
@permission_required('system.log.view')
def operation_logs():
    """操作日志：按模块/操作人/时间区间/动作筛选，倒序分页，只读。"""
    page = request.args.get('page', 1, type=int)
    module = (request.args.get('module') or '').strip()
    action = (request.args.get('action') or '').strip()
    operator_id = request.args.get('operator_id', type=int)
    # 首次进入默认今天；用户显式清空（date_from=）则不过滤，可查看全部历史
    date_from = request.args.get('date_from')
    date_from = (date_from or '').strip() if date_from is not None else today().isoformat()
    date_to = request.args.get('date_to')
    date_to = (date_to or '').strip() if date_to is not None else today().isoformat()

    query = OperationLog.query
    if module:
        query = query.filter(OperationLog.module == module)
    if action:
        query = query.filter(OperationLog.action == action)
    if operator_id:
        query = query.filter(OperationLog.operator_id == operator_id)
    if date_from:
        query = query.filter(OperationLog.created_at >= date_from + ' 00:00:00')
    if date_to:
        query = query.filter(OperationLog.created_at <= date_to + ' 23:59:59')
    pagination = query.order_by(OperationLog.created_at.desc(), OperationLog.id.desc()) \
        .paginate(page=page, per_page=20, error_out=False)

    modules = [row[0] for row in db.session.query(OperationLog.module)
               .distinct().order_by(OperationLog.module).all() if row[0]]
    operators = User.query.filter(User.id.in_(
        db.session.query(OperationLog.operator_id).filter(OperationLog.operator_id.isnot(None))
    )).order_by(User.employee_no).all()

    return render_template(
        'system/operation_log.html',
        pagination=pagination,
        module=module, action=action, operator_id=operator_id,
        date_from=date_from, date_to=date_to,
        modules=modules, operators=operators,
        action_labels=OperationLog.ACTION_LABELS,
    )
