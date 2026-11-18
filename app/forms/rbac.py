"""角色权限表单。"""
from flask_wtf import FlaskForm
from wtforms import SelectMultipleField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, Regexp

from app.utils.permissions import PERMISSION_REGISTRY


def fill_role_choices(form) -> None:
    """运行时填充权限多选项：来自 PERMISSION_REGISTRY（模块.权限码 → 中文名）。"""
    choices = []
    for module, perms in PERMISSION_REGISTRY.items():
        for code, name in perms.items():
            choices.append((code, '%s · %s（%s）' % (module, name, code)))
    form.permissions.choices = choices


class RoleForm(FlaskForm):
    """角色表单（permissions 为权限码列表）。"""
    code = StringField('角色编码', validators=[
        DataRequired(message='请输入角色编码'),
        Regexp(r'^[a-z][a-z0-9_]*$', message='编码仅限小写字母开头，含小写字母/数字/下划线'),
        Length(max=32),
    ])
    name = StringField('角色名称', validators=[DataRequired(message='请输入角色名称'), Length(max=64)])
    remark = TextAreaField('备注', validators=[Optional(), Length(max=200)])
    permissions = SelectMultipleField('权限点', coerce=str, validators=[Optional()])
    submit = SubmitField('保存')
