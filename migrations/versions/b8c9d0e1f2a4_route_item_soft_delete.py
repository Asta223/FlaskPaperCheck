"""工艺路线明细软删标记：随路线软删/恢复同步，避免已删路线占用工序引用。

Revision ID: b8c9d0e1f2a4
Revises: b7c8d9e0f1a3
Create Date: 2026-11-22

变更清单：
- add_column: process_route_items.is_deleted（非空，server_default=0，带索引）
- 明细编辑仍为物理替换；软删/恢复路线时由业务层同步明细标记。
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8c9d0e1f2a4'
down_revision = 'b7c8d9e0f1a3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('process_route_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=False,
                                      server_default=sa.text('0'),
                                      comment='软删除标记：随路线一起隐藏'))
        batch_op.create_index('ix_process_route_items_is_deleted', ['is_deleted'])


def downgrade():
    with op.batch_alter_table('process_route_items', schema=None) as batch_op:
        batch_op.drop_index('ix_process_route_items_is_deleted')
        batch_op.drop_column('is_deleted')
