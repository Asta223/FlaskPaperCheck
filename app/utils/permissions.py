"""RBAC 权限体系：权限点注册表 + 装饰器 + 权限查询。

约定（架构文档共享知识 §1/§7）：
- 权限点命名 `模块.动作`，全部小写，只在 PERMISSION_REGISTRY 声明一次；
  菜单渲染、角色勾选矩阵、种子数据、装饰器校验四处共用，禁止模板硬编码。
- 持有内置角色 superadmin 的用户直接放行全部权限。
- 权限码按请求缓存（flask.g），同一请求内不重复查库。
"""
from functools import wraps

from flask import abort, g
from flask_login import current_user

# 内置超级管理员角色编码
SUPERADMIN_CODE = 'superadmin'

# 权限点注册表：{模块中文名: {权限点: 中文名}}
PERMISSION_REGISTRY = {
    '人员管理': {
        'hr.view': '员工查看',
        'hr.manage': '员工管理',
    },
    '部门管理': {
        'dept.manage': '部门管理',
    },
    '角色权限': {
        'rbac.manage': '角色权限管理',
    },
    '考勤管理': {
        'attendance.clock': '考勤打卡',
        'attendance.view': '考勤查看',
        'attendance.view_all': '考勤查看全部',
        'attendance.leave.apply': '请假申请',
        'attendance.leave.approve': '请假审批',
        'attendance.summary.view': '部门考勤汇总',
    },
    '生产管理': {
        'production.view': '工单查看',
        'production.manage': '工单管理',
        'production.issue': '工单领料',
    },
    '物料管理': {
        'material.manage': '物料管理',
    },
    '仓库管理': {
        'warehouse.view': '库存查看',
        'warehouse.manage': '出入库管理',
        'warehouse.ledger.view': '库存流水查询',
    },
    '文件管理': {
        'files.view': '文件查看',
        'files.manage': '文件管理',
    },
    '系统管理': {
        'system.log.view': '操作日志查看',
        'system.export': '数据导出',
    },
}

# 全部权限码集合（由注册表推导，避免两处维护）
ALL_PERMISSION_CODES = {
    code for perms in PERMISSION_REGISTRY.values() for code in perms
}


def get_user_permission_codes(user) -> set:
    """查询用户的全部权限码集合；superadmin 返回全集。"""
    if user is None or not getattr(user, 'is_authenticated', False):
        return set()
    if user.has_role(SUPERADMIN_CODE):
        return set(ALL_PERMISSION_CODES)
    # 延迟导入避免模型包加载顺序问题
    from app.models.rbac import Permission, Role, role_permissions
    from app.models.user import user_roles
    rows = (
        db.session.query(Permission.code)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(Role, Role.id == role_permissions.c.role_id)
        .join(user_roles, user_roles.c.role_id == Role.id)
        .filter(user_roles.c.user_id == user.id)
        .all()
    )
    return {row[0] for row in rows}


# 局部导入 db（模块级导入会产生循环依赖：models -> app -> utils）
from app import db  # noqa: E402


def user_permissions(user) -> set:
    """本请求内缓存的用户权限集合。"""
    key = '_perm_codes_%s' % user.id
    if not hasattr(g, key):
        setattr(g, key, get_user_permission_codes(user))
    return getattr(g, key)


def has_permission(user, code: str) -> bool:
    """判断用户是否持有指定权限点。"""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    return code in user_permissions(user)


def permission_required(*codes):
    """视图装饰器：任一权限点满足即放行；superadmin 放行；否则 403。

    用法：@bp.route(...) / @login_required / @permission_required('hr.view')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not any(has_permission(current_user, c) for c in codes):
                abort(403)
            return view_func(*args, **kwargs)
        return wrapper
    return decorator
