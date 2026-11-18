"""生产工单表单：工序档案、工单、工序行项、领料。"""
from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, IntegerField, SelectField, StringField, SubmitField, \
    TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.utils.time_utils import today

ZERO_CHOICE = (0, '-- 无 --')


def fill_defect_reason_choices(form) -> None:
    """运行时填充：不良原因下拉（仅启用且未删除的主数据）。"""
    from app.models.production import DefectReason
    form.defect_reason_id.choices = [ZERO_CHOICE] + [
        (r.id, '%s %s%s' % (r.code, r.name, ('（%s）' % r.category) if r.category else ''))
        for r in DefectReason.query.filter_by(is_active=True).order_by(DefectReason.code).all()
    ]


def fill_process_choices(form) -> None:
    """运行时填充：工序档案下拉（仅启用项，按排序）。"""
    from app.models.production import Process
    form.process_id.choices = [
        (p.id, '%s %s%s' % (p.code, p.name,
                           ('（参考%.2fh）' % p.standard_hours) if p.standard_hours else ''))
        for p in Process.query.filter_by(is_active=True).order_by(Process.sort_order, Process.id).all()
    ]


class ProcessForm(FlaskForm):
    """工序档案新建/编辑表单。"""
    code = StringField('工序编码', validators=[
        DataRequired(message='请输入工序编码'), Length(max=32),
    ])
    name = StringField('工序名称', validators=[
        DataRequired(message='请输入工序名称'), Length(max=64),
    ])
    standard_hours = FloatField('参考工时(小时)', validators=[
        Optional(), NumberRange(min=0, message='参考工时不小于0'),
    ], default=0)
    sort_order = IntegerField('排序号', validators=[Optional()], default=0)
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('保存')


class DefectReasonForm(FlaskForm):
    """不良原因主数据新建/编辑表单。"""
    code = StringField('原因编码', validators=[
        DataRequired(message='请输入原因编码'), Length(max=32),
    ])
    name = StringField('原因名称', validators=[
        DataRequired(message='请输入原因名称'), Length(max=64),
    ])
    category = StringField('原因分类', validators=[Optional(), Length(max=64)])
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('保存')


class QualityRecordForm(FlaskForm):
    """工单质量记录表单：良率/不良率由服务端按数量计算，不接受用户填写。"""
    output_qty = IntegerField('成品数量', validators=[
        DataRequired(message='请输入成品数量'), NumberRange(min=0, message='成品数量不小于0'),
    ])
    good_qty = IntegerField('合格数量', validators=[
        DataRequired(message='请输入合格数量'), NumberRange(min=0, message='合格数量不小于0'),
    ])
    defect_qty = IntegerField('不良数量', validators=[
        DataRequired(message='请输入不良数量'), NumberRange(min=0, message='不良数量不小于0'),
    ])
    defect_reason_id = SelectField('不良原因', coerce=int, validators=[Optional()], default=0)
    quality_remark = TextAreaField('质量备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('保存质量记录')


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
        (m.id, '%s（%s）%s' % (m.name, m.code,
                              ('【库位：%s】' % m.storage_location) if m.storage_location else ''))
        for m in Material.query.filter_by(is_active=True).order_by(Material.code).all()
    ]

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
    due_date = DateField('交货日期', validators=[Optional()], format='%Y-%m-%d',
                         default=today)
    leader_id = SelectField('负责人', coerce=int, validators=[Optional()])
    related_department_id = SelectField('归属部门', coerce=int, validators=[Optional()],
                                        default=0)
    remark = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('保存')


class WorkOrderStepForm(FlaskForm):
    """工序新增表单：只能从已维护工序档案下拉选择，不允许自由输入名称。"""
    process_id = SelectField('工序', coerce=int,
                             validators=[DataRequired(message='请选择已维护的工序')])
    seq = IntegerField('顺序号', validators=[
        DataRequired(message='请输入顺序号'), NumberRange(min=1, message='顺序号必须大于0'),
    ])
    operator_id = SelectField('操作人', coerce=int, validators=[Optional()])
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('添加工序')


class StepLaborForm(FlaskForm):
    """工时修正表单：完成后可按实际消耗修正（生产侧无审批，直接留痕）。"""
    labor_hours = FloatField('消耗工时(小时)', validators=[
        DataRequired(message='请输入消耗工时'),
        NumberRange(min=0, message='消耗工时不小于0'),
    ])
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('保存工时')


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
