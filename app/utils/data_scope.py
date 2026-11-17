"""部门数据权限收窄（P1-04）：仅注入读查询出口，与功能权限取交集。

约定（架构 §7.3）：
- visible_department_ids(user) -> list[int] | None：None=不收窄；结果缓存 flask.g。
  - superadmin → None（完全豁免）；
  - leader 角色且命中 Department.leader_id → 该部门及全部子孙 id（A5）；
  - 其他角色 → None（维持 P0 现状，不因缺少 view_all 而越权）。
- apply_dept_scope(query, column, user)：向 query 追加 column IN scope（scope=None 原样返回）。
- is_scoped_leader(user)：是否为受数据权限约束的主管。
"""
from flask import g

# 内置角色编码（避免与 rbac 模块循环导入）
SUPERADMIN_CODE = 'superadmin'
LEADER_CODE = 'leader'


def is_scoped_leader(user) -> bool:
    """用户是否持 leader 角色且为某部门负责人（受数据权限约束的主管）。"""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if user.has_role(SUPERADMIN_CODE):
        return False
    if not user.has_role(LEADER_CODE):
        return False
    from app.models.org import Department
    return Department.query.filter_by(leader_id=user.id).first() is not None


def visible_department_ids(user):
    """当前用户可见的部门 id 集合；None 表示不收窄。缓存到 flask.g。"""
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    # superadmin 完全豁免
    try:
        if user.has_role(SUPERADMIN_CODE):
            return None
    except Exception:
        return None
    if not user.has_role(LEADER_CODE):
        return None

    key = '_scope_dept_ids_%s' % user.id
    if hasattr(g, key):
        return getattr(g, key)

    from app.models.org import Department
    led_dept = Department.query.filter_by(leader_id=user.id).first()
    if led_dept is None:
        ids = []
    else:
        ids = led_dept.descendant_ids()
    setattr(g, key, ids)
    return ids


def apply_dept_scope(query, column, user):
    """向 SQLAlchemy query 追加部门 IN 过滤（scope=None 时原样返回）。

    Args:
        query: 已有 query 对象。
        column: 要过滤的 ORM 列/表达式（如 User.department_id 或 coalesce 表达式）。
        user: 当前用户。
    """
    ids = visible_department_ids(user)
    if ids is None:
        return query
    if not ids:
        # 空集合：注入恒假条件，返回空结果且不报错
        return query.filter(column.in_([]))
    return query.filter(column.in_(ids))
