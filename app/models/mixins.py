"""软删除公共能力。

约定（2026-11-18 需求变更）：
- 所有用户可新增的数据都支持"删除"，但删除只置 is_deleted=True，数据库记录保留；
- 页面、列表、下拉、详情、关联展示一律看不到已删除记录；
- 管理员可通过"系统管理 → 回收站"查看并恢复；
- 出入库单据软删时仍反向冲销库存（见 inventory_service.reverse_stock_document）。

实现要点：
- 使用 SQLAlchemy 2.0 的 with_loader_criteria 在 Session 级统一过滤，
  Query / select / Session.get / 关联懒加载都会自动排除已删除行；
- 回收站等需要看到已删除数据的查询，加 .execution_options(include_deleted=True) 绕过；
- 只过滤 ORM SELECT，不干扰 Core SQL 与写入操作。
"""
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app import db


class SoftDeleteMixin:
    """可软删模型混入类：提供 is_deleted 字段与两个语义化方法。"""

    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True,
                           comment='软删除标记：页面默认不显示，可在回收站恢复')

    def soft_delete(self):
        """标记删除（不物理删除，业务数据仍可追溯）。"""
        self.is_deleted = True
        return self

    def restore(self):
        """从回收站恢复。"""
        self.is_deleted = False
        return self


def _soft_delete_mappers():
    """返回所有带 is_deleted 列的 ORM mapper（随模型定义自动发现）。"""
    for mapper in list(db.Model.registry.mappers):
        if 'is_deleted' in mapper.columns:
            yield mapper


@event.listens_for(Session, 'do_orm_execute')
def _exclude_soft_deleted(execute_state):
    """全局过滤：除显式 include_deleted 外，所有 ORM 查询排除已删除记录。"""
    if not execute_state.is_select:
        return
    if execute_state.execution_options.get('include_deleted'):
        return
    for mapper in _soft_delete_mappers():
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(mapper, lambda cls: cls.is_deleted.is_(False),
                                 include_aliases=True)
        )
