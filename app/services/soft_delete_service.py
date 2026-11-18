"""软删除统一入口：标记删除 / 恢复 / 物理清除 + 操作日志（同事务）。

删除只置 is_deleted=True，记录保留在库中，由全局查询过滤隐藏，管理员可在
"系统管理 → 回收站"恢复；只有管理员在回收站点"彻底删除"时才物理清除。
"""
from sqlalchemy import delete, select, update

from app import db
from app.services.log_service import log_operation


def mark_deleted(obj, *, module: str, target_type: str, label: str = '',
                 operator_id=None, summary: str = None):
    """标记软删除并写操作日志，返回展示用标签。"""
    obj.is_deleted = True
    log_operation(
        module=module, action='delete', target_type=target_type,
        target_id=obj.id,
        summary=summary or '删除%s#%s' % (label, obj.id),
        operator_id=operator_id,
    )
    db.session.commit()
    return label


def restore_record(obj, *, module: str, target_type: str, label: str = '',
                   operator_id=None, summary: str = None):
    """从回收站恢复并写操作日志。"""
    obj.is_deleted = False
    log_operation(
        module=module, action='restore', target_type=target_type,
        target_id=obj.id,
        summary=summary or '从回收站恢复%s#%s' % (label, obj.id),
        operator_id=operator_id,
    )
    db.session.commit()
    return label


def _incoming_fks(table_name):
    """列出所有引用 table_name 的 (子表, 外键列)。"""
    result = []
    for child in db.metadata.tables.values():
        for col in child.columns:
            if not col.foreign_keys:
                continue
            if any(fk.target_fullname.split('.')[0] == table_name
                   for fk in col.foreign_keys):
                result.append((child, col))
    return result


def _purge_rows(table_name, ids, _depth=0):
    """物理删除指定行，并处理所有指向它的外键。

    规则（保证任何外键都不会残留悬空引用）：
    - 可空外键（如操作日志.操作人、部门.负责人）：置 NULL，审计/业务行保留；
    - 不可空外键：先递归删除引用行（子记录随父记录一并彻底删除）；
    - 无主键的纯关联表（user_roles / role_permissions 等）：直接删除关联行。
    """
    if not ids or _depth > 15:
        return
    table = db.metadata.tables.get(table_name)
    if table is None:
        return
    for child, col in _incoming_fks(table_name):
        if child.name == table_name:
            # 自引用（部门/分类的 parent_id 均可空）：置空避免断链
            if col.nullable:
                db.session.execute(
                    update(child).where(col.in_(ids)).values(**{col.name: None})
                )
            continue
        if col.nullable:
            db.session.execute(
                update(child).where(col.in_(ids)).values(**{col.name: None})
            )
            continue
        child_pk = child.columns.get('id')
        if child_pk is None:
            db.session.execute(delete(child).where(col.in_(ids)))
            continue
        child_ids = [row[0] for row in db.session.execute(
            select(child_pk).where(col.in_(ids))
        ).all()]
        _purge_rows(child.name, child_ids, _depth + 1)
    pk_col = table.columns.get('id')
    db.session.execute(delete(table).where(pk_col.in_(ids)))


def purge_record(obj, *, module: str, target_type: str, label: str = '',
                 operator_id=None, summary: str = None):
    """物理硬删除回收站记录（不可恢复）并写操作日志。

    外键处理：可空外键（如操作日志.操作人、部门.负责人）一律置 NULL 保留历史行；
    不可空外键的引用行随主记录一并物理删除（这些子记录已随主记录先被软删）。
    调用方应先用 find_references() 确认不存在"仍在使用"的活引用。
    """
    pk = obj.id
    table_name = obj.__tablename__
    _purge_rows(table_name, [pk])
    db.session.expunge(obj)
    log_operation(
        module=module, action='purge', target_type=target_type,
        target_id=pk,
        summary=summary or '彻底删除%s「%s」（不可恢复）' % (label, pk),
        operator_id=operator_id,
    )
    db.session.commit()
