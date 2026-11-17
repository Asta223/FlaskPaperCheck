"""人员与部门表单。"""
from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, PasswordField, SelectField, SelectMultipleField, \
    StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, Regexp

from app.utils.time_utils import today

ZERO_CHOICE = (0, '-- 无 --')


def fill_employee_choices(form) -> None:
    """运行时填充员工表单下拉项：部门/角色。"""
    from app.models.org import Department
    from app.models.rbac import Role
    form.department_id.choices = [ZERO_CHOICE] + [
        (d.id, d.name) for d in Department.query.filter_by(is_active=True).order_by(Department.sort_order, Department.id).all()
    ]
    form.roles.choices = [(r.id, r.name) for r in Role.query.order_by(Role.id).all()]


def fill_department_choices(form, exclude_id=None) -> None:
    """运行时填充部门表单下拉项：上级部门（排除自身防环）/负责人。"""
    from app.models.org import Department
    from app.models.user import User
    depts = Department.query.filter_by(is_active=True).order_by(Department.sort_order, Department.id).all()
    if exclude_id is not None:
        depts = [d for d in depts if d.id != exclude_id]
    form.parent_id.choices = [ZERO_CHOICE] + [(d.id, d.name) for d in depts]
    form.leader_id.choices = [ZERO_CHOICE] + [
        (u.id, '%s（%s）' % (u.display_name(), u.employee_no))
        for u in User.query.filter_by(is_active=True).order_by(User.employee_no).all()
    ]


class EmployeeForm(FlaskForm):
    """员工档案表单（新建时 password 必填由路由校验）。"""
    username = StringField('登录名', validators=[
        DataRequired(message='请输入登录名'), Length(max=64),
        Regexp(r'^[A-Za-z0-9_]+$', message='登录名仅限字母、数字、下划线'),
    ])
    employee_no = StringField('工号', validators=[DataRequired(message='请输入工号'), Length(max=32)])
    name = StringField('姓名', validators=[DataRequired(message='请输入姓名'), Length(max=64)])
    email = StringField('邮箱', validators=[Optional(), Email(message='邮箱格式不正确'), Length(max=120)])
    phone = StringField('手机号', validators=[Optional(), Length(max=20)])
    position = StringField('岗位', validators=[Optional(), Length(max=64)])
    department_id = SelectField('部门', coerce=int, validators=[Optional()])
    hire_date = DateField('入职日期', validators=[Optional()], format='%Y-%m-%d',
                          default=today)
    roles = SelectMultipleField('角色', coerce=int, validators=[Optional()])
    password = PasswordField('初始密码', validators=[
        Optional(), Length(min=6, message='密码至少6位'),
    ])
    submit = SubmitField('保存')


class DepartmentForm(FlaskForm):
    """部门表单。"""
    name = StringField('部门名称', validators=[DataRequired(message='请输入部门名称'), Length(max=64)])
    parent_id = SelectField('上级部门', coerce=int, validators=[Optional()])
    leader_id = SelectField('部门负责人', coerce=int, validators=[Optional()])
    sort_order = IntegerField('排序号', validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField('保存')
