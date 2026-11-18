"""软删除统一入口：标记删除 / 恢复 + 操作日志（同事务）。

删除只置 is_deleted=True，绝不物理删除；记录保留在库中，由全局查询过滤隐藏，
管理员可在"系统管理 → 回收站"恢复。
"""
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
