"""考勤表单：打卡仅需 CSRF 保护，无业务字段。"""
from flask_wtf import FlaskForm
from wtforms import SubmitField


class ClockForm(FlaskForm):
    """打卡表单（动作由 POST 字段 action=in/out 指定）。"""
    submit = SubmitField('打卡')
