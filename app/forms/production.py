"""生产工单表单。"""
from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

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
