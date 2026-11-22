"""单位档案与单位换算表单。"""
from flask_wtf import FlaskForm
from wtforms import FloatField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

ZERO_CHOICE = (0, '-- 无 --')


def fill_unit_conversion_choices(form) -> None:
    """运行时填充：物料/换算单位下拉（避免模块导入期查库）。"""
    from app.models.material import Material
    from app.models.unit import Unit
    form.material_id.choices = [
        (m.id, '%s（%s）' % (m.name, m.code))
        for m in Material.query.filter_by(is_active=True).order_by(Material.code).all()
    ]
    form.unit_id.choices = [
        (u.id, '%s（%s）' % (u.name, Unit.DIMENSION_LABELS.get(u.dimension, u.dimension)))
        for u in Unit.query.filter_by(is_active=True).order_by(Unit.code).all()
    ]


class UnitForm(FlaskForm):
    """计量单位主数据表单。"""
    code = StringField('单位编码', validators=[
        DataRequired(message='请输入单位编码'), Length(max=32)])
    name = StringField('单位名称', validators=[
        DataRequired(message='请输入单位名称'), Length(max=32)])
    dimension = SelectField('量纲', choices=[
        ('quantity', '数量'), ('weight', '重量'), ('length', '长度'), ('volume', '体积'),
    ], validators=[DataRequired(message='请选择量纲')])
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('保存')


class UnitConversionForm(FlaskForm):
    """物料单位换算表单：1 单位 = factor 基本单位。"""
    material_id = SelectField('物料', coerce=int,
                              validators=[DataRequired(message='请选择物料')])
    unit_id = SelectField('换算单位', coerce=int,
                          validators=[DataRequired(message='请选择换算单位')])
    factor = FloatField('换算系数', validators=[
        DataRequired(message='请输入换算系数'),
        NumberRange(min=0.000001, message='换算系数必须大于0'),
    ])
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('保存换算')
