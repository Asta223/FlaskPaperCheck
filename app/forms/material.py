"""物料管理表单。"""
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Regexp

ZERO_CHOICE = (0, '-- 无 --')


def fill_material_choices(form) -> None:
    """运行时填充：分类下拉。"""
    from app.models.material import MaterialCategory
    cats = MaterialCategory.query.filter_by(is_active=True).order_by(MaterialCategory.id).all()
    form.category_id.choices = [ZERO_CHOICE] + [(c.id, c.name) for c in cats]


def fill_material_category_choices(form, exclude_id=None) -> None:
    """运行时填充：上级分类（排除自身防环）。"""
    from app.models.material import MaterialCategory
    cats = MaterialCategory.query.filter_by(is_active=True).order_by(MaterialCategory.id).all()
    if exclude_id is not None:
        cats = [c for c in cats if c.id != exclude_id]
    form.parent_id.choices = [ZERO_CHOICE] + [(c.id, c.name) for c in cats]


class MaterialCategoryForm(FlaskForm):
    """物料分类表单。"""
    name = StringField('分类名称', validators=[DataRequired(message='请输入分类名称'), Length(max=64)])
    parent_id = SelectField('上级分类', coerce=int, validators=[Optional()])
    submit = SubmitField('保存')


class MaterialForm(FlaskForm):
    """物料档案表单。"""
    code = StringField('物料编码', validators=[
        DataRequired(message='请输入物料编码'),
        Regexp(r'^[A-Za-z0-9_-]+$', message='编码仅限字母、数字、中划线、下划线'),
        Length(max=32),
    ])
    name = StringField('物料名称', validators=[DataRequired(message='请输入物料名称'), Length(max=128)])
    spec = StringField('规格', validators=[Optional(), Length(max=128)])
    unit = StringField('单位', validators=[DataRequired(message='请输入单位'), Length(max=16)])
    category_id = SelectField('分类', coerce=int, validators=[Optional()])
    submit = SubmitField('保存')
