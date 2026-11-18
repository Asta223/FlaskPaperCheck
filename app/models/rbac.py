"""RBAC 模型：角色、权限点、角色-权限关联表。"""
from app import db

# 角色-权限 多对多关联表
role_permissions = db.Table(
    'role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True),
)


class Role(db.Model):
    """角色。内置角色（is_builtin）不可删除，权限可调。"""
    __tablename__ = 'roles'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False,
                     comment='编码：superadmin/leader/keeper/producer/staff/archivist')
    name = db.Column(db.String(64), nullable=False, comment='中文名称')
    is_builtin = db.Column(db.Boolean, nullable=False, default=False, comment='内置角色不可删')
    remark = db.Column(db.String(200), nullable=False, default='', comment='备注')

    def __repr__(self) -> str:
        return '<Role %s>' % self.code


class Permission(db.Model):
    """权限点：内容由种子脚本从 PERMISSION_REGISTRY 同步。"""
    __tablename__ = 'permissions'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, comment='如 hr.manage')
    name = db.Column(db.String(64), nullable=False, comment='中文名')
    module = db.Column(db.String(32), nullable=False, comment='所属模块分组')

    # 角色多对多（Permission.roles 反向引用 Role.permissions）
    roles = db.relationship('Role', secondary=role_permissions, backref='permissions',
                            lazy='select')

    def __repr__(self) -> str:
        return '<Permission %s>' % self.code
