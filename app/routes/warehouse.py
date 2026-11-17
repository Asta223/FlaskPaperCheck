"""仓库路由：仓库档案、出入库单据、库存查询（阈值标红）。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.forms.warehouse import InventoryThresholdForm, StockDocForm, WarehouseForm, \
    fill_warehouse_doc_choices
from app.models.ledger import StockLedger
from app.models.material import Material
from app.models.warehouse import Inventory, StockDocument, Warehouse
from app.services.inventory_service import InsufficientStockError, InventoryServiceError, \
    apply_stock_document
from app.services.log_service import log_operation
from app.utils.permissions import permission_required
from app.utils.time_utils import today

bp = Blueprint('warehouse', __name__, url_prefix='/warehouse')


# ---------------- 仓库档案 ----------------

@bp.route('/warehouses')
@login_required
@permission_required('warehouse.manage')
def warehouse_list():
    """仓库档案列表 + 新增/编辑。"""
    edit_id = request.args.get('edit_id', type=int)
    warehouse = db.session.get(Warehouse, edit_id) if edit_id else None
    form = WarehouseForm(obj=warehouse) if warehouse else WarehouseForm()
    warehouses = Warehouse.query.order_by(Warehouse.id).all()
    return render_template('warehouse/warehouse_list.html', form=form, warehouse=warehouse,
                           warehouses=warehouses)


@bp.route('/warehouses/new', methods=['POST'])
@login_required
@permission_required('warehouse.manage')
def warehouse_new():
    """新增仓库。"""
    form = WarehouseForm()
    if form.validate_on_submit():
        if Warehouse.query.filter_by(name=form.name.data.strip()).first():
            flash('仓库名称已存在', 'danger')
            return redirect(url_for('warehouse.warehouse_list'))
        db.session.add(Warehouse(name=form.name.data.strip(),
                                 location=form.location.data or ''))
        db.session.commit()
        flash('仓库创建成功', 'success')
    else:
        flash('表单校验失败', 'danger')
    return redirect(url_for('warehouse.warehouse_list'))


@bp.route('/warehouses/<int:warehouse_id>/edit', methods=['POST'])
@login_required
@permission_required('warehouse.manage')
def warehouse_edit(warehouse_id):
    """编辑仓库。"""
    warehouse = db.get_or_404(Warehouse, warehouse_id)
    form = WarehouseForm(obj=warehouse)
    if form.validate_on_submit():
        exist = Warehouse.query.filter(Warehouse.name == form.name.data.strip(),
                                       Warehouse.id != warehouse.id).first()
        if exist:
            flash('仓库名称已存在', 'danger')
            return redirect(url_for('warehouse.warehouse_list', edit_id=warehouse.id))
        warehouse.name = form.name.data.strip()
        warehouse.location = form.location.data or ''
        db.session.commit()
        flash('仓库已保存', 'success')
    else:
        flash('表单校验失败', 'danger')
    return redirect(url_for('warehouse.warehouse_list'))


@bp.route('/warehouses/<int:warehouse_id>/delete', methods=['POST'])
@login_required
@permission_required('warehouse.manage')
def warehouse_delete(warehouse_id):
    """停用仓库（软删）：存在数量>0 的库存时拒绝。"""
    warehouse = db.get_or_404(Warehouse, warehouse_id)
    nonempty = [inv for inv in warehouse.inventories if (inv.quantity or 0) > 0]
    if nonempty:
        flash('该仓库下存在有库存的物料，无法停用', 'danger')
        return redirect(url_for('warehouse.warehouse_list'))
    warehouse.is_active = False
    db.session.commit()
    flash('仓库已停用', 'warning')
    return redirect(url_for('warehouse.warehouse_list'))


# ---------------- 出入库单据 ----------------

@bp.route('/docs')
@login_required
@permission_required('warehouse.manage')
def doc_list():
    """单据流水：类型筛选 + 分页。"""
    doc_type = request.args.get('doc_type', '', type=str)
    page = request.args.get('page', 1, type=int)
    query = StockDocument.query
    if doc_type in ('in', 'out'):
        query = query.filter(StockDocument.doc_type == doc_type)
    pagination = query.order_by(StockDocument.id.desc()).paginate(page=page, per_page=20,
                                                                  error_out=False)
    return render_template('warehouse/doc_list.html', pagination=pagination, doc_type=doc_type,
                           type_labels=StockDocument.DOC_TYPE_LABELS)


@bp.route('/docs/new', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse.manage')
def doc_new():
    """出入库单据录入（库存同事务增减，出库不足拒绝）。"""
    form = StockDocForm()
    fill_warehouse_doc_choices(form)
    if form.validate_on_submit():
        try:
            doc = apply_stock_document(
                doc_type=form.doc_type.data,
                warehouse_id=form.warehouse_id.data,
                material_id=form.material_id.data,
                quantity=form.quantity.data,
                handler_id=current_user.id,
                created_by=current_user.id,
                related_order_id=form.related_order_id.data or None,
                remark=form.remark.data or '',
            )
        except InsufficientStockError as exc:
            db.session.rollback()
            flash('库存不足，当前余量 %d，未生成单据' % exc.available, 'danger')
        except InventoryServiceError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        else:
            flash('单据 %s 已提交，库存已更新' % doc.doc_no, 'success')
            return redirect(url_for('warehouse.inventory'))
    return render_template('warehouse/doc_form.html', form=form)


# ---------------- 库存查询 ----------------

@bp.route('/inventory')
@login_required
@permission_required('warehouse.view')
def inventory():
    """库存列表：仓库/关键词筛选，低于阈值红色标注。"""
    warehouse_id = request.args.get('warehouse_id', type=int)
    keyword = (request.args.get('keyword') or '').strip()
    only_warning = request.args.get('only_warning', type=int, default=0)
    page = request.args.get('page', 1, type=int)

    query = Inventory.query
    if warehouse_id:
        query = query.filter(Inventory.warehouse_id == warehouse_id)
    if keyword:
        like = '%%%s%%' % keyword
        query = query.join(Material).filter(or_(Material.name.like(like), Material.code.like(like)))
    if only_warning:
        query = query.filter(Inventory.quantity <= Inventory.warn_threshold)
    pagination = query.order_by(Inventory.id).paginate(page=page, per_page=20, error_out=False)
    warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.id).all()
    threshold_form = InventoryThresholdForm()
    return render_template('warehouse/inventory.html', pagination=pagination,
                           warehouse_id=warehouse_id, keyword=keyword,
                           only_warning=only_warning, warehouses=warehouses,
                           threshold_form=threshold_form)


@bp.route('/inventory/<int:inv_id>/threshold', methods=['POST'])
@login_required
@permission_required('warehouse.manage')
def set_threshold(inv_id):
    """设置库存预警阈值。"""
    inv = db.get_or_404(Inventory, inv_id)
    form = InventoryThresholdForm()
    if form.validate_on_submit():
        inv.warn_threshold = form.warn_threshold.data
        db.session.commit()
        flash('阈值已更新', 'success')
    else:
        flash('阈值必须为不小于0的整数', 'danger')
    return redirect(url_for('warehouse.inventory'))


# ---------------- 库存流水（P1-07）----------------

@bp.route('/ledger')
@login_required
@permission_required('warehouse.ledger.view')
def ledger():
    """库存流水：物料/仓库/日期/单据类型筛选 + 分页。"""
    page = request.args.get('page', 1, type=int)
    material_id = request.args.get('material_id', type=int)
    warehouse_id = request.args.get('warehouse_id', type=int)
    doc_type = request.args.get('doc_type', '', type=str)
    # 首次进入默认今天；用户显式清空（date_from=）则不过滤，可查看全部历史
    date_from = request.args.get('date_from')
    date_from = (date_from or '').strip() if date_from is not None else today().isoformat()
    date_to = request.args.get('date_to')
    date_to = (date_to or '').strip() if date_to is not None else today().isoformat()

    query = StockLedger.query
    if material_id:
        query = query.filter(StockLedger.material_id == material_id)
    if warehouse_id:
        query = query.filter(StockLedger.warehouse_id == warehouse_id)
    if doc_type in ('in', 'out'):
        query = query.filter(StockLedger.doc_type == doc_type)
    if date_from:
        query = query.filter(StockLedger.created_at >= date_from + ' 00:00:00')
    if date_to:
        query = query.filter(StockLedger.created_at <= date_to + ' 23:59:59')
    pagination = query.order_by(StockLedger.created_at.desc(), StockLedger.id.desc()) \
        .paginate(page=page, per_page=20, error_out=False)
    return render_template('warehouse/ledger.html', pagination=pagination,
                           material_id=material_id, warehouse_id=warehouse_id,
                           doc_type=doc_type, date_from=date_from, date_to=date_to,
                           materials=Material.query.filter_by(is_active=True)
                           .order_by(Material.code).all(),
                           warehouses=Warehouse.query.filter_by(is_active=True)
                           .order_by(Warehouse.id).all(),
                           type_labels=StockLedger.DOC_TYPE_LABELS)


# ---------------- CSV 导出（P1-16）----------------

@bp.route('/inventory/export.csv')
@login_required
@permission_required('system.export')
def export_inventory_csv():
    """导出当前筛选库存（沿用 inventory 的筛选条件）。"""
    from app.services.export_service import export_csv as _export_csv, guard_export_or_redirect

    warehouse_id = request.args.get('warehouse_id', type=int)
    keyword = (request.args.get('keyword') or '').strip()
    only_warning = request.args.get('only_warning', type=int, default=0)

    query = Inventory.query
    if warehouse_id:
        query = query.filter(Inventory.warehouse_id == warehouse_id)
    if keyword:
        like = '%%%s%%' % keyword
        query = query.join(Material).filter(or_(Material.name.like(like), Material.code.like(like)))
    if only_warning:
        query = query.filter(Inventory.quantity <= Inventory.warn_threshold)
    inventories = query.order_by(Inventory.id).all()

    rows = []
    for inv in inventories:
        mat = inv.material
        rows.append([
            inv.warehouse.name if inv.warehouse else '',
            mat.name if mat else '',
            mat.code if mat else '',
            mat.spec if mat else '',
            inv.quantity,
            inv.warn_threshold,
            '预警' if inv.is_warning else '正常',
        ])
    guard = guard_export_or_redirect(
        rows, 'warehouse.inventory', warehouse_id=warehouse_id or 0,
        keyword=keyword, only_warning=only_warning)
    if guard is not None:
        return guard

    log_operation(module='warehouse', action='export', target_type='inventory',
                  summary='导出库存 wh=%s kw=%s，共%d行' % (warehouse_id or '全部', keyword, len(rows)))
    db.session.commit()
    return _export_csv(['仓库', '物料', '编码', '规格', '数量', '阈值', '状态'],
                       rows, 'inventory')


# ---------------- 预警消息已读（P1-09）----------------

@bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def read_notification(notif_id):
    """标记预警消息已读（仅接收人本人）。"""
    from app.services.notification_service import mark_warning_read
    if not mark_warning_read(notif_id, current_user.id):
        abort(403)
    return {'code': 0, 'data': {'notif_id': notif_id}, 'message': 'ok'}

