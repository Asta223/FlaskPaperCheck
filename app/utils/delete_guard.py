"""删除守卫：检测仍在使用中的引用，避免隐藏主数据后历史页面断链。

软删除改造后（2026-11-18）：
- 删除=置 is_deleted=True，记录保留在库中，页面/下拉默认不显示，回收站可恢复；
- 已软删的子记录不再算作有效引用（它们本身也不可见）；
- 多对多关联表与主记录同生命周期，不算引用；
- 操作日志、库存流水等审计数据永不删除。
"""
from sqlalchemy import func, inspect, select

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
    'defect_reasons': '不良原因',
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
        soft_col = table.columns.get('is_deleted')
        for column in table.columns:
            if not column.foreign_keys:
                continue
            if not any(fk.target_fullname.split('.')[0] == target_table
                       for fk in column.foreign_keys):
                continue
            where = column == pk_value
            if soft_col is not None:
                where = db.and_(where, soft_col.is_(False))
            count = db.session.execute(
                select(func.count()).select_from(table).where(where)
            ).scalar() or 0
            if count:
                refs[table.name] = refs.get(table.name, 0) + count
    return refs


def format_references(refs):
    """把引用字典转成中文提示。"""
    return '、'.join('%s %d 条' % (TABLE_LABELS.get(name, name), count)
                    for name, count in sorted(refs.items()))
