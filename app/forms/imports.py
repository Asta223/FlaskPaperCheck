# -*- coding: utf-8 -*-
"""数据导入表单。"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import SubmitField


class ImportUploadForm(FlaskForm):
    """CSV / Excel 上传表单（CSRF 由 FlaskForm 自动处理）。"""

    file = FileField('CSV / Excel 文件', validators=[
        FileRequired(message='请选择要导入的文件'),
        FileAllowed(['csv', 'xlsx', 'xls'], message='仅支持 CSV / XLSX / XLS 文件'),
    ])
    submit = SubmitField('导入')
