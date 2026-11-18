"""物料路由：分类 CRUD + 物料档案 CRUD。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.forms.material import MaterialCategoryForm, MaterialForm, \
    fill_material_category_choices, fill_material_choices
from app.models.material import Material, MaterialCategory
from app.services.soft_delete_service import mark_deleted
from app.utils.delete_guard import find_references, format_references
from app.utils.permissions import permission_required

bp = Blueprint('material', __name__, url_prefix='/material')


# ---------------- 物料分类 ----------------

@bp.route('/categories')
@login_required
@permission_required('material.manage')
def category_list():
    """分类管理页：树形列表 + 表单。"""
    edit_id = request.args.get('edit_id', type=int)
    cat = db.session.get(MaterialCategory, edit_id) if edit_id else None
    form = MaterialCategoryForm(obj=cat) if cat else MaterialCategoryForm()
    fill_material_category_choices(form, exclude_id=cat.id if cat else None)
    cats = MaterialCategory.query.filter_by(is_active=True).order_by(MaterialCategory.id).all()
    return render_template('material/category_list.html', form=form, cat=cat, cats=cats)


@bp.route('/categories/new', methods=['POST'])
@login_required
@permission_required('material.manage')
def category_new():
    """新增分类。"""
    form = MaterialCategoryForm()
    fill_material_category_choices(form)
    if form.validate_on_submit():
        db.session.add(MaterialCategory(name=form.name.data.strip(),
                                        parent_id=form.parent_id.data or None))
        db.session.commit()
        flash('分类创建成功', 'success')
    else:
        flash('表单校验失败', 'danger')
    return redirect(url_for('material.category_list'))


@bp.route('/categories/<int:cat_id>/edit', methods=['POST'])
@login_required
@permission_required('material.manage')
def category_edit(cat_id):
    """编辑分类。"""
    cat = db.get_or_404(MaterialCategory, cat_id)
    form = MaterialCategoryForm(obj=cat)
    fill_material_category_choices(form, exclude_id=cat.id)
    if form.validate_on_submit():
        cat.name = form.name.data.strip()
        cat.parent_id = form.parent_id.data or None
        db.session.commit()
        flash('分类已保存', 'success')
    else:
        flash('表单校验失败', 'danger')
    return redirect(url_for('material.category_list'))


@bp.route('/categories/<int:cat_id>/delete', methods=['POST'])
@login_required
@permission_required('material.manage')
def category_delete(cat_id):
    """软删除分类：存在未删除子分类或物料时拒绝，可从回收站恢复。"""
    cat = db.get_or_404(MaterialCategory, cat_id)
    if any(not c.is_deleted for c in cat.children):
        flash('该分类下存在子分类，无法删除', 'danger')
        return redirect(url_for('material.category_list'))
    if any(not m.is_deleted for m in cat.materials):
        flash('该分类下存在物料，无法删除', 'danger')
        return redirect(url_for('material.category_list'))
    name = cat.name
    mark_deleted(cat, module='material', target_type='material_category',
                 summary='删除物料分类「%s」，可在回收站恢复' % name)
    flash('分类「%s」已删除，可在回收站恢复' % name, 'success')
    return redirect(url_for('material.category_list'))


@bp.route('/categories/<int:cat_id>/purge', methods=['POST'])
@login_required
@permission_required('material.manage')
def category_purge(cat_id):
    """兼容旧入口：与 /delete 同为软删除。"""
    return category_delete(cat_id)


# ---------------- 物料档案 ----------------

@bp.route('/list')
@login_required
@permission_required('material.manage')
def material_list():
    """物料列表：分类/关键词筛选 + 分页。"""
    cat_id = request.args.get('cat_id', type=int)
    keyword = (request.args.get('keyword') or '').strip()
    page = request.args.get('page', 1, type=int)
    query = Material.query
    if cat_id:
        query = query.filter(Material.category_id == cat_id)
    if keyword:
        like = '%%%s%%' % keyword
        query = query.filter((Material.name.like(like)) | (Material.code.like(like)) |
                             (Material.storage_location.like(like)))
    pagination = query.order_by(Material.code).paginate(page=page, per_page=20, error_out=False)
    cats = MaterialCategory.query.filter_by(is_active=True).order_by(MaterialCategory.id).all()
    return render_template('material/material_list.html', pagination=pagination, cat_id=cat_id,
                           keyword=keyword, cats=cats)


@bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('material.manage')
def material_new():
    """新建物料。"""
    form = MaterialForm()
    fill_material_choices(form)
    if form.validate_on_submit():
        if Material.query.filter_by(code=form.code.data.strip()).first():
            flash('物料编码已存在', 'danger')
            return render_template('material/material_form.html', form=form, title='新建物料')
        db.session.add(Material(
            code=form.code.data.strip(),
            name=form.name.data.strip(),
            spec=form.spec.data or '',
            unit=form.unit.data.strip(),
            storage_location=form.storage_location.data or '',
            category_id=form.category_id.data or None,
        ))
        db.session.commit()
        flash('物料创建成功', 'success')
        return redirect(url_for('material.material_list'))
    return render_template('material/material_form.html', form=form, title='新建物料')


@bp.route('/<int:material_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('material.manage')
def material_edit(material_id):
    """编辑物料。"""
    material = db.get_or_404(Material, material_id)
    form = MaterialForm(obj=material)
    fill_material_choices(form)
    if form.validate_on_submit():
        exist = Material.query.filter(Material.code == form.code.data.strip(),
                                      Material.id != material.id).first()
        if exist:
            flash('物料编码已存在', 'danger')
            return render_template('material/material_form.html', form=form, title='编辑物料',
                                   target=material)
        material.code = form.code.data.strip()
        material.name = form.name.data.strip()
        material.spec = form.spec.data or ''
        material.unit = form.unit.data.strip()
        material.storage_location = form.storage_location.data or ''
        material.category_id = form.category_id.data or None
        db.session.commit()
        flash('物料已保存', 'success')
        return redirect(url_for('material.material_list'))
    return render_template('material/material_form.html', form=form, title='编辑物料',
                           target=material)


@bp.route('/<int:material_id>/toggle', methods=['POST'])
@login_required
@permission_required('material.manage')
def material_toggle(material_id):
    """停用/恢复物料（软删）。"""
    material = db.get_or_404(Material, material_id)
    material.is_active = not material.is_active
    db.session.commit()
    flash('物料 %s 已%s' % (material.name, '恢复' if material.is_active else '停用'),
          'warning' if not material.is_active else 'success')
    return redirect(url_for('material.material_list'))


@bp.route('/<int:material_id>/delete', methods=['POST'])
@login_required
@permission_required('material.manage')
def material_delete(material_id):
    """软删除物料：有库存/单据/流水/预警等有效引用时拒绝，可从回收站恢复。"""
    material = db.get_or_404(Material, material_id)
    refs = find_references(material)
    if refs:
        flash('物料「%s」仍被 %s 引用，不能删除' % (
            material.name, format_references(refs)), 'danger')
        return redirect(url_for('material.material_list'))
    name = material.name
    mark_deleted(material, module='material', target_type='material',
                 summary='删除物料「%s」，可在回收站恢复' % name)
    flash('物料「%s」已删除，可在回收站恢复' % name, 'success')
    return redirect(url_for('material.material_list'))
