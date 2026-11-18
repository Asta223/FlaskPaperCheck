"""P1 请假表单：申请（类型/起止/事由）、审批（意见）。"""
from datetime import timedelta

from flask_wtf import FlaskForm
from wtforms import DateTimeField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError

from app.utils.time_utils import now

LEAVE_TYPES = [('事假', '事假'), ('病假', '病假'), ('年假', '年假'),
               ('调休', '调休'), ('其他', '其他')]


def _default_start():
    """默认开始时间：当前时间向下取整到分钟。"""
    return now().replace(second=0, microsecond=0)


def _default_end():
    """默认结束时间：当前时间 +2 小时（保证晚于开始）。"""
    return (now() + timedelta(hours=2)).replace(second=0, microsecond=0)


class LeaveApplyForm(FlaskForm):
    """请假申请表单。"""
    leave_type = SelectField('请假类型', choices=LEAVE_TYPES,
                             validators=[DataRequired(message='请选择请假类型')])
    start_at = DateTimeField('开始时间', format='%Y-%m-%dT%H:%M', default=_default_start,
                             validators=[DataRequired(message='请选择开始时间')])
    end_at = DateTimeField('结束时间', format='%Y-%m-%dT%H:%M', default=_default_end,
                           validators=[DataRequired(message='请选择结束时间')])
    reason = TextAreaField('事由', validators=[DataRequired(message='请填写事由'),
                                              Length(max=500)])
    submit = SubmitField('提交申请')

    def validate_end_at(self, field):
        """结束时间必须晚于开始时间且跨度>0（字段级错误）。"""
        start = self.start_at.data
        end = field.data
        if start and end and end <= start:
            raise ValidationError('结束时间必须晚于开始时间')

    def validate_start_at(self, field):
        """开始时间不得早于今天零点之前过多（允许当天，拒绝明显历史）。此处仅校验非空格式。"""
        if field.data is None:
            raise ValidationError('开始时间格式不正确')


class LeaveApproveForm(FlaskForm):
    """审批意见表单（决定由 POST 字段 decision=approve/reject 指定）。"""
    approve_comment = TextAreaField('审批意见', validators=[Length(max=500)])
    submit = SubmitField('提交审批')
