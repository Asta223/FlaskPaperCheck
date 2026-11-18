"""站内聊天表单。"""
from flask_wtf import FlaskForm
from wtforms import HiddenField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class ChatSendForm(FlaskForm):
    """发送消息表单。"""
    receiver_id = HiddenField('接收人', validators=[DataRequired(message='请选择接收人')])
    content = TextAreaField('消息内容', validators=[
        DataRequired(message='消息不能为空'),
        Length(max=1000, message='消息最长1000字'),
    ])
    submit = SubmitField('发送')
