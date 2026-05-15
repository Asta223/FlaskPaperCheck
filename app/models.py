from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime
import json

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='user')  # 'user' 或 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    papers = db.relationship('Paper', backref='author', lazy='dynamic')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Paper(db.Model):
    __tablename__ = 'papers'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(200))
    file_path = db.Column(db.String(300))
    content_text = db.Column(db.Text)  # 提取的纯文本
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    checks = db.relationship('CheckRecord', backref='paper', lazy='dynamic')
    file_hash = db.Column(db.String(64), nullable=True, index=True)

class CheckRecord(db.Model):
    __tablename__ = 'check_records'
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('papers.id'))
    algorithm = db.Column(db.String(50))   # 使用的算法，如'tfidf','simhash'
    similarity_score = db.Column(db.Float)  # 相似度（最高）
    report_path = db.Column(db.String(300)) # 生成的报告文件路径（可选）
    check_time = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)           # 存储JSON格式的详细信息

    def set_details(self, data):
        self.details = json.dumps(data, ensure_ascii=False)

    def get_details(self):
        if self.details:
            return json.loads(self.details)
        return {}

class AlgorithmConfig(db.Model):
    __tablename__ = 'algorithm_config'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    threshold = db.Column(db.Float, default=0.5)
    params = db.Column(db.Text)  # JSON格式参数