"""硬删除守卫：物理删除前统一检测引用，避免留下悬挂数据。

设计原则（小型工厂"线上留痕"定位）：
- 凡用户可新增的数据，都提供"彻底删除"入口——误建的错误数据不需要停用/复用。
- 但硬删除不能抹掉业务历史：仍有其他业务记录引用时拒绝删除，并明确列出引用来源。
- 多对多关联表属于主记录的附属关系，删除主记录时自动清理，不算"引用"。
- 操作日志是审计留痕，永不删除；删除员工账号时只把 operator_id 置空（摘要仍含姓名）。
- 库存流水等不可变审计数据不在任何删除范围内。
"""
from sqlalchemy import func, inspect, select, text

from app import db

# 多对多关联表：随主记录一起清理，不作为阻止删除的引用
ASSOCIATION_TABLES = {
    'user_roles', 'role_permissions',
    'file_role_visibility', 'file_department_visibility',
}

# 删除员工时可一并清理的个人辅助数据（非审计留痕）
USER_PURGE_TABLES = ('notifications', 'chat_messages', 'conversation_reads')

TABLE_LABELS = {
    'users': '员工', 'departments': '部门', 'roles': '角色', 'permissions': '权限点',
    'attendance_records': '考勤记录', 'leave_requests': '请假申请',
    'work_orders': '生产工单', 'work_order_steps': '工单工序', 'processes': '工序档案',
    'materials': '物料', 'material_categories': '物料分类',
    'warehouses': '仓库', 'inventories': '库存记录', 'stock_documents': '出入库单据',
    'stock_ledgers': '库存流水', 'stock_warning_states': '库存预警状态',
    'factory_files': '文件', 'file_categories': '文件分类',
    'chat_messages': '聊天消息', 'notifications': '站内通知',
    'conversation_reads': '会话已读位点', 'operation_logs': '操作日志',
}


def find_references(obj, *, extra_ignore=()):
    """扫描全库外键，返回仍引用 obj 的业务表及条数：{表名: 条数}。

    默认忽略多对多关联表（附属关系）与操作日志（审计留痕，另行置空操作人）。
    extra_ignore 用于传入会被一并清理的表（如员工删除时的聊天/通知）。
    """
    target_table = obj.__tablename__
    primary_key = inspect(obj).mapper.primary_key[0]
    pk_value = getattr(obj, primary_key.name)
    if pk_value is None:
        return {}
    ignore = set(ASSOCIATION_TABLES) | {'operation_logs'} | set(extra_ignore)
    refs = {}
    for mapper in list(db.Model.registry.mappers):
        table = mapper.local_table
        if table.name in ignore or table.name == target_table:
            continue
        for column in table.columns:
            if not column.foreign_keys:
                continue
            if not any(fk.target_fullname.split('.')[0] == target_table
                       for fk in column.foreign_keys):
                continue
            count = db.session.execute(
                select(func.count()).select_from(table).where(column == pk_value)
            ).scalar() or 0
            if count:
                refs[table.name] = refs.get(table.name, 0) + count
    return refs


def format_references(refs):
    """把引用字典转成中文提示。"""
    return '、'.join('%s %d 条' % (TABLE_LABELS.get(name, name), count)
                    for name, count in sorted(refs.items()))


def purge_associations(obj):
    """清理该对象的全部多对多关联行（SQLAlchemy secondary）。"""
    primary_key = inspect(obj).mapper.primary_key[0]
    pk_value = getattr(obj, primary_key.name)
    for relationship in inspect(obj).mapper.relationships:
        if relationship.secondary is None:
            continue
        for column in relationship.secondary.columns:
            if any(fk.target_fullname.split('.')[0] == obj.__tablename__
                   for fk in column.foreign_keys):
                db.session.execute(relationship.secondary.delete().where(column == pk_value))


def purge_user_auxiliary(user_id):
    """删除员工账号时清理个人辅助数据，并把操作日志的操作人置空。

    聊天/通知/已读位点随账号删除；操作日志保留，仅置空 operator_id。
    """
    db.session.execute(text('DELETE FROM notifications WHERE receiver_id = :uid'),
                       {'uid': user_id})
    db.session.execute(text('DELETE FROM chat_messages WHERE sender_id = :uid '
                            'OR receiver_id = :uid'), {'uid': user_id})
    db.session.execute(text('DELETE FROM conversation_reads WHERE user_id = :uid '
                            'OR peer_id = :uid'), {'uid': user_id})
    db.session.execute(text('UPDATE operation_logs SET operator_id = NULL '
                            'WHERE operator_id = :uid'), {'uid': user_id})
