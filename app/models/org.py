"""组织架构：部门（邻接表树形 + 负责人）。"""
from app import db
from app.models.mixins import SoftDeleteMixin


class Department(SoftDeleteMixin, db.Model):
    """部门：parent_id 自引用树；leader_id 用 use_alter 解 User↔Department 循环外键。"""
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, comment='部门名称')
    parent_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True,
                          comment='上级部门，空为根')
    leader_id = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True,
                                                    name='fk_departments_leader'),
                          nullable=True, comment='部门负责人')
    sort_order = db.Column(db.Integer, nullable=False, default=0, comment='排序号')
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment='停用=软删')

    parent = db.relationship('Department', remote_side=[id], backref='children')
    leader = db.relationship('User', foreign_keys=[leader_id])

    @classmethod
    def get_tree(cls, include_inactive: bool = False) -> list:
        """内存组装部门树（规模小，无需 CTE）。

        返回 [{'dept': Department, 'children': [node, ...]}, ...]
        """
        query = cls.query
        if not include_inactive:
            query = query.filter_by(is_active=True)
        depts = query.order_by(cls.sort_order, cls.id).all()
        nodes = {d.id: {'dept': d, 'children': []} for d in depts}
        roots = []
        for d in depts:
            node = nodes[d.id]
            if d.parent_id and d.parent_id in nodes and d.parent_id != d.id:
                nodes[d.parent_id]['children'].append(node)
            else:
                roots.append(node)
        return roots

    def descendant_ids(self) -> list:
        """全部子孙部门 id（含自身）。"""
        ids = [self.id]
        frontier = [self.id]
        while frontier:
            children = (db.session.query(Department.id)
                        .filter(Department.parent_id.in_(frontier),
                                Department.is_active.is_(True))
                        .all())
            child_ids = [c[0] for c in children if c[0] not in ids]
            ids.extend(child_ids)
            frontier = child_ids
        return ids

    def __repr__(self) -> str:
        return '<Department %s>' % self.name
