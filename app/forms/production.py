"""生产工单表单。"""
from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


def fill_department_choices(form) -> None:
    """运行时填充：归属部门下拉（P1-04）。"""
    from app.models.org import Department
    depts = Department.query.filter_by(is_active=True).order_by(Department.sort_order).all()
    form.related_department_id.choices = [ZERO_CHOICE] + [(d.id, d.name) for d in depts]


def fill_issue_choices(form) -> None:
    """运行时填充：领料表单的仓库/物料下拉。"""
    from app.models.material import Material
    from app.models.warehouse import Warehouse
    form.warehouse_id.choices = [
        (w.id, w.name) for w in Warehouse.query.filter_by(is_active=True).order_by(Warehouse.id).all()
    ]
    form.material_id.choices = [
        (m.id, '%s（%s）' % (m.name, m.code))
        for m in Material.query.filter_by(is_active=True).order_by(Material.code).all()
    ]

ZERO_CHOICE = (0, '-- 无 --')


def fill_workorder_choices(form) -> None:
    """运行时填充：负责人/操作人下拉（按表单实际字段自动跳过）。"""
    from app.models.user import User
    users = User.query.filter_by(is_active=True).order_by(User.employee_no).all()
    if hasattr(form, 'leader_id'):
        form.leader_id.choices = [ZERO_CHOICE] + [
            (u.id, '%s（%s）' % (u.display_name(), u.employee_no)) for u in users
        ]
    if hasattr(form, 'operator_id'):
        form.operator_id.choices = [ZERO_CHOICE] + [
            (u.id, '%s（%s）' % (u.display_name(), u.employee_no)) for u in users
        ]


class WorkOrderForm(FlaskForm):
    """工单新建/编辑表单。"""
    product_name = StringField('产品名称', validators=[
        DataRequired(message='请输入产品名称'), Length(max=128),
    ])
    quantity = IntegerField('数量', validators=[
        DataRequired(message='请输入数量'), NumberRange(min=1, message='数量必须大于0'),
    ])
    due_date = DateField('交货日期', validators=[Optional()], format='%Y-%m-%d')
    leader_id = SelectField('负责人', coerce=int, validators=[Optional()])
    related_department_id = SelectField('归属部门', coerce=int, validators=[Optional()],
                                        default=0)
    remark = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('保存')


class WorkOrderStepForm(FlaskForm):
    """工序新增表单。"""
    name = StringField('工序名称', validators=[
        DataRequired(message='请输入工序名称'), Length(max=128),
    ])
    seq = IntegerField('顺序号', validators=[
        DataRequired(message='请输入顺序号'), NumberRange(min=1, message='顺序号必须大于0'),
    ])
    operator_id = SelectField('操作人', coerce=int, validators=[Optional()])
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('添加工序')


class IssueForm(FlaskForm):
    """工单领料表单（P1-05）：物料/仓库/数量。"""
    warehouse_id = SelectField('仓库', coerce=int,
                               validators=[DataRequired(message='请选择仓库')])
    material_id = SelectField('物料', coerce=int,
                              validators=[DataRequired(message='请选择物料')])
    quantity = IntegerField('数量', validators=[
        DataRequired(message='请输入数量'), NumberRange(min=1, message='数量必须大于0'),
    ])
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('确认领料')
