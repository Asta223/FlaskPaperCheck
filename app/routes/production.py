"""生产进度路由：工单 CRUD、工序流转、进度看板、工单领料、工单操作日志。

P1 数据权限：base_order_query() 单一出口注入部门过滤（related_department_id 为空回退负责人部门）。
"""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app import db
from app.forms.partner import CustomerForm
from app.forms.production import (DefectReasonForm, IssueForm, ProcessForm, ProductForm,
                                  ProcessRouteForm, QualityRecordForm, StepLaborForm,
                                  WorkOrderForm, WorkOrderStepForm, fill_defect_reason_choices,
                                  fill_department_choices, fill_customer_choices,
                                  fill_issue_choices,
                                  fill_process_choices, fill_product_choices,
                                  fill_route_choices, fill_workorder_choices)
from app.models.material import Material
from app.models.partner import Customer
from app.models.production import (BomItem, DefectReason, PRIORITY_LABELS, Process, Product,
                                   ProcessRoute, ProcessRouteItem, WorkOrder, WorkOrderStep)
from app.models.system import OperationLog
from app.models.user import User
from app.models.warehouse import Inventory, StockDocument
from app.services.inventory_service import InsufficientStockError, InventoryServiceError, \
    apply_stock_document
from app.services.log_service import log_operation
from app.services.scheduling_service import apply_plan, plan_status, sum_standard_hours
from app.services.soft_delete_service import mark_deleted
from app.services.unit_service import UnitConversionError, resolve_base_quantity
from app.utils.data_scope import visible_department_ids
from app.utils.delete_guard import find_references, format_references
from app.utils.permissions import permission_required
from app.utils.time_utils import now

bp = Blueprint('production', __name__, url_prefix='/production')

# 工单详情页签：info=工单资料 / steps=工序 / logs=操作日志
DETAIL_TABS = ('info', 'steps', 'logs')

# 看板条形图配色（与看板列头徽章保持一致）
BOARD_BAR_CLASSES = {
    'pending': 'bg-secondary', 'in_progress': 'bg-primary',
    'completed': 'bg-success', 'accepted': 'bg-dark',
}


def detail_tab() -> str:
    """读取并校验当前详情页签，非法值回退 info。"""
    tab = request.args.get('tab')
    return tab if tab in DETAIL_TABS else 'info'


def detail_redirect(order_id):
    """重定向回工单详情并保留页签（默认 info 不写 URL 参数）。"""
    tab = detail_tab()
    if tab == 'info':
        return redirect(url_for('production.order_detail', order_id=order_id))
    return redirect(url_for('production.order_detail', order_id=order_id, tab=tab))


# ---------------- 工序档案（P2：主数据统一维护，工单只能引用）----------------

UNFINISHED_ORDER_STATUSES = ('pending', 'in_progress')

# L1 计划结果提示（flash 与操作日志共用，避免两处文案分叉）
PLAN_RESULT_MESSAGES = {
    'auto': '已按交期自动倒排',
    'manual': '已保存人工计划日期',
    'unavailable': '未维护工序参考工时或无交期，计划日期留空',
}


def plan_result_text(result, order) -> str:
    """计划结果的中文提示（含日期），供 flash 与日志摘要复用。"""
    base = PLAN_RESULT_MESSAGES.get(result, result)
    if result == 'unavailable':
        return base
    return '%s（计划开工 %s，计划完工 %s）' % (
        base, order.plan_start_date or '-', order.plan_end_date or '-')


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
    plan_status_map = {o.id: plan_status(o) for o in pagination.items}
    return render_template('production/order_list.html', pagination=pagination, status=status,
                           leader_id=leader_id, status_labels=WorkOrder.STATUS_LABELS,
                           priority_labels=PRIORITY_LABELS, plan_status_map=plan_status_map)


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


# ---------------- 产品档案与 BOM（单层用料清单，工单/路线只引用不手输）----------------

def _duplicate_product(code, name, exclude_id=None):
    """产品编号/名称唯一性只校验未删除记录（与工序/路线口径一致）。"""
    query = Product.query.filter((Product.code == code) | (Product.name == name))
    if exclude_id:
        query = query.filter(Product.id != exclude_id)
    return query.first()


def _save_bom_items(product):
    """按勾选物料与单件用量物理替换 BOM 明细；返回 (错误提示, 明细数)。"""
    seen = set()
    picked = []
    for mid in request.form.getlist('material_ids', type=int):
        if not mid or mid in seen:
            continue
        seen.add(mid)
        material = db.session.get(Material, mid)
        if material is None or not material.is_active:
            return '所选物料不存在或已停用，请刷新后重试', 0
        qty = request.form.get('qty_%d' % mid, type=float)
        if qty is None or qty <= 0:
            return '物料「%s」的单件用量必须大于 0' % material.name, 0
        # 单位取自物料档案做快照，后续物料改单位不影响历史 BOM 读数
        picked.append((mid, qty, material.unit or ''))
    BomItem.query.filter_by(product_id=product.id).delete(synchronize_session=False)
    db.session.add_all([
        BomItem(product_id=product.id, material_id=mid, quantity=qty, unit=unit)
        for mid, qty, unit in picked
    ])
    db.session.expire(product, ['bom_items'])
    return None, len(picked)


@bp.route('/products')
@login_required
@permission_required('production.view')
def product_list():
    """产品档案列表 + 新增/编辑同页表单（含 BOM 用料明细）。"""
    edit_id = request.args.get('edit_id', type=int)
    product = db.session.get(Product, edit_id) if edit_id else None
    form = ProductForm(obj=product)
    products = Product.query.order_by(Product.code, Product.id).all()
    materials = Material.query.filter_by(is_active=True).order_by(Material.code).all()
    selected = ({item.material_id: (item.quantity, item.unit)
                 for item in product.bom_items} if product else {})
    return render_template('production/product_list.html', form=form, product=product,
                           products=products, materials=materials, selected=selected)


@bp.route('/products/new', methods=['POST'])
@login_required
@permission_required('production.product.manage')
def product_new():
    form = ProductForm()
    if not form.validate_on_submit():
        flash('产品档案表单校验失败', 'danger')
        return redirect(url_for('production.product_list'))
    code, name = form.code.data.strip(), form.name.data.strip()
    if _duplicate_product(code, name):
        flash('产品编号或名称已存在', 'danger')
        return redirect(url_for('production.product_list'))
    product = Product(code=code, name=name, spec=(form.spec.data or '').strip(),
                      unit=(form.unit.data or '个').strip(), remark=form.remark.data or '')
    db.session.add(product)
    db.session.flush()
    error, item_count = _save_bom_items(product)
    if error:
        db.session.rollback()
        flash(error, 'danger')
        return redirect(url_for('production.product_list'))
    log_operation(module='production', action='create', target_type='product',
                  target_id=product.id,
                  summary='创建产品「%s」，含 %d 条 BOM 用料' % (name, item_count))
    db.session.commit()
    flash('产品「%s」已创建，含 %d 条 BOM 用料' % (name, item_count), 'success')
    return redirect(url_for('production.product_list'))


@bp.route('/products/<int:product_id>/edit', methods=['POST'])
@login_required
@permission_required('production.product.manage')
def product_edit(product_id):
    product = db.get_or_404(Product, product_id)
    form = ProductForm(obj=product)
    if not form.validate_on_submit():
        flash('产品档案表单校验失败', 'danger')
        return redirect(url_for('production.product_list'))
    code, name = form.code.data.strip(), form.name.data.strip()
    if _duplicate_product(code, name, exclude_id=product.id):
        flash('产品编号或名称已存在', 'danger')
        return redirect(url_for('production.product_list'))
    product.code = code
    product.name = name
    product.spec = (form.spec.data or '').strip()
    product.unit = (form.unit.data or '个').strip()
    product.remark = form.remark.data or ''
    error, item_count = _save_bom_items(product)
    if error:
        db.session.rollback()
        flash(error, 'danger')
        return redirect(url_for('production.product_list'))
    log_operation(module='production', action='update', target_type='product',
                  target_id=product.id,
                  summary='保存产品「%s」，含 %d 条 BOM 用料' % (name, item_count))
    db.session.commit()
    flash('产品「%s」已保存' % name, 'success')
    return redirect(url_for('production.product_list'))


@bp.route('/products/<int:product_id>/toggle', methods=['POST'])
@login_required
@permission_required('production.product.manage')
def product_toggle(product_id):
    product = db.get_or_404(Product, product_id)
    product.is_active = not product.is_active
    db.session.commit()
    flash('产品「%s」已%s' % (product.name, '启用' if product.is_active else '停用'),
          'success' if product.is_active else 'warning')
    return redirect(url_for('production.product_list'))


@bp.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
@permission_required('production.product.manage')
def product_delete(product_id):
    """软删产品：BOM 明细同步隐藏；历史工单靠名称快照照常显示，不受影响。"""
    product = db.get_or_404(Product, product_id)
    for item in (BomItem.query.execution_options(include_deleted=True)
                 .filter_by(product_id=product.id).all()):
        item.is_deleted = True
    name = product.name
    mark_deleted(product, module='production', target_type='product',
                 summary='删除产品「%s」，可在回收站恢复' % name)
    flash('产品「%s」已删除，可在系统管理→回收站恢复' % name, 'success')
    return redirect(url_for('production.product_list'))


# ---------------- 客户档案（工单的下单方，名称写快照）----------------

def _duplicate_partner(model, code, name, exclude_id=None):
    """客户/供应商编码或名称唯一性只校验未删除记录。"""
    query = model.query.filter((model.code == code) | (model.name == name))
    if exclude_id:
        query = query.filter(model.id != exclude_id)
    return query.first()


@bp.route('/customers')
@login_required
@permission_required('production.view')
def customer_list():
    """客户档案列表 + 新增/编辑同页表单。"""
    edit_id = request.args.get('edit_id', type=int)
    customer = db.session.get(Customer, edit_id) if edit_id else None
    form = CustomerForm(obj=customer)
    customers = Customer.query.order_by(Customer.code, Customer.id).all()
    return render_template('production/customer_list.html', form=form, customer=customer,
                           customers=customers)


@bp.route('/customers/new', methods=['POST'])
@login_required
@permission_required('production.customer.manage')
def customer_new():
    form = CustomerForm()
    if not form.validate_on_submit():
        flash('客户档案表单校验失败', 'danger')
        return redirect(url_for('production.customer_list'))
    code, name = form.code.data.strip(), form.name.data.strip()
    if _duplicate_partner(Customer, code, name):
        flash('客户编号或名称已存在', 'danger')
        return redirect(url_for('production.customer_list'))
    customer = Customer(code=code, name=name, contact=(form.contact.data or '').strip(),
                        phone=(form.phone.data or '').strip(),
                        address=(form.address.data or '').strip(),
                        tax_no=(form.tax_no.data or '').strip(), remark=form.remark.data or '')
    db.session.add(customer)
    log_operation(module='production', action='create', target_type='customer',
                  target_id=customer.id, summary='创建客户「%s」' % name)
    db.session.commit()
    flash('客户「%s」已创建' % name, 'success')
    return redirect(url_for('production.customer_list'))


@bp.route('/customers/<int:customer_id>/edit', methods=['POST'])
@login_required
@permission_required('production.customer.manage')
def customer_edit(customer_id):
    customer = db.get_or_404(Customer, customer_id)
    form = CustomerForm(obj=customer)
    if not form.validate_on_submit():
        flash('客户档案表单校验失败', 'danger')
        return redirect(url_for('production.customer_list'))
    code, name = form.code.data.strip(), form.name.data.strip()
    if _duplicate_partner(Customer, code, name, exclude_id=customer.id):
        flash('客户编号或名称已存在', 'danger')
        return redirect(url_for('production.customer_list'))
    customer.code = code
    customer.name = name
    customer.contact = (form.contact.data or '').strip()
    customer.phone = (form.phone.data or '').strip()
    customer.address = (form.address.data or '').strip()
    customer.tax_no = (form.tax_no.data or '').strip()
    customer.remark = form.remark.data or ''
    log_operation(module='production', action='update', target_type='customer',
                  target_id=customer.id, summary='保存客户「%s」' % name)
    db.session.commit()
    flash('客户「%s」已保存' % name, 'success')
    return redirect(url_for('production.customer_list'))


@bp.route('/customers/<int:customer_id>/toggle', methods=['POST'])
@login_required
@permission_required('production.customer.manage')
def customer_toggle(customer_id):
    customer = db.get_or_404(Customer, customer_id)
    customer.is_active = not customer.is_active
    db.session.commit()
    flash('客户「%s」已%s' % (customer.name, '启用' if customer.is_active else '停用'),
          'success' if customer.is_active else 'warning')
    return redirect(url_for('production.customer_list'))


@bp.route('/customers/<int:customer_id>/delete', methods=['POST'])
@login_required
@permission_required('production.customer.manage')
def customer_delete(customer_id):
    """软删客户：历史工单靠名称快照显示，不受影响。"""
    customer = db.get_or_404(Customer, customer_id)
    name = customer.name
    mark_deleted(customer, module='production', target_type='customer',
                 summary='删除客户「%s」，可在回收站恢复' % name)
    flash('客户「%s」已删除，可在系统管理→回收站恢复' % name, 'success')
    return redirect(url_for('production.customer_list'))


# ---------------- 工艺路线（工序组：工单新建时可一键批量生成工序）----------------

def _duplicate_route(code, name, exclude_id=None):
    """路线编码/名称唯一性只校验未删除记录（与工序口径一致）。"""
    query = ProcessRoute.query.filter(
        (ProcessRoute.code == code) | (ProcessRoute.name == name))
    if exclude_id:
        query = query.filter(ProcessRoute.id != exclude_id)
    return query.first()


def _save_route_items(route):
    """按勾选工序与顺序号物理替换路线明细；返回 (错误提示, 明细数)。"""
    seen = set()
    picked = []
    for pid in request.form.getlist('process_ids', type=int):
        if not pid or pid in seen:
            continue
        seen.add(pid)
        process = db.session.get(Process, pid)
        if process is None or not process.is_active:
            return '所选工序不存在或已停用，请刷新后重试', 0
        seq = request.form.get('seq_%d' % pid, type=int) or (len(picked) + 1)
        if seq < 1:
            seq = len(picked) + 1
        picked.append((seq, pid))
    picked.sort(key=lambda item: (item[0], item[1]))
    # 明细无审计要求，物理替换即可；避免软删旧行占用 (route_id, seq) 唯一键
    ProcessRouteItem.query.filter_by(route_id=route.id).delete(synchronize_session=False)
    db.session.add_all([
        ProcessRouteItem(route_id=route.id, process_id=pid, seq=index + 1)
        for index, (_, pid) in enumerate(picked)
    ])
    db.session.expire(route, ['items'])
    return None, len(picked)


@bp.route('/process-routes')
@login_required
@permission_required('production.view')
def process_route_list():
    """工艺路线列表 + 新增/编辑同页表单。"""
    edit_id = request.args.get('edit_id', type=int)
    route = db.session.get(ProcessRoute, edit_id) if edit_id else None
    form = ProcessRouteForm(obj=route) if route else ProcessRouteForm()
    fill_product_choices(form)
    if route and route.product_id and all(
            c[0] != route.product_id for c in form.product_id.choices):
        form.product_id.choices.append(
            (route.product_id, '%s（已停用）' % (route.product.name if route.product
                                              else route.product_name)))
    routes = ProcessRoute.query.order_by(ProcessRoute.code, ProcessRoute.id).all()
    processes = (Process.query.filter_by(is_active=True)
                 .order_by(Process.sort_order, Process.id).all())
    selected = {item.process_id: item.seq for item in route.items} if route else {}
    return render_template('production/process_route_list.html', form=form, route=route,
                           routes=routes, processes=processes, selected=selected)


@bp.route('/process-routes/new', methods=['POST'])
@login_required
@permission_required('production.route.manage')
def process_route_new():
    form = ProcessRouteForm()
    fill_product_choices(form)
    if not form.validate_on_submit():
        flash('工艺路线表单校验失败', 'danger')
        return redirect(url_for('production.process_route_list'))
    code, name = form.code.data.strip(), form.name.data.strip()
    if _duplicate_route(code, name):
        flash('工艺路线编码或名称已存在', 'danger')
        return redirect(url_for('production.process_route_list'))
    product = db.session.get(Product, form.product_id.data) if form.product_id.data else None
    route = ProcessRoute(code=code, name=name,
                         product_id=product.id if product else None,
                         product_name=(product.name if product
                                       else (form.product_name.data or '').strip()),
                         remark=form.remark.data or '')
    db.session.add(route)
    db.session.flush()
    error, item_count = _save_route_items(route)
    if error:
        db.session.rollback()
        flash(error, 'danger')
        return redirect(url_for('production.process_route_list'))
    log_operation(module='production', action='create', target_type='process_route',
                  target_id=route.id,
                  summary='创建工艺路线「%s」，含 %d 道工序' % (name, item_count))
    db.session.commit()
    flash('工艺路线「%s」已创建，含 %d 道工序' % (name, item_count), 'success')
    return redirect(url_for('production.process_route_list'))


@bp.route('/process-routes/<int:route_id>/edit', methods=['POST'])
@login_required
@permission_required('production.route.manage')
def process_route_edit(route_id):
    route = db.get_or_404(ProcessRoute, route_id)
    form = ProcessRouteForm(obj=route)
    fill_product_choices(form)
    if not form.validate_on_submit():
        flash('工艺路线表单校验失败', 'danger')
        return redirect(url_for('production.process_route_list'))
    code, name = form.code.data.strip(), form.name.data.strip()
    if _duplicate_route(code, name, exclude_id=route.id):
        flash('工艺路线编码或名称已存在', 'danger')
        return redirect(url_for('production.process_route_list'))
    product = db.session.get(Product, form.product_id.data) if form.product_id.data else None
    route.code = code
    route.name = name
    route.product_id = product.id if product else None
    route.product_name = (product.name if product
                          else (form.product_name.data or '').strip())
    route.remark = form.remark.data or ''
    error, item_count = _save_route_items(route)
    if error:
        db.session.rollback()
        flash(error, 'danger')
        return redirect(url_for('production.process_route_list'))
    log_operation(module='production', action='update', target_type='process_route',
                  target_id=route.id,
                  summary='保存工艺路线「%s」，含 %d 道工序' % (name, item_count))
    db.session.commit()
    flash('工艺路线已保存', 'success')
    return redirect(url_for('production.process_route_list'))


@bp.route('/process-routes/<int:route_id>/toggle', methods=['POST'])
@login_required
@permission_required('production.route.manage')
def process_route_toggle(route_id):
    route = db.get_or_404(ProcessRoute, route_id)
    route.is_active = not route.is_active
    db.session.commit()
    flash('工艺路线「%s」已%s' % (route.name, '启用' if route.is_active else '停用'),
          'success' if route.is_active else 'warning')
    return redirect(url_for('production.process_route_list'))


@bp.route('/process-routes/<int:route_id>/delete', methods=['POST'])
@login_required
@permission_required('production.route.manage')
def process_route_delete(route_id):
    """软删除路线：明细同步隐藏（回收站恢复时一并恢复）。"""
    route = db.get_or_404(ProcessRoute, route_id)
    for item in (ProcessRouteItem.query
                 .execution_options(include_deleted=True)
                 .filter_by(route_id=route.id).all()):
        item.is_deleted = True
    name = route.name
    mark_deleted(route, module='production', target_type='process_route',
                 summary='删除工艺路线「%s」，可在回收站恢复' % name)
    flash('工艺路线「%s」已删除，可在系统管理→回收站恢复' % name, 'success')
    return redirect(url_for('production.process_route_list'))


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
    fill_product_choices(form)
    fill_customer_choices(form)
    fill_route_choices(form)
    route_product_map = {
        r.id: r.product_id for r in ProcessRoute.query.filter_by(is_active=True).all()
    }
    if form.validate_on_submit():
        # 产品档案与产品名称二选一：选了档案则名称自动带出，未建档才需手输
        if not form.product_id.data and not (form.product_name.data or '').strip():
            flash('请选择产品档案；产品尚未建档时才需手工填写产品名称', 'danger')
            return render_template('production/order_form.html', form=form, title='新建工单',
                                   priority_labels=PRIORITY_LABELS, show_route=True,
                                   route_product_map=route_product_map)
        manual_start = form.plan_start_date.data
        manual_end = form.plan_end_date.data
        # L1 覆盖判定：两个计划日期只要有一个非空即视为人工，此时两个都必须填
        if (manual_start is None) != (manual_end is None):
            flash('人工指定计划日期时，计划开工日与计划完工日必须同时填写；'
                  '两个都留空则由系统按交期自动倒排', 'danger')
            return render_template('production/order_form.html', form=form, title='新建工单',
                                   priority_labels=PRIORITY_LABELS, show_route=True,
                                   route_product_map=route_product_map)
        product = db.session.get(Product, form.product_id.data) if form.product_id.data else None
        if product is not None and not product.is_active:
            flash('所选产品已停用，请刷新页面重新选择', 'danger')
            return render_template('production/order_form.html', form=form, title='新建工单',
                                   priority_labels=PRIORITY_LABELS, show_route=True,
                                   route_product_map=route_product_map)
        customer = (db.session.get(Customer, form.customer_id.data)
                    if form.customer_id.data else None)
        if customer is not None and not customer.is_active:
            flash('所选客户已停用，请刷新页面重新选择', 'danger')
            return render_template('production/order_form.html', form=form, title='新建工单',
                                   priority_labels=PRIORITY_LABELS, show_route=True,
                                   route_product_map=route_product_map)
        order = WorkOrder(
            order_no=_generate_order_no(),
            product_id=product.id if product else None,
            # 名称写快照：产品后续改名不影响历史工单（与工序名快照同口径）
            product_name=product.name if product else (form.product_name.data or '').strip(),
            customer_id=customer.id if customer else None,
            customer_name=customer.name if customer else (form.customer_name.data or '').strip(),
            quantity=form.quantity.data,
            due_date=form.due_date.data,
            leader_id=form.leader_id.data or None,
            related_department_id=form.related_department_id.data or None,
            priority=form.priority.data or 'normal',
            remark=form.remark.data or '',
            created_by=current_user.id,
        )
        db.session.add(order)
        db.session.flush()

        # 工艺路线批量生成工序：名称做快照，顺序沿用路线明细；停用的工序跳过
        route = db.session.get(ProcessRoute, form.route_id.data) if form.route_id.data else None
        route_note = ''
        if route is not None and route.is_active:
            added = 0
            for item in route.items:
                process = db.session.get(Process, item.process_id)
                if process is None or not process.is_active:
                    continue
                db.session.add(WorkOrderStep(work_order_id=order.id,
                                             process_id=process.id, name=process.name,
                                             seq=item.seq, remark=''))
                added += 1
            route_note = '；按工艺路线「%s」批量添加 %d 道工序' % (route.name, added)
            if route.items and added < len(route.items):
                route_note += '（%d 道工序已停用被跳过）' % (len(route.items) - added)

        plan_result = apply_plan(order, manual_start, manual_end)
        log_operation(module='production', action='create', target_type='work_order',
                      target_id=order.id,
                      summary='创建工单 %s；计划：%s%s' % (
                          order.order_no, plan_result_text(plan_result, order), route_note))
        db.session.commit()
        flash('工单 %s 创建成功；%s%s' % (order.order_no,
                                    plan_result_text(plan_result, order), route_note), 'success')
        return detail_redirect(order.id)
    return render_template('production/order_form.html', form=form, title='新建工单',
                           priority_labels=PRIORITY_LABELS, show_route=True,
                           route_product_map=route_product_map)


@bp.route('/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('production.manage')
def order_edit(order_id):
    """编辑工单基础信息。"""
    order = db.get_or_404(WorkOrder, order_id)
    form = WorkOrderForm(obj=order)
    # L1：自动工单的计划日期不回填表单，仅以只读占位提示展示当前值（架构 §5）
    if request.method == 'GET' and not order.plan_manual:
        form.plan_start_date.data = None
        form.plan_end_date.data = None
    fill_workorder_choices(form)
    fill_department_choices(form)
    fill_product_choices(form)
    fill_customer_choices(form)
    fill_route_choices(form)
    # 历史工单可能关联了已停用产品/客户：补回选项，避免编辑时丢失关联
    if order.product_id and all(c[0] != order.product_id for c in form.product_id.choices):
        form.product_id.choices.append(
            (order.product_id, '%s（已停用）' % (order.product.name if order.product
                                              else order.product_name)))
    if order.customer_id and all(c[0] != order.customer_id for c in form.customer_id.choices):
        form.customer_id.choices.append(
            (order.customer_id, '%s（已停用）' % (order.customer.name if order.customer
                                               else order.customer_name)))
    route_product_map = {
        r.id: r.product_id for r in ProcessRoute.query.filter_by(is_active=True).all()
    }
    if form.validate_on_submit():
        if not form.product_id.data and not (form.product_name.data or '').strip():
            flash('请选择产品档案；产品尚未建档时才需手工填写产品名称', 'danger')
            return render_template('production/order_form.html', form=form, title='编辑工单',
                                   target=order, priority_labels=PRIORITY_LABELS, show_route=False,
                                   route_product_map=route_product_map)
        manual_start = form.plan_start_date.data
        manual_end = form.plan_end_date.data
        if (manual_start is None) != (manual_end is None):
            flash('人工指定计划日期时，计划开工日与计划完工日必须同时填写；'
                  '两个都留空则由系统按交期自动倒排', 'danger')
            return render_template('production/order_form.html', form=form, title='编辑工单',
                                   target=order, priority_labels=PRIORITY_LABELS, show_route=False,
                                   route_product_map=route_product_map)
        product = db.session.get(Product, form.product_id.data) if form.product_id.data else None
        order.product_id = product.id if product else None
        order.product_name = product.name if product else (form.product_name.data or '').strip()
        customer = (db.session.get(Customer, form.customer_id.data)
                    if form.customer_id.data else None)
        order.customer_id = customer.id if customer else None
        order.customer_name = customer.name if customer else (form.customer_name.data or '').strip()
        order.quantity = form.quantity.data
        order.due_date = form.due_date.data
        order.leader_id = form.leader_id.data or None
        order.related_department_id = form.related_department_id.data or None
        order.priority = form.priority.data or 'normal'
        order.remark = form.remark.data or ''
        plan_result = apply_plan(order, manual_start, manual_end)
        log_operation(module='production', action='update', target_type='work_order',
                      target_id=order.id,
                      summary='编辑工单 %s；计划：%s' % (
                          order.order_no, plan_result_text(plan_result, order)))
        db.session.commit()
        flash('工单已保存；%s' % plan_result_text(plan_result, order), 'success')
        return detail_redirect(order.id)
    return render_template('production/order_form.html', form=form, title='编辑工单',
                           target=order, priority_labels=PRIORITY_LABELS, show_route=False,
                           route_product_map=route_product_map)


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
    # L1 计划展示：状态聚合 + 无法倒排时的可读提示
    plan = plan_status(order)
    plan_hint = ''
    if not order.due_date:
        plan_hint = '未填写交期，无法倒排'
    elif sum_standard_hours(order) <= 0:
        plan_hint = '未维护工序参考工时，无法倒排'
    # BOM 标准用料：优先走产品关联，历史工单按名称快照回退匹配
    bom_product = order.product
    if bom_product is None and order.product_name:
        bom_product = Product.query.filter_by(name=order.product_name).first()
    bom_rows = []
    if bom_product is not None:
        for item in bom_product.bom_items:
            mat = item.material
            bom_rows.append({
                'code': mat.code if mat else '-',
                'name': mat.name if mat else '#' + str(item.material_id),
                'spec': mat.spec if mat else '',
                'quantity': item.quantity,
                'unit': item.unit,
                'total': round((item.quantity or 0) * (order.quantity or 0), 2),
            })
    return render_template('production/order_detail.html', order=order, step_form=step_form,
                           status_labels=WorkOrder.STATUS_LABELS,
                           step_labels=WorkOrderStep.STATUS_LABELS,
                           issue_form=issue_form, issue_docs=issue_docs, op_logs=op_logs,
                           can_issue=order.status in ('pending', 'in_progress'),
                           can_run_steps=order.can_run_steps,
                           can_record_quality=order.status in ('in_progress', 'completed'),
                           total_hours=total_hours, labor_form=StepLaborForm(),
                           quality_form=quality_form, plan=plan, plan_hint=plan_hint,
                           bom_product=bom_product, bom_rows=bom_rows,
                           priority_labels=PRIORITY_LABELS, active_tab=detail_tab())


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
    return detail_redirect(order.id)


@bp.route('/orders/<int:order_id>/reopen', methods=['POST'])
@login_required
@permission_required('production.manage')
def order_reopen(order_id):
    """撤销开工：in_progress → pending，作为工序清单冻结后的补救路径。

    只回退工单状态；工序状态、实耗工时、质量记录、领料记录全部保留，
    管理员回到待开始调整完工序后再正常流转至进行中即可继续生产。
    数据权限统一走 base_order_query()，跨部门工单直接 404。
    """
    order = base_order_query().filter_by(id=order_id).first_or_404()
    if order.status != 'in_progress':
        flash('只有「进行中」工单可以撤销开工', 'danger')
        return detail_redirect(order.id)
    order.status = 'pending'
    log_operation(module='production', action='transition', target_type='work_order',
                  target_id=order.id,
                  summary='工单 %s 撤销开工：进行中 → 待开始（用于调整工序清单）' % order.order_no)
    db.session.commit()
    flash('工单 %s 已撤销开工，回到「待开始」；现在可以增删工序，'
          '调整完成后再流转至「进行中」' % order.order_no, 'success')
    return detail_redirect(order.id)


@bp.route('/orders/<int:order_id>/plan/recalculate', methods=['POST'])
@login_required
@permission_required('production.manage')
def order_plan_recalculate(order_id):
    """重新倒排：清除人工覆盖，按当前交期/数量/工序重算（仅未完结工单）。

    数据权限：统一走 base_order_query()，跨部门工单 first_or_404 直接 404；
    CSRF 由全局 CSRFProtect 覆盖，无需在此重复校验。
    """
    order = base_order_query().filter_by(id=order_id).first_or_404()
    if order.status not in UNFINISHED_ORDER_STATUSES:
        flash('已完结工单不参与重新倒排', 'danger')
        return detail_redirect(order.id)
    # 不传人工日期：强制回到自动模式并清除 plan_manual
    plan_result = apply_plan(order)
    log_operation(module='production', action='update', target_type='work_order',
                  target_id=order.id,
                  summary='工单 %s 重新倒排：%s' % (
                      order.order_no, plan_result_text(plan_result, order)))
    db.session.commit()
    flash('工单 %s 已重新倒排；%s' % (order.order_no, plan_result_text(plan_result, order)),
          'success' if plan_result != 'unavailable' else 'warning')
    return detail_redirect(order.id)


@bp.route('/orders/<int:order_id>/steps/new', methods=['POST'])
@login_required
@permission_required('production.manage')
def step_new(order_id):
    """为工单添加工序：仅「待开始」工单可增删工序，开工后工序清单冻结。

    补救路径：管理员可先将进行中工单"撤销开工"回到待开始，调整完再流转回来。
    """
    order = db.get_or_404(WorkOrder, order_id)
    if order.status != 'pending':
        flash('工单处于「%s」状态，工序清单已冻结，不能添加新工序；'
              '如需调整请先由管理员撤销开工回到「待开始」' %
              WorkOrder.STATUS_LABELS.get(order.status, order.status), 'danger')
        return detail_redirect(order.id)
    form = WorkOrderStepForm()
    fill_workorder_choices(form)
    fill_process_choices(form)
    if form.validate_on_submit():
        process = db.session.get(Process, form.process_id.data)
        if process is None or not process.is_active:
            flash('所选工序不存在或已停用，请刷新后重试', 'danger')
            return detail_redirect(order.id)
        step = WorkOrderStep(
            work_order_id=order.id,
            process_id=process.id,
            name=process.name,  # 快照：工序日后改名不影响历史工单
            seq=form.seq.data,
            operator_id=form.operator_id.data or None,
            remark=form.remark.data or '',
        )
        db.session.add(step)
        # L1 高危点：新建工单时还没有工序，工序变更后必须重算，否则计划日期永远为空
        db.session.flush()  # 先落库，确保 order.steps 关系包含刚添加的工序
        if not order.plan_manual:
            apply_plan(order)  # 人工覆盖的工单不改写计划日期
        db.session.commit()
        flash('工序「%s」已添加' % step.name, 'success')
    else:
        flash('请从下拉列表选择已维护的工序', 'danger')
    return detail_redirect(order.id)


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
        return detail_redirect(order.id)
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
    return detail_redirect(step.work_order_id)


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
        return detail_redirect(order.id)
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
    return detail_redirect(step.work_order_id)


@bp.route('/orders/<int:order_id>/quality', methods=['POST'])
@login_required
@permission_required('production.manage')
def order_quality(order_id):
    """记录/修正工单质量数据（仅进行中/已完成；良率与不良率由服务端计算）。"""
    order = db.get_or_404(WorkOrder, order_id)
    if order.status not in ('in_progress', 'completed'):
        flash('只有「进行中」或「已完成」工单才能记录质量数据', 'danger')
        return detail_redirect(order.id)
    form = QualityRecordForm()
    fill_defect_reason_choices(form)
    if not form.validate_on_submit():
        errors = [msg for msgs in form.errors.values() for msg in msgs]
        flash('质量记录表单校验失败：%s' % ('；'.join(errors) if errors else '请检查输入'),
              'danger')
        return detail_redirect(order.id)
    output_qty = form.output_qty.data or 0
    good_qty = form.good_qty.data or 0
    defect_qty = form.defect_qty.data or 0
    reason_id = form.defect_reason_id.data or None
    if reason_id:
        reason = db.session.get(DefectReason, reason_id)
        if reason is None or not reason.is_active:
            flash('所选不良原因不存在或已停用', 'danger')
            return detail_redirect(order.id)
    try:
        order.record_quality(output_qty, good_qty, defect_qty, reason_id,
                             form.quality_remark.data or '', current_user.id)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return detail_redirect(order.id)
    log_operation(module='production', action='update', target_type='work_order',
                  target_id=order.id, operator_id=current_user.id,
                  summary='工单 %s 质量记录：成品%s / 良品%s / 不良%s，良率%.2f%% 不良率%.2f%%' % (
                      order.order_no, output_qty, good_qty, defect_qty,
                      order.yield_rate, order.defect_rate))
    db.session.commit()
    flash('工单 %s 质量记录已保存' % order.order_no, 'success')
    return detail_redirect(order.id)


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
        if not order.plan_manual:
            # 工序减少后按剩余参考工时重算；mark_deleted 已 commit，此处只提交计划字段
            apply_plan(order)
            db.session.commit()
        flash('工序「%s」已删除，可在回收站恢复' % name, 'warning')
    return detail_redirect(order_id)


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
        return jsonify(ok=False, available=0, unit='', message='请选择仓库和物料')
    row = (Inventory.query
           .filter_by(warehouse_id=warehouse.id, material_id=material.id).first())
    available = row.quantity if row else 0
    from app.models.unit import UnitConversion
    conversions = [{
        'unit_id': c.unit_id, 'name': c.unit.name if c.unit else '', 'factor': c.factor,
    } for c in UnitConversion.query.filter_by(material_id=material.id).all() if c.unit]
    # 单位随余量一并返回，供领料弹窗联动展示；空值兜底避免前端出现 undefined/None
    return jsonify(ok=True, available=available, warehouse=warehouse.name,
                   material=material.name, unit=material.unit or '',
                   conversions=conversions)


@bp.route('/orders/<int:order_id>/issue', methods=['POST'])
@login_required
@permission_required('production.issue')
def order_issue(order_id):
    """领料：复用库存事务（出库+流水+工单日志三步原子）。已完成/已验收工单禁止。"""
    order = db.get_or_404(WorkOrder, order_id)
    if order.status not in ('pending', 'in_progress'):
        flash('工单已%s，不能领料' % WorkOrder.STATUS_LABELS.get(order.status, order.status),
              'danger')
        return detail_redirect(order.id)

    form = IssueForm()
    fill_issue_choices(form)
    if not form.validate_on_submit():
        flash('领料表单校验失败', 'danger')
        return detail_redirect(order.id)

    # P2-03 前置清晰提示：事务内仍有行锁强校验（防并发），此处只为给出可读反馈
    from app.models.material import Material
    from app.models.warehouse import Warehouse
    warehouse = db.session.get(Warehouse, form.warehouse_id.data)
    material = db.session.get(Material, form.material_id.data)
    if warehouse is None or not warehouse.is_active or material is None or not material.is_active:
        flash('仓库或物料不存在/已停用', 'danger')
        return detail_redirect(order.id)
    try:
        base_qty, conv, unit = resolve_base_quantity(
            material, form.unit_id.data or None, form.quantity.data)
    except UnitConversionError as exc:
        flash(str(exc), 'danger')
        return detail_redirect(order.id)

    entered_text = '%s%s' % (form.quantity.data, (' ' + unit.name if unit else ''))
    base_text = '%s %s' % (base_qty, material.unit or '基本单位')
    inv = (Inventory.query
           .filter_by(warehouse_id=warehouse.id, material_id=material.id).first())
    available = inv.quantity if inv else 0
    if base_qty > available:
        flash('库存不足：【%s / %s】当前余量 %d，本次领料 %s（折合 %s），缺 %d' % (
            warehouse.name, material.name, available, entered_text, base_text,
            base_qty - available), 'danger')
        return detail_redirect(order.id)

    try:
        apply_stock_document(
            doc_type='out',
            warehouse_id=form.warehouse_id.data,
            material_id=form.material_id.data,
            quantity=base_qty,
            handler_id=current_user.id,
            created_by=current_user.id,
            related_order_id=order.id,
            remark=form.remark.data or '工单领料',
            unit_id=form.unit_id.data or None,
            input_quantity=form.quantity.data,
            work_order_log={
                'order_id': order.id,
                'operator_id': current_user.id,
                'summary': '工单 %s 领料：%s / %s ×%s（折合 %s）' % (
                    order.order_no, warehouse.name, material.name, entered_text, base_text),
            },
        )
    except UnitConversionError as exc:
        flash(str(exc), 'danger')
    except InsufficientStockError as exc:
        # 并发兜底：前置校验通过后仍可能被其他事务抢先扣减
        flash('库存不足（并发变动），当前余量 %d，领料未成功' % exc.available, 'danger')
    except InventoryServiceError as exc:
        flash(str(exc), 'danger')
    else:
        flash('领料成功，已关联工单 %s' % order.order_no, 'success')
    return detail_redirect(order.id)


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
    plan_status_map = {o.id: plan_status(o) for o in orders}
    # 条形图统计口径与看板列完全一致（同一份 base_order_query 结果）
    max_count = max((len(items) for _, _, items in columns), default=0)
    chart_rows = [{
        'status': status, 'label': label, 'count': len(items),
        'percent': round(len(items) * 100.0 / max_count) if max_count else 0,
        'bar_class': BOARD_BAR_CLASSES.get(status, 'bg-secondary'),
    } for status, label, items in columns]
    # 横轴刻度：数量少时逐个显示，数量多时取 0/¼/½/¾/最大值
    if max_count <= 4:
        chart_ticks = list(range(0, max_count + 1))
    else:
        step = max(1, max_count // 4)
        chart_ticks = sorted({0, step, step * 2, step * 3, max_count})
    return render_template('production/board.html', columns=columns,
                           status_labels=WorkOrder.STATUS_LABELS,
                           step_labels=WorkOrderStep.STATUS_LABELS,
                           priority_labels=PRIORITY_LABELS, plan_status_map=plan_status_map,
                           chart_rows=chart_rows, chart_max=max_count,
                           chart_ticks=chart_ticks, total_orders=len(orders))
