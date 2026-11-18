"""人员与部门管理路由：员工 CRUD + 离职停用；部门树 CRUD + 负责人。

P1 数据权限（部门主管只看本部门）预留统一查询出口 base_employee_query()。
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.forms.hr import DepartmentForm, EmployeeForm, fill_department_choices, \
    fill_employee_choices
from app.models.org import Department
from app.models.rbac import Role
from app.models.user import User
from app.utils.permissions import permission_required
from app.utils.time_utils import today

bp = Blueprint('hr', __name__, url_prefix='/hr')


def base_employee_query():
    """员工列表统一查询出口（P1 数据权限只改此处）。"""
    from app.utils.data_scope import apply_dept_scope
    return apply_dept_scope(User.query, User.department_id, current_user)


# ---------------- 员工管理 ----------------

@bp.route('/employees')
@login_required
@permission_required('hr.view')
def employee_list():
    """员工列表：左部门树筛选 + 搜索 + 分页。"""
    dept_id = request.args.get('dept_id', type=int)
    keyword = (request.args.get('keyword') or '').strip()
    page = request.args.get('page', 1, type=int)

    query = base_employee_query()
    if dept_id:
        query = query.filter(User.department_id == dept_id)
    if keyword:
        like = '%%%s%%' % keyword
        query = query.filter(or_(User.name.like(like), User.username.like(like),
                                 User.employee_no.like(like)))
    pagination = query.order_by(User.employee_no).paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'hr/employee_list.html',
        pagination=pagination,
        tree=Department.get_tree(),
        dept_id=dept_id,
        keyword=keyword,
    )


@bp.route('/employees/export.csv')
@login_required
@permission_required('system.export')
def employee_export_csv():
    """导出当前筛选员工 CSV（P1-16）：复用 base_employee_query + 数据权限，无密码哈希。"""
    from app.services.export_service import export_csv as _export_csv, guard_export_or_redirect
    from app.services.log_service import log_operation

    dept_id = request.args.get('dept_id', type=int)
    keyword = (request.args.get('keyword') or '').strip()

    query = base_employee_query()
    if dept_id:
        # 数据权限：注入出口后，非管辖 dept_id 自然收窄为空
        query = query.filter(User.department_id == dept_id)
    if keyword:
        like = '%%%s%%' % keyword
        query = query.filter(or_(User.name.like(like), User.username.like(like),
                                 User.employee_no.like(like)))
    users = query.order_by(User.employee_no).all()

    rows = []
    for u in users:
        rows.append([
            u.employee_no, u.name,
            u.department.name if u.department else '',
            u.position or '', u.phone or '', u.email or '',
            '在职' if u.is_active else '离职',
        ])
    guard = guard_export_or_redirect(rows, 'hr.employee_list', dept_id=dept_id or 0,
                                     keyword=keyword)
    if guard is not None:
        return guard

    log_operation(module='hr', action='export', target_type='employee',
                  summary='导出员工 dept=%s kw=%s，共%d行' % (dept_id or '全部', keyword, len(rows)))
    db.session.commit()
    return _export_csv(['工号', '姓名', '部门', '岗位', '手机', '邮箱', '状态'],
                       rows, 'employees')


def _validate_unique(form, user=None) -> bool:
    """登录名/工号唯一校验（编辑时排除自身）。"""
    username_q = User.query.filter_by(username=form.username.data.strip())
    no_q = User.query.filter_by(employee_no=form.employee_no.data.strip())
    if user is not None:
        username_q = username_q.filter(User.id != user.id)
        no_q = no_q.filter(User.id != user.id)
    if username_q.first():
        flash('登录名已存在', 'danger')
        return False
    if no_q.first():
        flash('工号已存在', 'danger')
        return False
    return True


@bp.route('/employees/new', methods=['GET', 'POST'])
@login_required
@permission_required('hr.manage')
def employee_new():
    """新建员工（账号由管理员开户，无自助注册）。"""
    form = EmployeeForm()
    fill_employee_choices(form)
    if form.validate_on_submit():
        if not _validate_unique(form):
            return render_template('hr/employee_form.html', form=form, title='新建员工')
        if not form.password.data:
            flash('新建员工必须设置初始密码（至少6位）', 'danger')
            return render_template('hr/employee_form.html', form=form, title='新建员工')
        user = User(
            username=form.username.data.strip(),
            employee_no=form.employee_no.data.strip(),
            name=form.name.data.strip(),
            email=form.email.data or None,
            phone=form.phone.data or None,
            position=form.position.data or None,
            department_id=form.department_id.data or None,
            hire_date=form.hire_date.data,
        )
        user.set_password(form.password.data)
        roles = Role.query.filter(Role.id.in_(form.roles.data or [])).all()
        user.roles = roles
        db.session.add(user)
        db.session.commit()
        flash('员工创建成功', 'success')
        return redirect(url_for('hr.employee_list'))
    return render_template('hr/employee_form.html', form=form, title='新建员工')


@bp.route('/employees/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('hr.manage')
def employee_edit(user_id):
    """编辑员工档案（改密请走个人页或重置密码）。"""
    user = db.get_or_404(User, user_id)
    form = EmployeeForm(obj=user)
    fill_employee_choices(form)
    if form.validate_on_submit():
        if not _validate_unique(form, user):
            return render_template('hr/employee_form.html', form=form, title='编辑员工',
                                   target=user)
        user.username = form.username.data.strip()
        user.employee_no = form.employee_no.data.strip()
        user.name = form.name.data.strip()
        user.email = form.email.data or None
        user.phone = form.phone.data or None
        user.position = form.position.data or None
        user.department_id = form.department_id.data or None
        user.hire_date = form.hire_date.data
        user.roles = Role.query.filter(Role.id.in_(form.roles.data or [])).all()
        if form.password.data:
            user.set_password(form.password.data)
        db.session.commit()
        flash('员工信息已保存', 'success')
        return redirect(url_for('hr.employee_list'))
    return render_template('hr/employee_form.html', form=form, title='编辑员工', target=user)


@bp.route('/employees/<int:user_id>/toggle', methods=['POST'])
@login_required
@permission_required('hr.manage')
def employee_toggle(user_id):
    """离职停用 / 复用（软操作，数据保留）。"""
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash('不能停用当前登录账号', 'danger')
        return redirect(url_for('hr.employee_list'))
    user.is_active = not user.is_active
    if user.is_active:
        user.leave_date = None
        flash('员工 %s 已复用（恢复在职）' % user.display_name(), 'success')
    else:
        user.leave_date = today()
        flash('员工 %s 已停用（视为离职），历史数据保留' % user.display_name(), 'warning')
    db.session.commit()
    return redirect(url_for('hr.employee_list'))


# ---------------- 部门管理 ----------------

@bp.route('/departments')
@login_required
@permission_required('dept.manage')
def departments():
    """部门树管理页：左树 + 右详情/表单。"""
    tree = Department.get_tree(include_inactive=True)
    edit_id = request.args.get('edit_id', type=int)
    parent_id = request.args.get('parent_id', type=int)
    dept = db.session.get(Department, edit_id) if edit_id else None
    form = DepartmentForm(obj=dept) if dept else DepartmentForm()
    fill_department_choices(form, exclude_id=dept.id if dept else None)
    if not dept and parent_id:
        form.parent_id.data = parent_id
    selected_id = edit_id or request.args.get('dept_id', type=int)
    selected = db.session.get(Department, selected_id) if selected_id else None
    return render_template('hr/department.html', tree=tree, form=form, dept=dept,
                           selected=selected)


@bp.route('/departments/new', methods=['POST'])
@login_required
@permission_required('dept.manage')
def department_new():
    """新增部门。"""
    form = DepartmentForm()
    fill_department_choices(form)
    if form.validate_on_submit():
        dept = Department(
            name=form.name.data.strip(),
            parent_id=form.parent_id.data or None,
            leader_id=form.leader_id.data or None,
            sort_order=form.sort_order.data or 0,
        )
        db.session.add(dept)
        db.session.commit()
        flash('部门创建成功', 'success')
    else:
        flash('表单校验失败，请检查填写', 'danger')
    return redirect(url_for('hr.departments'))


@bp.route('/departments/<int:dept_id>/edit', methods=['POST'])
@login_required
@permission_required('dept.manage')
def department_edit(dept_id):
    """编辑部门（名称/上级/负责人/排序）。"""
    dept = db.get_or_404(Department, dept_id)
    form = DepartmentForm(obj=dept)
    fill_department_choices(form, exclude_id=dept.id)
    if form.validate_on_submit():
        if form.parent_id.data == dept.id:
            flash('上级部门不能选择自身', 'danger')
            return redirect(url_for('hr.departments', edit_id=dept.id))
        dept.name = form.name.data.strip()
        dept.parent_id = form.parent_id.data or None
        dept.leader_id = form.leader_id.data or None
        dept.sort_order = form.sort_order.data or 0
        db.session.commit()
        flash('部门已保存', 'success')
    else:
        flash('表单校验失败，请检查填写', 'danger')
    return redirect(url_for('hr.departments'))


@bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@login_required
@permission_required('dept.manage')
def department_delete(dept_id):
    """停用部门（软删）：存在在职员工或未停用子部门时拒绝。"""
    dept = db.get_or_404(Department, dept_id)
    if dept.children and any(c.is_active for c in dept.children):
        flash('该部门下存在未停用的子部门，无法停用', 'danger')
        return redirect(url_for('hr.departments'))
    active_employees = [e for e in dept.employees if e.is_active]
    if active_employees:
        flash('该部门下存在在职员工，无法停用', 'danger')
        return redirect(url_for('hr.departments'))
    dept.is_active = False
    db.session.commit()
    flash('部门已停用', 'warning')
    return redirect(url_for('hr.departments'))
