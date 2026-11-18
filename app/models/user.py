"""用户模型 + 用户-角色关联表。"""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager
from app.models.mixins import SoftDeleteMixin
from app.utils.time_utils import now

# 用户-角色 多对多关联表
user_roles = db.Table(
    'user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
)


class User(UserMixin, SoftDeleteMixin, db.Model):
    """员工账号：既是登录主体，也是人员档案（工号/部门/岗位/入职离职）。"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    # 唯一性由业务层只校验未删除记录（软删记录仍占库，故不放数据库唯一约束）
    username = db.Column(db.String(64), nullable=False, comment='登录名')
    employee_no = db.Column(db.String(32), nullable=False, comment='工号')
    name = db.Column(db.String(64), nullable=False, comment='真实姓名')
    email = db.Column(db.String(120), nullable=True, comment='邮箱，可空')
    phone = db.Column(db.String(20), nullable=True, comment='手机号，可空')
    password_hash = db.Column(db.String(256), nullable=False, comment='密码哈希')
    position = db.Column(db.String(64), nullable=True, comment='岗位')
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True,
                              comment='单部门归属，可空')
    hire_date = db.Column(db.Date, nullable=True, comment='入职日期')
    leave_date = db.Column(db.Date, nullable=True, comment='离职日期')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='离职=停用')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='创建时间')

    department = db.relationship('Department', backref='employees', foreign_keys=[department_id])
    roles = db.relationship('Role', secondary=user_roles, backref='users', lazy='select')

    def set_password(self, raw_password: str) -> None:
        """设置密码（哈希存储）。"""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """校验密码。"""
        return check_password_hash(self.password_hash, raw_password)

    def has_role(self, code: str) -> bool:
        """是否持有指定编码的角色。"""
        return any(role.code == code for role in self.roles)

    def display_name(self) -> str:
        """展示名：真实姓名优先，其次登录名。"""
        return self.name or self.username

    def __repr__(self) -> str:
        return '<User %s %s>' % (self.employee_no, self.username)


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login 用户加载器。"""
    return db.session.get(User, int(user_id))
