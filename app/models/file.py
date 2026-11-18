"""文件管理模型：分类、工厂文件、角色可见范围关联表。"""
import uuid

from app import db
from app.models.mixins import SoftDeleteMixin
from app.utils.time_utils import now

# 文件-角色 可见范围 多对多关联表
file_role_visibility = db.Table(
    'file_role_visibility',
    db.Column('file_id', db.Integer, db.ForeignKey('factory_files.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
)

# 文件-部门 可见范围 多对多关联表（P1-10）
file_department_visibility = db.Table(
    'file_department_visibility',
    db.Column('file_id', db.Integer, db.ForeignKey('factory_files.id'), primary_key=True),
    db.Column('department_id', db.Integer, db.ForeignKey('departments.id'), primary_key=True),
)


class FileCategory(SoftDeleteMixin, db.Model):
    """文件分类：parent_id 自引用，可空为根分类。"""
    __tablename__ = 'file_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, comment='分类名称')
    parent_id = db.Column(db.Integer, db.ForeignKey('file_categories.id'), nullable=True,
                          comment='上级分类')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='停用=软删')

    parent = db.relationship('FileCategory', remote_side=[id], backref='children')

    def __repr__(self) -> str:
        return '<FileCategory %s>' % self.name


class FactoryFile(SoftDeleteMixin, db.Model):
    """工厂文件：磁盘文件名用 uuid 防冲突，原文件名存库；可见范围 all/roles。"""
    __tablename__ = 'factory_files'

    VISIBILITY_LABELS = {'all': '全员可见', 'roles': '指定角色', 'departments': '指定部门'}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, comment='显示名')
    original_filename = db.Column(db.String(200), nullable=False, comment='原始文件名')
    stored_filename = db.Column(db.String(128), nullable=False, comment='磁盘存储名（uuid）')
    file_ext = db.Column(db.String(16), nullable=False, default='', comment='扩展名')
    size_bytes = db.Column(db.Integer, nullable=False, default=0, comment='文件大小(字节)')
    category_id = db.Column(db.Integer, db.ForeignKey('file_categories.id'), nullable=True,
                            comment='分类，可空')
    visibility_type = db.Column(db.String(16), nullable=False, default='all',
                                comment='all=全员 roles=指定角色 departments=指定部门')
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='上传人')
    created_at = db.Column(db.DateTime, nullable=False, default=now, comment='上传时间')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='停用=软删')

    category = db.relationship('FileCategory', backref='files')
    uploader = db.relationship('User', foreign_keys=[uploaded_by])
    visible_roles = db.relationship('Role', secondary=file_role_visibility,
                                    backref='visible_files', lazy='select')
    visible_departments = db.relationship('Department', secondary=file_department_visibility,
                                          backref='visible_files', lazy='select')

    def can_view(self, user) -> bool:
        """下载/预览前校验可见范围：all 放行；roles 角色交集；departments 部门（含子部门）命中；
        上传人与 superadmin 始终可见。"""
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        if self.visibility_type == 'all':
            return True
        if self.uploaded_by == user.id:
            return True
        if user.has_role('superadmin'):
            return True
        if self.visibility_type == 'roles':
            user_role_ids = {role.id for role in user.roles}
            file_role_ids = {role.id for role in self.visible_roles}
            return bool(user_role_ids & file_role_ids)
        if self.visibility_type == 'departments':
            from app.models.org import Department
            # 文件的可见部门（每个部门含其子孙）；用户部门命中任一集合即可见
            own_dept = user.department_id
            if not own_dept:
                return False
            for dept in self.visible_departments:
                if own_dept in set(dept.descendant_ids()):
                    return True
            return False
        return False

    @staticmethod
    def new_stored_filename(ext: str) -> str:
        """生成磁盘存储文件名（uuid 防冲突）。"""
        return uuid.uuid4().hex + (ext or '')

    @property
    def size_display(self) -> str:
        """人性化文件大小。"""
        size = self.size_bytes or 0
        if size >= 1024 * 1024:
            return '%.1f MB' % (size / 1024 / 1024)
        if size >= 1024:
            return '%.1f KB' % (size / 1024)
        return '%d B' % size

    def __repr__(self) -> str:
        return '<FactoryFile %s>' % self.name
