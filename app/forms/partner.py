"""往来单位表单：客户档案、供应商档案（字段一致，派生自同一基类）。"""
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import Length, Optional, DataRequired


class _PartnerForm(FlaskForm):
    code = StringField('档案编号', validators=[
        DataRequired(message='请输入档案编号'), Length(max=32),
    ])
    name = StringField('单位名称', validators=[
        DataRequired(message='请输入单位名称'), Length(max=128),
    ])
    contact = StringField('联系人', validators=[Optional(), Length(max=64)])
    phone = StringField('联系电话', validators=[Optional(), Length(max=64)])
    address = StringField('地址', validators=[Optional(), Length(max=255)])
    tax_no = StringField('税号', validators=[Optional(), Length(max=64)])
    remark = StringField('备注', validators=[Optional(), Length(max=255)])
    submit = SubmitField('保存')


class CustomerForm(_PartnerForm):
    """客户档案表单。"""


class SupplierForm(_PartnerForm):
    """供应商档案表单。"""
