from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, PasswordField, SubmitField, SelectField, FloatField
from wtforms.validators import DataRequired, Email, EqualTo, Length
from wtforms import BooleanField

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    submit = SubmitField('登录')

class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('邮箱', validators=[DataRequired(), Email()])
    password = PasswordField('密码', validators=[DataRequired()])
    password2 = PasswordField('确认密码', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('注册')

class UploadForm(FlaskForm):
    title = StringField('论文标题', validators=[DataRequired()])
    file = FileField('选择文件', validators=[
        FileRequired(),
        FileAllowed(['pdf', 'doc', 'docx', 'txt'], '仅支持 PDF、Word、TXT 格式！')
    ])
    algorithm = SelectField('查重算法', choices=[
        ('tfidf', 'TF-IDF (基于词频)'),
        ('bert', 'Sentence-BERT (文档级)'),
        ('sentence_bert', 'Sentence-BERT (句子级)'),
        ('doc2vec', 'Doc2Vec (自定义训练)'),
        ('jaccard', 'Jaccard 相似度 (新增)')
    ], default='tfidf')
    threshold = FloatField('相似度阈值', default=0.5, validators=[DataRequired()])
    submit = SubmitField('上传并查重')
    compare_self = BooleanField('与自己的历史论文比对', default=False)