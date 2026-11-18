"""认证表单：登录、修改密码。"""
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length


class LoginForm(FlaskForm):
    """登录表单。"""
    username = StringField('用户名', validators=[
        DataRequired(message='请输入用户名'),
        Length(max=64, message='用户名过长'),
    ])
    password = PasswordField('密码', validators=[
        DataRequired(message='请输入密码'),
    ])
    submit = SubmitField('登录')


class PasswordChangeForm(FlaskForm):
    """修改密码表单。"""
    old_password = PasswordField('原密码', validators=[
        DataRequired(message='请输入原密码'),
    ])
    new_password = PasswordField('新密码', validators=[
        DataRequired(message='请输入新密码'),
        Length(min=6, message='新密码至少6位'),
    ])
    confirm_password = PasswordField('确认新密码', validators=[
        DataRequired(message='请再次输入新密码'),
        EqualTo('new_password', message='两次输入的密码不一致'),
    ])
    submit = SubmitField('保存')
