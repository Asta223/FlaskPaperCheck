"""生产进度路由：工单 CRUD、工序流转、进度看板、工单领料、工单操作日志。

P1 数据权限：base_order_query() 单一出口注入部门过滤（related_department_id 为空回退负责人部门）。
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app import db
from app.forms.production import (IssueForm, WorkOrderForm, WorkOrderStepForm,
                                  fill_department_choices, fill_issue_choices,
                                  fill_workorder_choices)
from app.models.production import WorkOrder, WorkOrderStep
from app.models.system import OperationLog
from app.models.user import User
from app.models.warehouse import StockDocument
from app.services.inventory_service import InsufficientStockError, InventoryServiceError, \
    apply_stock_document
from app.services.log_service import log_operation
from app.utils.data_scope import visible_department_ids
from app.utils.permissions import permission_required
from app.utils.time_utils import now

bp = Blueprint('production', __name__, url_prefix='/production')


def base_order_query():
    """工单列表统一查询出口（P1 数据权限只改此处）。

    department 口径（A5）：coalesce(related_department_id, 负责人部门) IN scope。
    """
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


@bp.route('/orders')
@login_required
@permission_required('production.view')
def order_list():
    """工单列表：状态/负责人筛选 + 分页。"""
    status = request.args.get('status', '', type=str)
    leader_id = request.args.get('leader_id', type=int)
    page = request.args.get('page', 1, type=int)

    query = base_order_query()
    if status:
        query = query.filter(WorkOrder.status == status)
    if leader_id:
        query = query.filter(WorkOrder.leader_id == leader_id)
    pagination = query.order_by(WorkOrder.id.desc()).paginate(page=page, per_page=20,
                                                              error_out=False)
    return render_template('production/order_list.html', pagination=pagination, status=status,
                           leader_id=leader_id, status_labels=WorkOrder.STATUS_LABELS)


def _generate_order_no() -> str:
    """生成唯一单号：WO + 日期 + 3 位当日序号。"""
    date_str = now().strftime('%Y%m%d')
    seq = 1
    while True:
        order_no = 'WO%s%03d' % (date_str, seq)
        if not WorkOrder.query.filter_by(order_no=order_no).first():
            return order_no
        seq += 1


@bp.route('/orders/new', methods=['GET', 'POST'])
@login_required
@permission_required('production.manage')
def order_new():
    """新建工单。"""
    form = WorkOrderForm()
    fill_workorder_choices(form)
    fill_department_choices(form)
    if form.validate_on_submit():
        order = WorkOrder(
            order_no=_generate_order_no(),
            product_name=form.product_name.data.strip(),
            quantity=form.quantity.data,
            due_date=form.due_date.data,
            leader_id=form.leader_id.data or None,
            related_department_id=form.related_department_id.data or None,
            remark=form.remark.data or '',
            created_by=current_user.id,
        )
        db.session.add(order)
        db.session.flush()
        log_operation(module='production', action='create', target_type='work_order',
                      target_id=order.id, summary='创建工单 %s' % order.order_no)
        db.session.commit()
        flash('工单 %s 创建成功' % order.order_no, 'success')
        return redirect(url_for('production.order_detail', order_id=order.id))
    return render_template('production/order_form.html', form=form, title='新建工单')


@bp.route('/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('production.manage')
def order_edit(order_id):
    """编辑工单基础信息。"""
    order = db.get_or_404(WorkOrder, order_id)
    form = WorkOrderForm(obj=order)
    fill_workorder_choices(form)
    fill_department_choices(form)
    if form.validate_on_submit():
        order.product_name = form.product_name.data.strip()
        order.quantity = form.quantity.data
        order.due_date = form.due_date.data
        order.leader_id = form.leader_id.data or None
        order.related_department_id = form.related_department_id.data or None
        order.remark = form.remark.data or ''
        log_operation(module='production', action='update', target_type='work_order',
                      target_id=order.id, summary='编辑工单 %s' % order.order_no)
        db.session.commit()
        flash('工单已保存', 'success')
        return redirect(url_for('production.order_detail', order_id=order.id))
    return render_template('production/order_form.html', form=form, title='编辑工单',
                           target=order)


@bp.route('/orders/<int:order_id>')
@login_required
@permission_required('production.view')
def order_detail(order_id):
    """工单详情：信息 + 工序时间线 + 状态流转 + 物料领用 + 操作日志页签。"""
    order = db.get_or_404(WorkOrder, order_id)
    step_form = WorkOrderStepForm()
    fill_workorder_choices(step_form)
    if not step_form.seq.data:
        step_form.seq.data = len(order.steps) + 1
    issue_form = IssueForm()
    fill_issue_choices(issue_form)
    issue_docs = (StockDocument.query
                  .filter_by(related_order_id=order.id)
                  .order_by(StockDocument.created_at.desc()).all())
    op_logs = (OperationLog.query
               .filter_by(target_type='work_order', target_id=order.id)
               .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
               .limit(100).all())
    return render_template('production/order_detail.html', order=order, step_form=step_form,
                           status_labels=WorkOrder.STATUS_LABELS,
                           step_labels=WorkOrderStep.STATUS_LABELS,
                           issue_form=issue_form, issue_docs=issue_docs, op_logs=op_logs,
                           can_issue=order.status in ('pending', 'in_progress'))


@bp.route('/orders/<int:order_id>/status', methods=['POST'])
@login_required
@permission_required('production.manage')
def order_status(order_id):
    """工单状态流转（仅允许合法迁移），记录操作日志。"""
    order = db.get_or_404(WorkOrder, order_id)
    target = request.form.get('status', '')
    allowed = order.next_status()
    if target and target == allowed:
        old = order.status
        order.status = target
        log_operation(module='production', action='transition', target_type='work_order',
                      target_id=order.id,
                      summary='状态 %s → %s' % (
                          WorkOrder.STATUS_LABELS.get(old, old),
                          WorkOrder.STATUS_LABELS.get(target, target)))
        db.session.commit()
        flash('工单 %s 状态已流转为「%s」' % (order.order_no,
                                            WorkOrder.STATUS_LABELS.get(target, target)), 'success')
    else:
        flash('非法的状态流转：%s → %s' % (WorkOrder.STATUS_LABELS.get(order.status, order.status),
                                         WorkOrder.STATUS_LABELS.get(target, target or '空')), 'danger')
    return redirect(url_for('production.order_detail', order_id=order.id))


@bp.route('/orders/<int:order_id>/steps/new', methods=['POST'])
@login_required
@permission_required('production.manage')
def step_new(order_id):
    """为工单添加工序。"""
    order = db.get_or_404(WorkOrder, order_id)
    form = WorkOrderStepForm()
    fill_workorder_choices(form)
    if form.validate_on_submit():
        step = WorkOrderStep(
            work_order_id=order.id,
            name=form.name.data.strip(),
            seq=form.seq.data,
            operator_id=form.operator_id.data or None,
            remark=form.remark.data or '',
        )
        db.session.add(step)
        db.session.commit()
        flash('工序「%s」已添加' % step.name, 'success')
    else:
        flash('工序表单校验失败', 'danger')
    return redirect(url_for('production.order_detail', order_id=order.id))


@bp.route('/steps/<int:step_id>/status', methods=['POST'])
@login_required
@permission_required('production.manage')
def step_status(step_id):
    """工序状态流转（仅允许合法迁移），记录操作日志。"""
    step = db.get_or_404(WorkOrderStep, step_id)
    target = request.form.get('status', '')
    allowed = step.next_status()
    if target and target == allowed:
        old = step.status
        step.status = target
        if target == 'in_progress':
            step.started_at = now()
        elif target == 'completed':
            step.finished_at = now()
        log_operation(module='production', action='transition', target_type='work_order',
                      target_id=step.work_order_id,
                      summary='工序「%s」%s → %s' % (
                          step.name,
                          WorkOrderStep.STATUS_LABELS.get(old, old),
                          WorkOrderStep.STATUS_LABELS.get(target, target)))
        db.session.commit()
        flash('工序「%s」状态已流转为「%s」' % (step.name,
                                             WorkOrderStep.STATUS_LABELS.get(target, target)), 'success')
    else:
        flash('非法的工序状态流转', 'danger')
    return redirect(url_for('production.order_detail', order_id=step.work_order_id))


@bp.route('/steps/<int:step_id>/delete', methods=['POST'])
@login_required
@permission_required('production.manage')
def step_delete(step_id):
    """删除未开始的工序。"""
    step = db.get_or_404(WorkOrderStep, step_id)
    order_id = step.work_order_id
    if step.status != 'pending':
        flash('仅「待开始」工序可删除', 'danger')
    else:
        db.session.delete(step)
        db.session.commit()
        flash('工序「%s」已删除' % step.name, 'warning')
    return redirect(url_for('production.order_detail', order_id=order_id))


# ---------------- 工单领料（P1-05）----------------

@bp.route('/orders/<int:order_id>/issue', methods=['POST'])
@login_required
@permission_required('production.issue')
def order_issue(order_id):
    """领料：复用库存事务（出库+流水+工单日志三步原子）。已完成/已验收工单禁止。"""
    order = db.get_or_404(WorkOrder, order_id)
    if order.status not in ('pending', 'in_progress'):
        flash('工单已%s，不能领料' % WorkOrder.STATUS_LABELS.get(order.status, order.status),
              'danger')
        return redirect(url_for('production.order_detail', order_id=order.id))

    form = IssueForm()
    fill_issue_choices(form)
    if not form.validate_on_submit():
        flash('领料表单校验失败', 'danger')
        return redirect(url_for('production.order_detail', order_id=order.id))

    try:
        apply_stock_document(
            doc_type='out',
            warehouse_id=form.warehouse_id.data,
            material_id=form.material_id.data,
            quantity=form.quantity.data,
            handler_id=current_user.id,
            created_by=current_user.id,
            related_order_id=order.id,
            remark=form.remark.data or '工单领料',
            work_order_log={
                'order_id': order.id,
                'operator_id': current_user.id,
                'summary': '工单 %s 领料：物料#%s ×%s' % (
                    order.order_no, form.material_id.data, form.quantity.data),
            },
        )
    except InsufficientStockError as exc:
        flash('库存不足，当前余量 %d，领料未成功' % exc.available, 'danger')
    except InventoryServiceError as exc:
        flash(str(exc), 'danger')
    else:
        flash('领料成功，已关联工单 %s' % order.order_no, 'success')
    return redirect(url_for('production.order_detail', order_id=order.id))


@bp.route('/board')
@login_required
@permission_required('production.view')
def board():
    """进度看板：按状态分列卡片（数据权限收窄）。"""
    orders = base_order_query().order_by(WorkOrder.id.desc()).all()
    columns = [
        (status, WorkOrder.STATUS_LABELS[status],
         [o for o in orders if o.status == status])
        for status in ('pending', 'in_progress', 'completed', 'accepted')
    ]
    return render_template('production/board.html', columns=columns,
                           status_labels=WorkOrder.STATUS_LABELS,
                           step_labels=WorkOrderStep.STATUS_LABELS)
