"""角色权限路由：角色 CRUD + 权限勾选矩阵 + 权限点总览。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.forms.rbac import RoleForm, fill_role_choices
from app.models.rbac import Role
from app.utils.permissions import PERMISSION_REGISTRY, permission_required

bp = Blueprint('rbac', __name__, url_prefix='/rbac')


@bp.route('/roles')
@login_required
@permission_required('rbac.manage')
def role_list():
    """角色列表。"""
    roles = Role.query.order_by(Role.id).all()
    return render_template('rbac/role_list.html', roles=roles)


@bp.route('/roles/new', methods=['GET', 'POST'])
@login_required
@permission_required('rbac.manage')
def role_new():
    """新建角色 + 权限勾选矩阵。"""
    form = RoleForm()
    fill_role_choices(form)
    if form.validate_on_submit():
        if Role.query.filter_by(code=form.code.data.strip()).first():
            flash('角色编码已存在', 'danger')
            return render_template('rbac/role_form.html', form=form, title='新建角色',
                                   registry=PERMISSION_REGISTRY)
        role = Role(
            code=form.code.data.strip(),
            name=form.name.data.strip(),
            is_builtin=False,
            remark=form.remark.data or '',
        )
        role.permissions = _resolve_permissions(form.permissions.data)
        db.session.add(role)
        db.session.commit()
        flash('角色创建成功', 'success')
        return redirect(url_for('rbac.role_list'))
    return render_template('rbac/role_form.html', form=form, title='新建角色',
                           registry=PERMISSION_REGISTRY)


@bp.route('/roles/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('rbac.manage')
def role_edit(role_id):
    """编辑角色（含权限矩阵）。"""
    role = db.get_or_404(Role, role_id)
    form = RoleForm(obj=role)
    fill_role_choices(form)
    if request.method == 'GET':
        form.permissions.data = [p.code for p in role.permissions]
    if form.validate_on_submit():
        exist = Role.query.filter(Role.code == form.code.data.strip(),
                                  Role.id != role.id).first()
        if exist:
            flash('角色编码已存在', 'danger')
            return render_template('rbac/role_form.html', form=form, title='编辑角色',
                                   target=role, registry=PERMISSION_REGISTRY)
        role.code = form.code.data.strip()
        role.name = form.name.data.strip()
        role.remark = form.remark.data or ''
        role.permissions = _resolve_permissions(form.permissions.data)
        db.session.commit()
        flash('角色已保存', 'success')
        return redirect(url_for('rbac.role_list'))
    return render_template('rbac/role_form.html', form=form, title='编辑角色',
                           target=role, registry=PERMISSION_REGISTRY)


@bp.route('/permissions')
@login_required
@permission_required('rbac.manage')
def permission_list():
    """权限点总览（只读，来自注册表）。"""
    return render_template('rbac/permission_list.html', registry=PERMISSION_REGISTRY)


def _resolve_permissions(codes):
    """把权限码列表解析为 Permission 对象列表（过滤非法码）。"""
    from app.models.rbac import Permission
    if not codes:
        return []
    return Permission.query.filter(Permission.code.in_(codes)).all()
