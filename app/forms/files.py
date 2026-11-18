"""文件管理表单：分类、上传（可见范围 all/roles/departments）、检索。"""
from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (RadioField, SelectField, SelectMultipleField, StringField,
                     SubmitField)
from wtforms.validators import DataRequired, Length, Optional, ValidationError

ZERO_CHOICE = (0, '-- 无 --')


def fill_file_choices(form) -> None:
    """运行时填充：分类下拉、可见角色多选、可见部门多选。"""
    from app.models.file import FileCategory
    from app.models.org import Department
    from app.models.rbac import Role
    cats = FileCategory.query.filter_by(is_active=True).order_by(FileCategory.id).all()
    form.category_id.choices = [ZERO_CHOICE] + [(c.id, c.name) for c in cats]
    form.role_ids.choices = [(r.id, r.name) for r in Role.query.order_by(Role.id).all()]
    if hasattr(form, 'department_ids'):
        form.department_ids.choices = [
            (d.id, d.name) for d in Department.query.filter_by(is_active=True)
            .order_by(Department.sort_order, Department.id).all()
        ]


def fill_file_category_choices(form, exclude_id=None) -> None:
    """运行时填充：上级分类（排除自身防环）。"""
    from app.models.file import FileCategory
    cats = FileCategory.query.filter_by(is_active=True).order_by(FileCategory.id).all()
    if exclude_id is not None:
        cats = [c for c in cats if c.id != exclude_id]
    form.parent_id.choices = [ZERO_CHOICE] + [(c.id, c.name) for c in cats]


def fill_file_search_choices(form) -> None:
    """运行时填充：检索分类下拉。"""
    from app.models.file import FileCategory
    cats = FileCategory.query.filter_by(is_active=True).order_by(FileCategory.id).all()
    form.cat_id.choices = [ZERO_CHOICE] + [(c.id, c.name) for c in cats]


class FileCategoryForm(FlaskForm):
    """文件分类表单。"""
    name = StringField('分类名称', validators=[DataRequired(message='请输入分类名称'), Length(max=64)])
    parent_id = SelectField('上级分类', coerce=int, validators=[Optional()])
    submit = SubmitField('保存')


class FileUploadForm(FlaskForm):
    """文件上传表单（可见范围 all/roles/departments）。"""
    category_id = SelectField('分类', coerce=int, validators=[Optional()])
    file = FileField('选择文件', validators=[DataRequired(message='请选择文件')])
    visibility_type = RadioField(
        '可见范围',
        choices=[('all', '全员可见'), ('roles', '指定角色'), ('departments', '指定部门')],
        default='all', validators=[DataRequired()])
    role_ids = SelectMultipleField('可见角色', coerce=int, validators=[Optional()])
    department_ids = SelectMultipleField('可见部门', coerce=int, validators=[Optional()])
    submit = SubmitField('上传')

    def validate_file(self, field):
        """校验扩展名白名单（config.UPLOAD_EXTENSIONS）。"""
        import os
        filename = field.data.filename or ''
        ext = os.path.splitext(filename)[1].lower()
        allowed = current_app.config.get('UPLOAD_EXTENSIONS', set())
        if not ext or ext not in allowed:
            raise ValidationError('不支持的文件类型：%s' % (ext or '无扩展名'))


class FileSearchForm(FlaskForm):
    """文件检索表单（名称关键词 + 分类树）。"""
    keyword = StringField('名称关键词', validators=[Optional(), Length(max=200)])
    cat_id = SelectField('分类', coerce=int, validators=[Optional()])
    submit = SubmitField('搜索')
