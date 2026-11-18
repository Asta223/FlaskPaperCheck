"""文件管理路由：分类、上传、列表检索、下载、预览（可见范围校验）。"""
import os

from flask import Blueprint, current_app, flash, redirect, render_template, request, \
    send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.forms.files import (FileCategoryForm, FileSearchForm, FileUploadForm,
                             fill_file_category_choices, fill_file_choices,
                             fill_file_search_choices)
from app.models.file import (FactoryFile, FileCategory, file_department_visibility,
                             file_role_visibility)
from app.utils.permissions import has_permission, permission_required

bp = Blueprint('files', __name__, url_prefix='/files')


def _visible_dept_ids():
    """当前用户部门 + 子部门 id 集合（A5，含子部门）。"""
    from app.models.org import Department
    if not current_user.department_id:
        return []
    own = db.session.get(Department, current_user.department_id)
    return own.descendant_ids() if own else []


def _visible_files_query():
    """按可见范围过滤的文件查询（唯一出口）：all ∪ 自己上传 ∪ 角色命中 ∪ 部门命中（含子部门）。

    files.manage / superadmin 可见全部；其余 maintains P0 三支 + P1 departments 第三支。
    """
    query = FactoryFile.query.filter_by(is_active=True)
    if has_permission(current_user, 'files.manage') or current_user.has_role('superadmin'):
        return query
    role_ids = [role.id for role in current_user.roles]
    dept_ids = _visible_dept_ids()
    return query.filter(or_(
        FactoryFile.visibility_type == 'all',
        FactoryFile.uploaded_by == current_user.id,
        FactoryFile.id.in_(
            db.session.query(file_role_visibility.c.file_id)
            .filter(file_role_visibility.c.role_id.in_(role_ids))
        ),
        FactoryFile.id.in_(
            db.session.query(file_department_visibility.c.file_id)
            .filter(file_department_visibility.c.department_id.in_(dept_ids or [-1]))
        ),
    ))


def _descendant_category_ids(cat_id: int) -> list:
    """分类及其所有子孙分类 id（分类树检索，A5 类比）。"""
    ids = [cat_id]
    frontier = [cat_id]
    while frontier:
        children = (db.session.query(FileCategory.id)
                    .filter(FileCategory.parent_id.in_(frontier),
                            FileCategory.is_active.is_(True)).all())
        child_ids = [c[0] for c in children if c[0] not in ids]
        ids.extend(child_ids)
        frontier = child_ids
    return ids


@bp.route('/')
@login_required
@permission_required('files.view')
def index():
    """分类树 + 文件列表检索（按可见范围过滤）。"""
    cat_id = request.args.get('cat_id', type=int)
    keyword = (request.args.get('keyword') or '').strip()
    page = request.args.get('page', 1, type=int)
    query = _visible_files_query()
    if cat_id:
        query = query.filter(FactoryFile.category_id.in_(_descendant_category_ids(cat_id)))
    if keyword:
        like = '%%%s%%' % keyword
        query = query.filter(FactoryFile.name.like(like))
    pagination = query.order_by(FactoryFile.created_at.desc()).paginate(page=page, per_page=20,
                                                                        error_out=False)
    cats = FileCategory.query.filter_by(is_active=True).order_by(FileCategory.id).all()
    can_manage = has_permission(current_user, 'files.manage')
    upload_form = FileUploadForm() if can_manage else None
    if upload_form:
        fill_file_choices(upload_form)
    search_form = FileSearchForm()
    fill_file_search_choices(search_form)
    search_form.keyword.data = keyword
    search_form.cat_id.data = cat_id or 0
    return render_template('files/index.html', pagination=pagination, cats=cats, cat_id=cat_id,
                           keyword=keyword, can_manage=can_manage, upload_form=upload_form,
                           search_form=search_form)


@bp.route('/upload', methods=['GET', 'POST'])
@login_required
@permission_required('files.manage')
def upload():
    """上传文件（分类 + 可见范围 all/roles/departments）。"""
    form = FileUploadForm()
    fill_file_choices(form)
    if form.validate_on_submit():
        upload_file = form.file.data
        ext = os.path.splitext(upload_file.filename)[1].lower()
        stored_name = FactoryFile.new_stored_filename(ext)
        folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(folder, exist_ok=True)
        file_path = os.path.join(folder, stored_name)
        upload_file.save(file_path)
        size_bytes = os.path.getsize(file_path)

        file_rec = FactoryFile(
            name=upload_file.filename,
            original_filename=upload_file.filename,
            stored_filename=stored_name,
            file_ext=ext,
            size_bytes=size_bytes,
            category_id=form.category_id.data or None,
            visibility_type=form.visibility_type.data,
            uploaded_by=current_user.id,
        )
        if form.visibility_type.data == 'roles':
            from app.models.rbac import Role
            file_rec.visible_roles = Role.query.filter(Role.id.in_(form.role_ids.data or [])).all()
            if not file_rec.visible_roles:
                os.remove(file_path)
                flash('可见范围为指定角色时，请至少选择一个角色', 'danger')
                return render_template('files/upload.html', form=form)
        if form.visibility_type.data == 'departments':
            from app.models.org import Department
            file_rec.visible_departments = Department.query.filter(
                Department.id.in_(form.department_ids.data or [])).all()
            if not file_rec.visible_departments:
                os.remove(file_path)
                flash('可见范围为指定部门时，请至少选择一个部门', 'danger')
                return render_template('files/upload.html', form=form)
        db.session.add(file_rec)
        db.session.commit()
        flash('文件上传成功', 'success')
        return redirect(url_for('files.index'))
    return render_template('files/upload.html', form=form)


def _is_previewable(ext: str) -> bool:
    """是否可内联预览（图片/PDF）。"""
    return (ext or '').lower() in current_app.config.get(
        'PREVIEW_EXTENSIONS', {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp'})


@bp.route('/<int:file_id>/preview')
@login_required
@permission_required('files.view')
def preview(file_id):
    """图片/PDF 内联预览（Content-Disposition: inline）；其他格式重定向下载。"""
    file_rec = db.get_or_404(FactoryFile, file_id)
    if not file_rec.is_active or not file_rec.can_view(current_user):
        from flask import abort
        abort(403)
    if not _is_previewable(file_rec.file_ext):
        return redirect(url_for('files.download', file_id=file_id))
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_rec.stored_filename)
    if not os.path.exists(file_path):
        flash('文件已丢失，请联系管理员', 'danger')
        return redirect(url_for('files.index'))
    return render_template('files/preview.html', file_rec=file_rec,
                           preview_url=url_for('files.preview_file', file_id=file_id))


@bp.route('/<int:file_id>/preview_file')
@login_required
@permission_required('files.view')
def preview_file(file_id):
    """内联返回文件字节流（供 preview.html 的 <img>/<iframe> 引用）。"""
    file_rec = db.get_or_404(FactoryFile, file_id)
    if not file_rec.is_active or not file_rec.can_view(current_user):
        from flask import abort
        abort(403)
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_rec.stored_filename)
    if not os.path.exists(file_path):
        from flask import abort
        abort(404)
    return send_file(file_path, as_attachment=False,
                     mimetype=None, download_name=file_rec.original_filename)


@bp.route('/<int:file_id>/download')
@login_required
@permission_required('files.view')
def download(file_id):
    """下载文件（越权返回 403）。"""
    file_rec = db.get_or_404(FactoryFile, file_id)
    if not file_rec.is_active or not file_rec.can_view(current_user):
        from flask import abort
        abort(403)
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_rec.stored_filename)
    if not os.path.exists(file_path):
        flash('文件已丢失，请联系管理员', 'danger')
        return redirect(url_for('files.index'))
    return send_file(file_path, as_attachment=True, download_name=file_rec.original_filename)


@bp.route('/<int:file_id>/delete', methods=['POST'])
@login_required
@permission_required('files.manage')
def file_delete(file_id):
    """停用文件（软删，磁盘保留）。"""
    file_rec = db.get_or_404(FactoryFile, file_id)
    file_rec.is_active = False
    db.session.commit()
    flash('文件已删除（软删）', 'warning')
    return redirect(url_for('files.index'))


@bp.route('/categories/new', methods=['POST'])
@login_required
@permission_required('files.manage')
def category_new():
    """新增分类。"""
    form = FileCategoryForm()
    fill_file_category_choices(form)
    if form.validate_on_submit():
        db.session.add(FileCategory(name=form.name.data.strip(),
                                    parent_id=form.parent_id.data or None))
        db.session.commit()
        flash('分类创建成功', 'success')
    else:
        flash('表单校验失败', 'danger')
    return redirect(url_for('files.index'))


@bp.route('/categories/<int:cat_id>/edit', methods=['POST'])
@login_required
@permission_required('files.manage')
def category_edit(cat_id):
    """编辑分类。"""
    cat = db.get_or_404(FileCategory, cat_id)
    form = FileCategoryForm(obj=cat)
    fill_file_category_choices(form, exclude_id=cat.id)
    if form.validate_on_submit():
        cat.name = form.name.data.strip()
        cat.parent_id = form.parent_id.data or None
        db.session.commit()
        flash('分类已保存', 'success')
    else:
        flash('表单校验失败', 'danger')
    return redirect(url_for('files.index'))


@bp.route('/categories/<int:cat_id>/delete', methods=['POST'])
@login_required
@permission_required('files.manage')
def category_delete(cat_id):
    """停用分类（软删）：存在子分类或文件时拒绝。"""
    cat = db.get_or_404(FileCategory, cat_id)
    if any(c.is_active for c in cat.children):
        flash('该分类下存在未停用的子分类，无法停用', 'danger')
        return redirect(url_for('files.index'))
    if any(f.is_active for f in cat.files):
        flash('该分类下存在文件，无法停用', 'danger')
        return redirect(url_for('files.index'))
    cat.is_active = False
    db.session.commit()
    flash('分类已停用', 'warning')
    return redirect(url_for('files.index'))
