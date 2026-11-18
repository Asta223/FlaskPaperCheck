"""系统通用路由（第 11 蓝图）：操作日志（P1-15）、回收站（软删除恢复）。"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app import db
from app.models.attendance import AttendanceRecord
from app.models.chat import ChatMessage
from app.models.file import FactoryFile, FileCategory
from app.models.leave import LeaveRequest
from app.models.material import Material, MaterialCategory
from app.models.org import Department
from app.models.production import DefectReason, Process, WorkOrder, WorkOrderStep
from app.models.rbac import Role
from app.models.system import OperationLog
from app.models.user import User
from app.models.warehouse import StockDocument, Warehouse
from app.services.inventory_service import InsufficientStockError, restore_stock_document
from app.services.soft_delete_service import restore_record
from app.utils.permissions import permission_required
from app.utils.time_utils import today

bp = Blueprint('system', __name__, url_prefix='/system')


def _describe(obj, type_key: str) -> str:
    """回收站展示摘要（短文本，便于管理员判断该不该恢复）。"""
    if type_key == 'user':
        return '%s（%s）' % (obj.display_name(), obj.employee_no)
    if type_key == 'work_order':
        return '%s %s' % (obj.order_no, obj.product_name)
    if type_key == 'work_order_step':
        return '%s（工单#%s）' % (obj.name, obj.work_order_id)
    if type_key == 'material':
        return '%s %s' % (obj.code, obj.name)
    if type_key == 'stock_document':
        return '%s %s ×%s' % (obj.doc_no, StockDocument.DOC_TYPE_LABELS.get(obj.doc_type, ''),
                             obj.quantity)
    if type_key == 'file':
        return obj.name
    if type_key == 'attendance_record':
        return '%s %s' % (obj.user.display_name() if obj.user else '未知员工', obj.work_date)
    if type_key == 'leave_request':
        return '%s %s' % (obj.applicant.display_name() if obj.applicant else '未知员工',
                          obj.leave_type)
    if type_key == 'chat_message':
        return '%s→%s：%s' % (obj.sender_id, obj.receiver_id, (obj.content or '')[:24])
    if type_key == 'process':
        return '%s %s' % (obj.code, obj.name)
    return getattr(obj, 'name', '') or getattr(obj, 'code', '') or '#%s' % obj.id


# 键顺序即回收站下拉顺序
RECYCLE_REGISTRY = {
    'user': (User, '员工', 'hr', 'employee', ('username', 'employee_no')),
    'department': (Department, '部门', 'hr', 'department', ()),
    'role': (Role, '角色', 'rbac', 'role', ('code',)),
    'process': (Process, '工序档案', 'production', 'process', ('code', 'name')),
    'defect_reason': (DefectReason, '不良原因', 'production', 'defect_reason', ('code', 'name')),
    'work_order': (WorkOrder, '生产工单', 'production', 'work_order', ('order_no',)),
    'work_order_step': (WorkOrderStep, '工单工序', 'production', 'work_order_step', ()),
    'material_category': (MaterialCategory, '物料分类', 'material', 'material_category', ()),
    'material': (Material, '物料', 'material', 'material', ('code',)),
    'warehouse': (Warehouse, '仓库', 'warehouse', 'warehouse', ('name',)),
    'stock_document': (StockDocument, '出入库单', 'warehouse', 'stock_document', ('doc_no',)),
    'file_category': (FileCategory, '文件分类', 'files', 'file_category', ()),
    'file': (FactoryFile, '文件', 'files', 'file', ()),
    'attendance_record': (AttendanceRecord, '打卡记录', 'attendance', 'attendance_record', ()),
    'leave_request': (LeaveRequest, '请假申请', 'attendance', 'leave_request', ()),
    'chat_message': (ChatMessage, '聊天消息', 'chat', 'chat_message', ()),
}


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


@bp.route('/recycle')
@login_required
@permission_required('system.recycle')
def recycle():
    """回收站：按类型列出is_deleted=True的记录（显式绕过全局软删过滤）。"""
    type_key = request.args.get('type', '')
    if type_key and type_key not in RECYCLE_REGISTRY:
        type_key = ''
    rows = []
    counts = {}
    for key, (model, label, _module, _target, _unique) in RECYCLE_REGISTRY.items():
        query = model.query.execution_options(include_deleted=True).filter_by(is_deleted=True)
        counts[key] = query.count()
        if type_key and key != type_key:
            continue
        for obj in query.order_by(model.id.desc()).limit(200).all():
            rows.append({
                'type': key, 'label': label, 'id': obj.id,
                'desc': _describe(obj, key),
            })
    rows.sort(key=lambda r: r['id'], reverse=True)
    return render_template('system/recycle.html', rows=rows, registry=RECYCLE_REGISTRY,
                           counts=counts, type_key=type_key)


def _include_deleted_get(model, obj_id):
    """按主键取已删除记录（绕过全局过滤）。"""
    stmt = select(model).where(model.id == obj_id).execution_options(include_deleted=True)
    return db.session.execute(stmt).scalar_one_or_none()


def _restore_conflict(model, obj, unique_fields) -> str:
    """恢复前校验唯一性；已删除记录不占用唯一键，只与未删除记录冲突。"""
    include_deleted = model in (WorkOrder, StockDocument)
    for field in unique_fields:
        value = getattr(obj, field, None)
        if not value:
            continue
        query = model.query
        if include_deleted:
            query = query.execution_options(include_deleted=True)
        exists = query.filter(getattr(model, field) == value).first()
        if exists is not None and exists.id != obj.id:
            return '%s=%s 已被其他记录占用' % (field, value)
    if model is AttendanceRecord:
        other = (AttendanceRecord.query
                 .filter_by(user_id=obj.user_id, work_date=obj.work_date).first())
        if other is not None and other.id != obj.id:
            return '该员工当天已有未删除的打卡记录'
    return ''


@bp.route('/recycle/<type_key>/<int:obj_id>/restore', methods=['POST'])
@login_required
@permission_required('system.recycle')
def recycle_restore(type_key, obj_id):
    """从回收站恢复记录；恢复单据时重新入账库存。"""
    cfg = RECYCLE_REGISTRY.get(type_key)
    if cfg is None:
        abort(404)
    model, label, module, target_type, unique_fields = cfg
    obj = _include_deleted_get(model, obj_id)
    if obj is None:
        abort(404)
    if not obj.is_deleted:
        flash('该记录未处于删除状态', 'warning')
        return redirect(url_for('system.recycle', type=type_key))

    conflict = _restore_conflict(model, obj, unique_fields)
    if conflict:
        flash('无法恢复：%s' % conflict, 'danger')
        return redirect(url_for('system.recycle', type=type_key))

    if model is StockDocument:
        from app.models.material import Material
        if db.session.get(Warehouse, obj.warehouse_id) is None or \
                db.session.get(Material, obj.material_id) is None:
            flash('仓库或物料已被删除/停用，无法恢复该单据', 'danger')
            return redirect(url_for('system.recycle', type=type_key))
        try:
            restore_stock_document(obj, current_user.id)
        except InsufficientStockError as exc:
            db.session.rollback()
            flash('库存不足（当前余量 %d），无法恢复该出库单' % exc.available, 'danger')
            return redirect(url_for('system.recycle', type=type_key))

    desc = _describe(obj, type_key)
    restore_record(obj, module=module, target_type=target_type,
                   summary='从回收站恢复%s：%s' % (label, desc))
    flash('%s「%s」已恢复' % (label, desc), 'success')
    return redirect(url_for('system.recycle', type=type_key))
