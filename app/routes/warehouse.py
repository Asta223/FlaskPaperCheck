"""仓库路由：仓库档案、出入库单据、库存查询（阈值标红）。"""
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.forms.partner import SupplierForm
from app.forms.unit import UnitForm, UnitConversionForm, fill_unit_conversion_choices
from app.forms.warehouse import InventoryThresholdForm, StockDocForm, WarehouseForm, \
    fill_warehouse_doc_choices
from app.models.ledger import StockLedger
from app.models.material import Material
from app.models.partner import Supplier
from app.models.unit import Unit, UnitConversion
from app.models.warehouse import Inventory, StockDocument, Warehouse
from app.services.inventory_service import InsufficientStockError, InventoryServiceError, \
    apply_stock_document, reverse_stock_document
from app.services.unit_service import UnitConversionError, base_unit_of
from app.services.log_service import log_operation
from app.services.soft_delete_service import mark_deleted
from app.utils.delete_guard import find_references, format_references
from app.utils.permissions import permission_required
from app.utils.time_utils import today

bp = Blueprint('warehouse', __name__, url_prefix='/warehouse')


# ---------------- 供应商档案（入库单的送货方）----------------

def _duplicate_supplier(code, name, exclude_id=None):
    query = Supplier.query.filter((Supplier.code == code) | (Supplier.name == name))
    if exclude_id:
        query = query.filter(Supplier.id != exclude_id)
    return query.first()


@bp.route('/suppliers')
@login_required
@permission_required('warehouse.view')
def supplier_list():
    edit_id = request.args.get('edit_id', type=int)
    supplier = db.session.get(Supplier, edit_id) if edit_id else None
    form = SupplierForm(obj=supplier)
    suppliers = Supplier.query.order_by(Supplier.code, Supplier.id).all()
    return render_template('warehouse/supplier_list.html', form=form, supplier=supplier,
                           suppliers=suppliers)


@bp.route('/suppliers/new', methods=['POST'])
@login_required
@permission_required('warehouse.supplier.manage')
def supplier_new():
    form = SupplierForm()
    if not form.validate_on_submit():
        flash('供应商档案表单校验失败', 'danger')
        return redirect(url_for('warehouse.supplier_list'))
    code, name = form.code.data.strip(), form.name.data.strip()
    if _duplicate_supplier(code, name):
        flash('供应商编号或名称已存在', 'danger')
        return redirect(url_for('warehouse.supplier_list'))
    supplier = Supplier(code=code, name=name, contact=(form.contact.data or '').strip(),
                        phone=(form.phone.data or '').strip(),
                        address=(form.address.data or '').strip(),
                        tax_no=(form.tax_no.data or '').strip(), remark=form.remark.data or '')
    db.session.add(supplier)
    log_operation(module='warehouse', action='create', target_type='supplier',
                  target_id=supplier.id, summary='创建供应商「%s」' % name)
    db.session.commit()
    flash('供应商「%s」已创建' % name, 'success')
    return redirect(url_for('warehouse.supplier_list'))


@bp.route('/suppliers/<int:supplier_id>/edit', methods=['POST'])
@login_required
@permission_required('warehouse.supplier.manage')
def supplier_edit(supplier_id):
    supplier = db.get_or_404(Supplier, supplier_id)
    form = SupplierForm(obj=supplier)
    if not form.validate_on_submit():
        flash('供应商档案表单校验失败', 'danger')
        return redirect(url_for('warehouse.supplier_list'))
    code, name = form.code.data.strip(), form.name.data.strip()
    if _duplicate_supplier(code, name, exclude_id=supplier.id):
        flash('供应商编号或名称已存在', 'danger')
        return redirect(url_for('warehouse.supplier_list'))
    supplier.code = code
    supplier.name = name
    supplier.contact = (form.contact.data or '').strip()
    supplier.phone = (form.phone.data or '').strip()
    supplier.address = (form.address.data or '').strip()
    supplier.tax_no = (form.tax_no.data or '').strip()
    supplier.remark = form.remark.data or ''
    log_operation(module='warehouse', action='update', target_type='supplier',
                  target_id=supplier.id, summary='保存供应商「%s」' % name)
    db.session.commit()
    flash('供应商「%s」已保存' % name, 'success')
    return redirect(url_for('warehouse.supplier_list'))


@bp.route('/suppliers/<int:supplier_id>/toggle', methods=['POST'])
@login_required
@permission_required('warehouse.supplier.manage')
def supplier_toggle(supplier_id):
    supplier = db.get_or_404(Supplier, supplier_id)
    supplier.is_active = not supplier.is_active
    db.session.commit()
    flash('供应商「%s」已%s' % (supplier.name, '启用' if supplier.is_active else '停用'),
          'success' if supplier.is_active else 'warning')
    return redirect(url_for('warehouse.supplier_list'))


@bp.route('/suppliers/<int:supplier_id>/delete', methods=['POST'])
@login_required
@permission_required('warehouse.supplier.manage')
def supplier_delete(supplier_id):
    """软删供应商：历史单据靠名称快照/引用显示，不受影响。"""
    supplier = db.get_or_404(Supplier, supplier_id)
    name = supplier.name
    mark_deleted(supplier, module='warehouse', target_type='supplier',
                 summary='删除供应商「%s」，可在回收站恢复' % name)
    flash('供应商「%s」已删除，可在系统管理→回收站恢复' % name, 'success')
    return redirect(url_for('warehouse.supplier_list'))


# ---------------- 计量单位档案与换算 ----------------

def _duplicate_unit(code, name, exclude_id=None):
    query = Unit.query.filter((Unit.code == code) | (Unit.name == name))
    if exclude_id:
        query = query.filter(Unit.id != exclude_id)
    return query.first()


def _duplicate_conversion(material_id, unit_id, exclude_id=None):
    query = UnitConversion.query.filter_by(material_id=material_id, unit_id=unit_id)
    if exclude_id:
        query = query.filter(UnitConversion.id != exclude_id)
    return query.first()


@bp.route('/units')
@login_required
@permission_required('material.unit.manage')
def unit_list():
    """单位档案 + 物料换算关系：同页维护，均可软删/回收站恢复。"""
    edit_id = request.args.get('edit_id', type=int)
    conv_edit_id = request.args.get('conv_edit_id', type=int)
    unit = db.session.get(Unit, edit_id) if edit_id else None
    conv = db.session.get(UnitConversion, conv_edit_id) if conv_edit_id else None
    form = UnitForm(obj=unit)
    conv_form = UnitConversionForm(obj=conv)
    fill_unit_conversion_choices(conv_form)
    return render_template(
        'warehouse/unit_list.html', form=form, unit=unit,
        units=Unit.query.order_by(Unit.code, Unit.id).all(),
        conv_form=conv_form, conv=conv,
        conversions=UnitConversion.query.order_by(UnitConversion.id.desc()).all(),
        dimension_labels=Unit.DIMENSION_LABELS)


@bp.route('/units/new', methods=['POST'])
@login_required
@permission_required('material.unit.manage')
def unit_new():
    form = UnitForm()
    if not form.validate_on_submit():
        flash('单位表单校验失败：%s' % '；'.join(err for errs in form.errors.values()
                                          for err in errs), 'danger')
        return redirect(url_for('warehouse.unit_list'))
    code = form.code.data.strip()
    name = form.name.data.strip()
    if _duplicate_unit(code, name):
        flash('单位编码或名称已存在：%s / %s' % (code, name), 'danger')
        return redirect(url_for('warehouse.unit_list'))
    unit = Unit(code=code, name=name, dimension=form.dimension.data,
                remark=form.remark.data or '')
    db.session.add(unit)
    log_operation(module='material', action='create', target_type='unit',
                  target_id=unit.id, summary='创建计量单位「%s」' % name)
    db.session.commit()
    flash('单位「%s」已新增' % name, 'success')
    return redirect(url_for('warehouse.unit_list'))


@bp.route('/units/<int:unit_id>/edit', methods=['POST'])
@login_required
@permission_required('material.unit.manage')
def unit_edit(unit_id):
    unit = db.get_or_404(Unit, unit_id)
    form = UnitForm(obj=unit)
    if not form.validate_on_submit():
        flash('单位表单校验失败：%s' % '；'.join(err for errs in form.errors.values()
                                          for err in errs), 'danger')
        return redirect(url_for('warehouse.unit_list'))
    code = form.code.data.strip()
    name = form.name.data.strip()
    if _duplicate_unit(code, name, exclude_id=unit.id):
        flash('单位编码或名称已存在：%s / %s' % (code, name), 'danger')
        return redirect(url_for('warehouse.unit_list'))
    old_name = unit.name
    unit.code = code
    unit.name = name
    unit.dimension = form.dimension.data
    unit.remark = form.remark.data or ''
    log_operation(module='material', action='update', target_type='unit',
                  target_id=unit.id, summary='保存计量单位「%s」' % name)
    db.session.commit()
    flash('单位%s已保存' % ('「%s」→「%s」' % (old_name, name) if old_name != name
                        else '「%s」' % name), 'success')
    return redirect(url_for('warehouse.unit_list'))


@bp.route('/units/<int:unit_id>/toggle', methods=['POST'])
@login_required
@permission_required('material.unit.manage')
def unit_toggle(unit_id):
    unit = db.get_or_404(Unit, unit_id)
    unit.is_active = not unit.is_active
    db.session.commit()
    flash('单位「%s」已%s' % (unit.name, '启用' if unit.is_active else '停用'),
          'success' if unit.is_active else 'warning')
    return redirect(url_for('warehouse.unit_list'))


@bp.route('/units/<int:unit_id>/delete', methods=['POST'])
@login_required
@permission_required('material.unit.manage')
def unit_delete(unit_id):
    """软删单位：仍被换算关系或历史单据引用时拒绝，避免下拉断链。"""
    unit = db.get_or_404(Unit, unit_id)
    refs = find_references(unit)
    if refs:
        flash('单位「%s」仍被引用（%s），不能删除' % (unit.name, format_references(refs)),
              'danger')
        return redirect(url_for('warehouse.unit_list'))
    mark_deleted(unit, module='material', target_type='unit',
                 summary='删除计量单位「%s」，可在回收站恢复' % unit.name)
    flash('单位「%s」已删除，可在系统管理→回收站恢复' % unit.name, 'success')
    return redirect(url_for('warehouse.unit_list'))


@bp.route('/unit-conversions/new', methods=['POST'])
@login_required
@permission_required('material.unit.manage')
def unit_conversion_new():
    form = UnitConversionForm()
    fill_unit_conversion_choices(form)
    if not form.validate_on_submit():
        flash('换算表单校验失败：%s' % '；'.join(err for errs in form.errors.values()
                                          for err in errs), 'danger')
        return redirect(url_for('warehouse.unit_list'))
    return _save_unit_conversion(form)


@bp.route('/unit-conversions/<int:conv_id>/edit', methods=['POST'])
@login_required
@permission_required('material.unit.manage')
def unit_conversion_edit(conv_id):
    conv = db.get_or_404(UnitConversion, conv_id)
    form = UnitConversionForm(obj=conv)
    fill_unit_conversion_choices(form)
    if not form.validate_on_submit():
        flash('换算表单校验失败：%s' % '；'.join(err for errs in form.errors.values()
                                          for err in errs), 'danger')
        return redirect(url_for('warehouse.unit_list'))
    return _save_unit_conversion(form, exclude_id=conv.id)


def _save_unit_conversion(form, exclude_id=None):
    material = db.session.get(Material, form.material_id.data)
    unit = db.session.get(Unit, form.unit_id.data)
    if material is None or unit is None or not unit.is_active:
        flash('物料或单位不存在/已停用', 'danger')
        return redirect(url_for('warehouse.unit_list'))
    base = base_unit_of(material)
    if base is None:
        flash('物料「%s」的基本单位「%s」尚未在单位档案中维护，请先建档' % (
            material.name, material.unit), 'danger')
        return redirect(url_for('warehouse.unit_list'))
    if base.dimension != unit.dimension:
        flash('单位「%s」与物料基本单位「%s」量纲不同，不能换算' % (
            unit.name, base.name), 'danger')
        return redirect(url_for('warehouse.unit_list'))
    if _duplicate_conversion(material.id, unit.id, exclude_id=exclude_id):
        flash('该物料的「%s」换算关系已存在' % unit.name, 'danger')
        return redirect(url_for('warehouse.unit_list'))

    if exclude_id:
        conv = db.session.get(UnitConversion, exclude_id)
        conv.material_id = material.id
        conv.unit_id = unit.id
        conv.factor = form.factor.data
        conv.remark = form.remark.data or ''
        action, label = 'update', '保存'
    else:
        conv = UnitConversion(material_id=material.id, unit_id=unit.id,
                              factor=form.factor.data, remark=form.remark.data or '')
        db.session.add(conv)
        action, label = 'create', '新增'
    log_operation(module='material', action=action, target_type='unit_conversion',
                  target_id=conv.id, summary='%s换算：1%s = %s%s（%s）' % (
                      label, unit.name, form.factor.data, base.name, material.name))
    db.session.commit()
    flash('已%s换算：1%s = %s%s' % (label, unit.name, form.factor.data, base.name), 'success')
    return redirect(url_for('warehouse.unit_list'))


@bp.route('/unit-conversions/<int:conv_id>/delete', methods=['POST'])
@login_required
@permission_required('material.unit.manage')
def unit_conversion_delete(conv_id):
    conv = db.get_or_404(UnitConversion, conv_id)
    desc = '1单位 = %s基本单位' % conv.factor
    mark_deleted(conv, module='material', target_type='unit_conversion',
                 summary='删除单位换算「%s」，可在回收站恢复' % desc)
    flash('换算关系已删除，可在系统管理→回收站恢复', 'success')
    return redirect(url_for('warehouse.unit_list'))


# ---------------- 仓库档案 ----------------

@bp.route('/warehouses')
@login_required
@permission_required('warehouse.manage')
def warehouse_list():
    """仓库档案列表 + 新增/编辑：支持按名称/位置搜索。"""
    edit_id = request.args.get('edit_id', type=int)
    keyword = (request.args.get('keyword') or '').strip()
    warehouse = db.session.get(Warehouse, edit_id) if edit_id else None
    form = WarehouseForm(obj=warehouse) if warehouse else WarehouseForm()
    query = Warehouse.query
    if keyword:
        like = '%%%s%%' % keyword
        query = query.filter((Warehouse.name.like(like)) | (Warehouse.location.like(like)))
    warehouses = query.order_by(Warehouse.is_active.desc(), Warehouse.id).all()
    return render_template('warehouse/warehouse_list.html', form=form, warehouse=warehouse,
                           warehouses=warehouses, keyword=keyword)


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
        wh = Warehouse(name=form.name.data.strip(), location=form.location.data or '')
        db.session.add(wh)
        db.session.flush()
        log_operation(module='warehouse', action='create', target_type='warehouse',
                      target_id=wh.id, summary='创建仓库 %s' % wh.name)
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
        log_operation(module='warehouse', action='update', target_type='warehouse',
                      target_id=warehouse.id, summary='编辑仓库 %s' % warehouse.name)
        db.session.commit()
        flash('仓库已保存', 'success')
    else:
        flash('表单校验失败', 'danger')
    return redirect(url_for('warehouse.warehouse_list'))


@bp.route('/warehouses/<int:warehouse_id>/toggle', methods=['POST'])
@login_required
@permission_required('warehouse.manage')
def warehouse_toggle(warehouse_id):
    """停用/启用仓库（软删可逆）：存在数量>0 的库存时禁止停用。"""
    warehouse = db.get_or_404(Warehouse, warehouse_id)
    if warehouse.is_active:
        nonempty = [inv for inv in warehouse.inventories if (inv.quantity or 0) > 0]
        if nonempty:
            flash('该仓库下存在有库存的物料，无法停用（请先出库）', 'danger')
            return redirect(url_for('warehouse.warehouse_list'))
        warehouse.is_active = False
        msg, cat = '仓库「%s」已停用（可随时恢复）' % warehouse.name, 'warning'
    else:
        # 恢复时若同名仓库已存在则拒绝（唯一约束）
        if Warehouse.query.filter(Warehouse.name == warehouse.name,
                                   Warehouse.id != warehouse.id).first():
            flash('存在同名仓库，无法恢复', 'danger')
            return redirect(url_for('warehouse.warehouse_list'))
        warehouse.is_active = True
        msg, cat = '仓库「%s」已恢复启用' % warehouse.name, 'success'
    log_operation(module='warehouse', action='update', target_type='warehouse',
                  target_id=warehouse.id, summary=msg)
    db.session.commit()
    flash(msg, cat)
    return redirect(url_for('warehouse.warehouse_list'))


@bp.route('/warehouses/<int:warehouse_id>/delete', methods=['POST'])
@login_required
@permission_required('warehouse.manage')
def warehouse_delete(warehouse_id):
    """软删除仓库：有库存/未删除单据/流水时拒绝，可从回收站恢复。"""
    warehouse = db.get_or_404(Warehouse, warehouse_id)
    if warehouse.inventories:
        flash('该仓库仍存在库存记录，不能删除（可先停用）', 'danger')
        return redirect(url_for('warehouse.warehouse_list'))
    if StockDocument.query.filter_by(warehouse_id=warehouse.id).first():
        flash('该仓库存在出入库单据历史，不能删除（可先停用）', 'danger')
        return redirect(url_for('warehouse.warehouse_list'))
    from app.models.ledger import StockLedger
    if StockLedger.query.filter_by(warehouse_id=warehouse.id).first():
        flash('该仓库存在库存流水历史，不能删除（可先停用）', 'danger')
        return redirect(url_for('warehouse.warehouse_list'))
    name = warehouse.name
    mark_deleted(warehouse, module='warehouse', target_type='warehouse',
                 summary='删除仓库「%s」，可在回收站恢复' % name)
    flash('仓库「%s」已删除，可在回收站恢复' % name, 'success')
    return redirect(url_for('warehouse.warehouse_list'))


# ---------------- 出入库单据 ----------------

@bp.route('/api/units')
@login_required
@permission_required('warehouse.manage')
def api_units():
    """出入库录入联动：返回物料基本单位与已维护换算单位。"""
    material_id = request.args.get('material_id', type=int)
    material = db.session.get(Material, material_id) if material_id else None
    if material is None:
        return jsonify(ok=False, message='物料不存在')
    conversions = [{
        'unit_id': c.unit_id, 'name': c.unit.name if c.unit else '', 'factor': c.factor,
    } for c in UnitConversion.query.filter_by(material_id=material.id).all() if c.unit]
    return jsonify(ok=True, base_unit=material.unit or '', conversions=conversions)


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
                supplier_id=form.supplier_id.data or None,
                unit_id=form.unit_id.data or None,
                input_quantity=form.quantity.data,
            )
        except UnitConversionError as exc:
            flash(str(exc), 'danger')
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


@bp.route('/docs/<int:doc_id>/delete', methods=['POST'])
@login_required
@permission_required('warehouse.manage')
def doc_delete(doc_id):
    """软删除出入库单：同事务反向冲销库存并追加冲销流水；回收站恢复时再重新入账。"""
    doc = db.get_or_404(StockDocument, doc_id)
    doc_no = doc.doc_no
    try:
        reverse_stock_document(doc, current_user.id)
    except InsufficientStockError:
        db.session.rollback()
        flash('单据 %s 对应库存已被后续出库消耗，无法删除（否则库存会变负）' % doc_no,
              'danger')
        return redirect(url_for('warehouse.doc_list'))
    mark_deleted(doc, module='warehouse', target_type='stock_document',
                 summary='删除%s单据 %s ×%s，库存已反向冲销，可在回收站恢复' % (
                     '入库' if doc.doc_type == 'in' else '出库', doc_no, doc.quantity))
    flash('单据 %s 已删除，库存已反向冲销；可在回收站恢复' % doc_no, 'success')
    return redirect(url_for('warehouse.doc_list'))


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
    from app.services.csv_specs import INVENTORY_HEADERS
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
            mat.storage_location if mat else '',
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
    return _export_csv(INVENTORY_HEADERS, rows, 'inventory')


# ---------------- 预警消息已读（P1-09）----------------

@bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def read_notification(notif_id):
    """标记预警消息已读（仅接收人本人）。"""
    from app.services.notification_service import mark_warning_read
    if not mark_warning_read(notif_id, current_user.id):
        abort(403)
    return {'code': 0, 'data': {'notif_id': notif_id}, 'message': 'ok'}

