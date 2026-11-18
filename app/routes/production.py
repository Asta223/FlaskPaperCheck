"""生产进度路由：工单 CRUD、工序流转、进度看板、工单领料、工单操作日志。

P1 数据权限：base_order_query() 单一出口注入部门过滤（related_department_id 为空回退负责人部门）。
"""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app import db
from app.forms.production import (DefectReasonForm, IssueForm, ProcessForm, QualityRecordForm,
                                  StepLaborForm, WorkOrderForm, WorkOrderStepForm,
                                  fill_defect_reason_choices, fill_department_choices,
                                  fill_issue_choices, fill_process_choices,
                                  fill_workorder_choices)
from app.models.production import DefectReason, Process, WorkOrder, WorkOrderStep
from app.models.system import OperationLog
from app.models.user import User
from app.models.warehouse import Inventory, StockDocument
from app.services.inventory_service import InsufficientStockError, InventoryServiceError, \
    apply_stock_document
from app.services.log_service import log_operation
from app.services.soft_delete_service import mark_deleted
from app.utils.data_scope import visible_department_ids
from app.utils.delete_guard import find_references, format_references
from app.utils.permissions import permission_required
from app.utils.time_utils import now

bp = Blueprint('production', __name__, url_prefix='/production')


# ---------------- 工序档案（P2：主数据统一维护，工单只能引用）----------------

UNFINISHED_ORDER_STATUSES = ('pending', 'in_progress')


def unfinished_order_refs(process_id):
    """引用该工序且所属工单仍未完结（待开始/进行中）的工单展示串列表。

    全局软删过滤自动排除已删除的工单与工序行；已完成/已验收工单属于历史快照，
    不再锁定工序主数据。
    """
    rows = (db.session.query(WorkOrder.order_no, WorkOrder.status)
            .join(WorkOrderStep, WorkOrderStep.work_order_id == WorkOrder.id)
            .filter(WorkOrderStep.process_id == process_id,
                    WorkOrder.status.in_(UNFINISHED_ORDER_STATUSES))
            .order_by(WorkOrder.id).all())
    return ['%s（%s）' % (order_no, WorkOrder.STATUS_LABELS.get(status, status))
            for order_no, status in rows]


def _guard_process_locked(process, action):
    """被未完结工单引用时禁止编辑/停用/删除；返回 True 表示已锁定。"""
    refs = unfinished_order_refs(process.id)
    if not refs:
        return False
    flash('工序「%s」已被未完结工单 %s 引用，禁止%s；请先将相关工单完结或移除该工序' % (
        process.name, '、'.join(refs[:5]), action), 'danger')
    return True


@bp.route('/processes')
@login_required
@permission_required('production.view')
def process_list():
    """工序档案列表：新增/编辑同页表单（与物料分类一致的交互）。"""
    edit_id = request.args.get('edit_id', type=int)
    process = db.session.get(Process, edit_id) if edit_id else None
    form = ProcessForm(obj=process) if process else ProcessForm()
    processes = Process.query.order_by(Process.sort_order, Process.id).all()
    locked = {p.id: unfinished_order_refs(p.id) for p in processes}
    return render_template('production/process_list.html', form=form, process=process,
                           processes=processes, locked=locked)


@bp.route('/processes/new', methods=['POST'])
@login_required
@permission_required('production.process.manage')
def process_new():
    """新增工序档案：编码/名称唯一（数据库约束 + 前置校验）。"""
    form = ProcessForm()
    if not form.validate_on_submit():
        flash('工序表单校验失败', 'danger')
        return redirect(url_for('production.process_list'))
    code = form.code.data.strip()
    name = form.name.data.strip()
    if Process.query.filter_by(code=code).first() or Process.query.filter_by(name=name).first():
        flash('工序编码或名称已存在', 'danger')
        return redirect(url_for('production.process_list'))
    db.session.add(Process(code=code, name=name,
                           standard_hours=form.standard_hours.data or 0,
                           sort_order=form.sort_order.data or 0,
                           remark=form.remark.data or ''))
    db.session.commit()
    flash('工序「%s」已创建' % name, 'success')
    return redirect(url_for('production.process_list'))


@bp.route('/processes/<int:process_id>/edit', methods=['POST'])
@login_required
@permission_required('production.process.manage')
def process_edit(process_id):
    """编辑工序档案：被未完结工单引用时禁止；历史步骤快照不回溯。"""
    process = db.get_or_404(Process, process_id)
    if _guard_process_locked(process, '编辑'):
        return redirect(url_for('production.process_list'))
    form = ProcessForm(obj=process)
    if not form.validate_on_submit():
        flash('工序表单校验失败', 'danger')
        return redirect(url_for('production.process_list'))
    code = form.code.data.strip()
    name = form.name.data.strip()
    duplicate = Process.query.filter(
        (Process.code == code) | (Process.name == name),
        Process.id != process.id,
    ).first()
    if duplicate:
        flash('工序编码或名称已存在', 'danger')
        return redirect(url_for('production.process_list'))
    process.code = code
    process.name = name
    process.standard_hours = form.standard_hours.data or 0
    process.sort_order = form.sort_order.data or 0
    process.remark = form.remark.data or ''
    db.session.commit()
    flash('工序已保存', 'success')
    return redirect(url_for('production.process_list'))


@bp.route('/processes/<int:process_id>/toggle', methods=['POST'])
@login_required
@permission_required('production.process.manage')
def process_toggle(process_id):
    """停用/启用工序：被未完结工单引用时禁止停用（启用不受限）。"""
    process = db.get_or_404(Process, process_id)
    if process.is_active and _guard_process_locked(process, '停用'):
        return redirect(url_for('production.process_list'))
    process.is_active = not process.is_active
    db.session.commit()
    flash('工序「%s」已%s' % (process.name, '启用' if process.is_active else '停用'),
          'success' if process.is_active else 'warning')
    return redirect(url_for('production.process_list'))


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
        exists = (WorkOrder.query.execution_options(include_deleted=True)
                  .filter_by(order_no=order_no).first())
        if not exists:
            return order_no
        seq += 1


@bp.route('/processes/<int:process_id>/delete', methods=['POST'])
@login_required
@permission_required('production.process.manage')
def process_delete(process_id):
    """软删除工序档案：被未完结工单引用时禁止；历史工单引用仍按引用守卫拒绝。"""
    process = db.get_or_404(Process, process_id)
    if _guard_process_locked(process, '删除'):
        return redirect(url_for('production.process_list'))
    refs = find_references(process)
    if refs:
        flash('工序「%s」仍被 %s 引用，不能删除；可先停用' % (
            process.name, format_references(refs)), 'danger')
        return redirect(url_for('production.process_list'))
    name = process.name
    mark_deleted(process, module='production', target_type='process',
                 summary='删除工序「%s」，可在回收站恢复' % name)
    flash('工序「%s」已删除，可在系统管理→回收站恢复' % name, 'success')
    return redirect(url_for('production.process_list'))


# ---------------- 不良原因主数据（P2-6：工单质量记录只能引用）----------------

@bp.route('/defect-reasons')
@login_required
@permission_required('production.view')
def defect_reason_list():
    """不良原因列表：新增/编辑同页表单（仅管理权限者可见表单）。"""
    edit_id = request.args.get('edit_id', type=int)
    reason = db.session.get(DefectReason, edit_id) if edit_id else None
    form = DefectReasonForm(obj=reason) if reason else DefectReasonForm()
    reasons = DefectReason.query.order_by(DefectReason.code, DefectReason.id).all()
    return render_template('production/defect_reason_list.html', form=form, reason=reason,
                           reasons=reasons)


def _duplicate_defect_reason(code, name, exclude_id=None):
    """唯一性只校验未删除记录（软删后允许重建同编码/名称）。"""
    query = DefectReason.query.filter(
        (DefectReason.code == code) | (DefectReason.name == name))
    if exclude_id:
        query = query.filter(DefectReason.id != exclude_id)
    return query.first()


@bp.route('/defect-reasons/new', methods=['POST'])
@login_required
@permission_required('production.defect_reason.manage')
def defect_reason_new():
    """新增不良原因：编码/名称唯一，防止同一原因多种写法。"""
    form = DefectReasonForm()
    if not form.validate_on_submit():
        flash('不良原因表单校验失败', 'danger')
        return redirect(url_for('production.defect_reason_list'))
    code = form.code.data.strip()
    name = form.name.data.strip()
    if _duplicate_defect_reason(code, name):
        flash('不良原因编码或名称已存在', 'danger')
        return redirect(url_for('production.defect_reason_list'))
    db.session.add(DefectReason(code=code, name=name,
                                category=form.category.data.strip() if form.category.data else '',
                                remark=form.remark.data or ''))
    db.session.commit()
    flash('不良原因「%s」已创建' % name, 'success')
    return redirect(url_for('production.defect_reason_list'))


@bp.route('/defect-reasons/<int:reason_id>/edit', methods=['POST'])
@login_required
@permission_required('production.defect_reason.manage')
def defect_reason_edit(reason_id):
    """编辑不良原因：历史质量记录按 id 引用，改名不影响历史。"""
    reason = db.get_or_404(DefectReason, reason_id)
    form = DefectReasonForm(obj=reason)
    if not form.validate_on_submit():
        flash('不良原因表单校验失败', 'danger')
        return redirect(url_for('production.defect_reason_list'))
    code = form.code.data.strip()
    name = form.name.data.strip()
    duplicate = _duplicate_defect_reason(code, name, exclude_id=reason.id)
    if duplicate:
        flash('不良原因编码或名称已存在', 'danger')
        return redirect(url_for('production.defect_reason_list'))
    reason.code = code
    reason.name = name
    reason.category = form.category.data.strip() if form.category.data else ''
    reason.remark = form.remark.data or ''
    db.session.commit()
    flash('不良原因已保存', 'success')
    return redirect(url_for('production.defect_reason_list'))


@bp.route('/defect-reasons/<int:reason_id>/toggle', methods=['POST'])
@login_required
@permission_required('production.defect_reason.manage')
def defect_reason_toggle(reason_id):
    """停用/启用不良原因：停用后不再出现在工单质量记录下拉。"""
    reason = db.get_or_404(DefectReason, reason_id)
    reason.is_active = not reason.is_active
    db.session.commit()
    flash('不良原因「%s」已%s' % (reason.name, '启用' if reason.is_active else '停用'),
          'success' if reason.is_active else 'warning')
    return redirect(url_for('production.defect_reason_list'))


@bp.route('/defect-reasons/<int:reason_id>/delete', methods=['POST'])
@login_required
@permission_required('production.defect_reason.manage')
def defect_reason_delete(reason_id):
    """软删除不良原因：已被引用的质量记录存在时拒绝，可从回收站恢复。"""
    reason = db.get_or_404(DefectReason, reason_id)
    refs = find_references(reason)
    if refs:
        flash('不良原因「%s」仍被 %s 引用，不能删除；可先停用' % (
            reason.name, format_references(refs)), 'danger')
        return redirect(url_for('production.defect_reason_list'))
    name = reason.name
    mark_deleted(reason, module='production', target_type='defect_reason',
                 summary='删除不良原因「%s」，可在回收站恢复' % name)
    flash('不良原因「%s」已删除，可在系统管理→回收站恢复' % name, 'success')
    return redirect(url_for('production.defect_reason_list'))


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


@bp.route('/orders/<int:order_id>/delete', methods=['POST'])
@login_required
@permission_required('production.manage')
def order_delete(order_id):
    """软删除工单：已有未删除的工序/领料记录时拒绝，可从回收站恢复。"""
    order = db.get_or_404(WorkOrder, order_id)
    refs = find_references(order)
    if refs:
        flash('工单 %s 仍被 %s 引用，不能删除' % (
            order.order_no, format_references(refs)), 'danger')
        return redirect(url_for('production.order_list'))
    order_no = order.order_no
    mark_deleted(order, module='production', target_type='work_order',
                 summary='删除工单 %s，可在回收站恢复' % order_no)
    flash('工单 %s 已删除，可在系统管理→回收站恢复' % order_no, 'success')
    return redirect(url_for('production.order_list'))


@bp.route('/orders/<int:order_id>')
@login_required
@permission_required('production.view')
def order_detail(order_id):
    """工单详情：信息 + 工序时间线 + 状态流转 + 物料领用 + 操作日志页签。"""
    order = db.get_or_404(WorkOrder, order_id)
    step_form = WorkOrderStepForm()
    fill_workorder_choices(step_form)
    fill_process_choices(step_form)
    if not step_form.seq.data:
        step_form.seq.data = len(order.steps) + 1
    # 工单总消耗工时
    total_hours = round(sum(s.labor_hours or 0 for s in order.steps), 2)
    quality_form = QualityRecordForm(obj=order)
    fill_defect_reason_choices(quality_form)
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
                           can_issue=order.status in ('pending', 'in_progress'),
                           can_run_steps=order.can_run_steps,
                           can_record_quality=order.status in ('in_progress', 'completed'),
                           total_hours=total_hours, labor_form=StepLaborForm(),
                           quality_form=quality_form)


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
    """为工单添加工序：下拉引用已维护的工序档案，名称做快照留痕。"""
    order = db.get_or_404(WorkOrder, order_id)
    form = WorkOrderStepForm()
    fill_workorder_choices(form)
    fill_process_choices(form)
    if form.validate_on_submit():
        process = db.session.get(Process, form.process_id.data)
        if process is None or not process.is_active:
            flash('所选工序不存在或已停用，请刷新后重试', 'danger')
            return redirect(url_for('production.order_detail', order_id=order.id))
        step = WorkOrderStep(
            work_order_id=order.id,
            process_id=process.id,
            name=process.name,  # 快照：工序日后改名不影响历史工单
            seq=form.seq.data,
            operator_id=form.operator_id.data or None,
            remark=form.remark.data or '',
        )
        db.session.add(step)
        db.session.commit()
        flash('工序「%s」已添加' % step.name, 'success')
    else:
        flash('请从下拉列表选择已维护的工序', 'danger')
    return redirect(url_for('production.order_detail', order_id=order.id))


@bp.route('/steps/<int:step_id>/status', methods=['POST'])
@login_required
@permission_required('production.manage')
def step_status(step_id):
    """工序状态流转（仅允许合法迁移），记录操作日志。"""
    step = db.get_or_404(WorkOrderStep, step_id)
    order = db.session.get(WorkOrder, step.work_order_id)
    if order is None:
        abort(404)
    if not order.can_run_steps:
        flash('工单处于「%s」状态，只有「进行中」工单才能执行工序流转；'
              '待开始工单请先流转工单状态' % WorkOrder.STATUS_LABELS.get(order.status, order.status),
              'danger')
        return redirect(url_for('production.order_detail', order_id=order.id))
    target = request.form.get('status', '')
    allowed = step.next_status()
    if target and target == allowed:
        old = step.status
        step.status = target
        if target == 'in_progress':
            step.started_at = now()
        elif target == 'completed':
            step.finished_at = now()
            step.labor_hours = step.auto_labor_hours()  # 自动算，之后可手动修正
            # 若未点过"开始"（历史数据），作兜底：按完成时刻单列 0 工时并记录
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


@bp.route('/steps/<int:step_id>/labor', methods=['POST'])
@login_required
@permission_required('production.manage')
def step_labor(step_id):
    """修正工序消耗工时（仅进行中工单；生产侧无审批，保存即生效并留操作日志）。"""
    step = db.get_or_404(WorkOrderStep, step_id)
    order = db.session.get(WorkOrder, step.work_order_id)
    if order is None:
        abort(404)
    if not order.can_run_steps:
        flash('只有「进行中」工单才能修正工序工时', 'danger')
        return redirect(url_for('production.order_detail', order_id=order.id))
    form = StepLaborForm()
    if form.validate_on_submit():
        old = step.labor_hours or 0
        step.labor_hours = form.labor_hours.data
        if form.remark.data is not None:
            step.remark = form.remark.data.strip()
        log_operation(module='production', action='update', target_type='work_order',
                      target_id=step.work_order_id,
                      summary='工序「%s」工时修正：%.2f → %.2f 小时' % (
                          step.name, old, step.labor_hours),
                      operator_id=current_user.id)
        db.session.commit()
        flash('工序「%s」工时已保存' % step.name, 'success')
    else:
        flash('工时数据不合法（须为不小于0的数字）', 'danger')
    return redirect(url_for('production.order_detail', order_id=step.work_order_id))


@bp.route('/orders/<int:order_id>/quality', methods=['POST'])
@login_required
@permission_required('production.manage')
def order_quality(order_id):
    """记录/修正工单质量数据（仅进行中/已完成；良率与不良率由服务端计算）。"""
    order = db.get_or_404(WorkOrder, order_id)
    if order.status not in ('in_progress', 'completed'):
        flash('只有「进行中」或「已完成」工单才能记录质量数据', 'danger')
        return redirect(url_for('production.order_detail', order_id=order.id))
    form = QualityRecordForm()
    fill_defect_reason_choices(form)
    if not form.validate_on_submit():
        flash('质量记录表单校验失败，请检查数量是否为不小于0的整数', 'danger')
        return redirect(url_for('production.order_detail', order_id=order.id))
    output_qty = form.output_qty.data or 0
    good_qty = form.good_qty.data or 0
    defect_qty = form.defect_qty.data or 0
    reason_id = form.defect_reason_id.data or None
    if reason_id:
        reason = db.session.get(DefectReason, reason_id)
        if reason is None or not reason.is_active:
            flash('所选不良原因不存在或已停用', 'danger')
            return redirect(url_for('production.order_detail', order_id=order.id))
    try:
        order.record_quality(output_qty, good_qty, defect_qty, reason_id,
                             form.quality_remark.data or '', current_user.id)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('production.order_detail', order_id=order.id))
    log_operation(module='production', action='update', target_type='work_order',
                  target_id=order.id, operator_id=current_user.id,
                  summary='工单 %s 质量记录：成品%s / 良品%s / 不良%s，良率%.2f%% 不良率%.2f%%' % (
                      order.order_no, output_qty, good_qty, defect_qty,
                      order.yield_rate, order.defect_rate))
    db.session.commit()
    flash('工单 %s 质量记录已保存' % order.order_no, 'success')
    return redirect(url_for('production.order_detail', order_id=order.id))


@bp.route('/steps/<int:step_id>/delete', methods=['POST'])
@login_required
@permission_required('production.manage')
def step_delete(step_id):
    """软删除工序（回收站可恢复）：仅待开始工单中的待开始工序允许删除。

    进行中工单已进入生产态，其工序（含尚未开始的）一律不允许删除；
    进行中/已完成的工序本身也不允许删除。
    """
    step = db.get_or_404(WorkOrderStep, step_id)
    order_id = step.work_order_id
    order = db.session.get(WorkOrder, order_id)
    if order is None:
        abort(404)
    if order.status == 'in_progress':
        flash('工单处于「进行中」状态，工序不允许删除；请先将工单流转至完成或待开始再调整',
              'danger')
    elif step.status != 'pending':
        flash('仅「待开始」工序可删除', 'danger')
    else:
        name = step.name
        mark_deleted(step, module='production', target_type='work_order_step',
                     summary='删除工单工序「%s」，可在回收站恢复' % name)
        flash('工序「%s」已删除，可在回收站恢复' % name, 'warning')
    return redirect(url_for('production.order_detail', order_id=order_id))


# ---------------- 工单领料（P1-05 / P2-03 余量显示 + 强校验）----------------

@bp.route('/api/stock')
@login_required
@permission_required('production.issue')
def api_stock():
    """领料弹窗联动：查询指定仓库+物料的当前可用余量（只读）。"""
    warehouse_id = request.args.get('warehouse_id', type=int)
    material_id = request.args.get('material_id', type=int)
    from app.models.warehouse import Warehouse
    from app.models.material import Material
    warehouse = db.session.get(Warehouse, warehouse_id) if warehouse_id else None
    material = db.session.get(Material, material_id) if material_id else None
    if warehouse is None or material is None:
        return jsonify(ok=False, available=0, message='请选择仓库和物料')
    row = (Inventory.query
           .filter_by(warehouse_id=warehouse.id, material_id=material.id).first())
    available = row.quantity if row else 0
    return jsonify(ok=True, available=available, warehouse=warehouse.name,
                   material=material.name)


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

    # P2-03 前置清晰提示：事务内仍有行锁强校验（防并发），此处只为给出可读反馈
    from app.models.material import Material
    from app.models.warehouse import Warehouse
    warehouse = db.session.get(Warehouse, form.warehouse_id.data)
    material = db.session.get(Material, form.material_id.data)
    if warehouse is None or not warehouse.is_active or material is None or not material.is_active:
        flash('仓库或物料不存在/已停用', 'danger')
        return redirect(url_for('production.order_detail', order_id=order.id))
    inv = (Inventory.query
           .filter_by(warehouse_id=warehouse.id, material_id=material.id).first())
    available = inv.quantity if inv else 0
    if form.quantity.data > available:
        flash('库存不足：【%s / %s】当前余量 %d，本次领料 %d，缺 %d' % (
            warehouse.name, material.name, available, form.quantity.data,
            form.quantity.data - available), 'danger')
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
                'summary': '工单 %s 领料：%s / %s ×%s' % (
                    order.order_no, warehouse.name, material.name, form.quantity.data),
            },
        )
    except InsufficientStockError as exc:
        # 并发兜底：前置校验通过后仍可能被其他事务抢先扣减
        flash('库存不足（并发变动），当前余量 %d，领料未成功' % exc.available, 'danger')
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
