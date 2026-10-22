"""生产进度路由：工单 CRUD、工序流转、进度看板。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.production import WorkOrderForm, WorkOrderStepForm, fill_workorder_choices
from app.models.production import WorkOrder, WorkOrderStep
from app.utils.permissions import permission_required
from app.utils.time_utils import now

bp = Blueprint('production', __name__, url_prefix='/production')


def base_order_query():
    """工单列表统一查询出口（P1 数据权限只改此处）。"""
    return WorkOrder.query


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
    if form.validate_on_submit():
        order = WorkOrder(
            order_no=_generate_order_no(),
            product_name=form.product_name.data.strip(),
            quantity=form.quantity.data,
            due_date=form.due_date.data,
            leader_id=form.leader_id.data or None,
            remark=form.remark.data or '',
            created_by=current_user.id,
        )
        db.session.add(order)
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
    if form.validate_on_submit():
        order.product_name = form.product_name.data.strip()
        order.quantity = form.quantity.data
        order.due_date = form.due_date.data
        order.leader_id = form.leader_id.data or None
        order.remark = form.remark.data or ''
        db.session.commit()
        flash('工单已保存', 'success')
        return redirect(url_for('production.order_detail', order_id=order.id))
    return render_template('production/order_form.html', form=form, title='编辑工单',
                           target=order)


@bp.route('/orders/<int:order_id>')
@login_required
@permission_required('production.view')
def order_detail(order_id):
    """工单详情：工单信息 + 工序时间线 + 状态流转。"""
    order = db.get_or_404(WorkOrder, order_id)
    step_form = WorkOrderStepForm()
    fill_workorder_choices(step_form)
    if not step_form.seq.data:
        step_form.seq.data = len(order.steps) + 1
    return render_template('production/order_detail.html', order=order, step_form=step_form,
                           status_labels=WorkOrder.STATUS_LABELS,
                           step_labels=WorkOrderStep.STATUS_LABELS)


@bp.route('/orders/<int:order_id>/status', methods=['POST'])
@login_required
@permission_required('production.manage')
def order_status(order_id):
    """工单状态流转（仅允许合法迁移）。"""
    order = db.get_or_404(WorkOrder, order_id)
    target = request.form.get('status', '')
    allowed = order.next_status()
    if target and target == allowed:
        order.status = target
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
    """工序状态流转（仅允许合法迁移）。"""
    step = db.get_or_404(WorkOrderStep, step_id)
    target = request.form.get('status', '')
    allowed = step.next_status()
    if target and target == allowed:
        step.status = target
        if target == 'in_progress':
            step.started_at = now()
        elif target == 'completed':
            step.finished_at = now()
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


@bp.route('/board')
@login_required
@permission_required('production.view')
def board():
    """进度看板：按状态分列卡片。"""
    orders = WorkOrder.query.order_by(WorkOrder.id.desc()).all()
    columns = [
        (status, WorkOrder.STATUS_LABELS[status],
         [o for o in orders if o.status == status])
        for status in ('pending', 'in_progress', 'completed', 'accepted')
    ]
    return render_template('production/board.html', columns=columns,
                           status_labels=WorkOrder.STATUS_LABELS,
                           step_labels=WorkOrderStep.STATUS_LABELS)
