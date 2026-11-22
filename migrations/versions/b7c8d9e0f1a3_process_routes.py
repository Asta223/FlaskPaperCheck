"""工艺路线（工序组）：主表 + 有序工序明细。

Revision ID: b7c8d9e0f1a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-22

变更清单：
- create_table: process_routes（编码/名称/适用产品/启用/软删/备注/创建时间）
- create_table: process_route_items（路线FK + 工序FK + 顺序号）
- 明细不单独软删，随路线编辑整体替换；路线软删后由全局 loader criteria 隐藏。

约定：
- 路线编码/名称唯一性只校验未删除记录，不在数据库加 UNIQUE；
- process_route_items(route_id, seq) 唯一，process_id 建普通索引供删除守卫扫描。
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7c8d9e0f1a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'process_routes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False, comment='路线编码，如 RT01'),
        sa.Column('name', sa.String(length=64), nullable=False, comment='路线名称'),
        sa.Column('product_name', sa.String(length=128), nullable=False, server_default='',
                  comment='适用产品（提示用）'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1'),
                  comment='是否启用'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                  comment='软删除标记'),
        sa.Column('remark', sa.String(length=255), nullable=False, server_default='',
                  comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_process_routes_is_deleted', 'process_routes', ['is_deleted'])

    op.create_table(
        'process_route_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False, comment='所属工艺路线'),
        sa.Column('process_id', sa.Integer(), nullable=False, comment='引用的工序档案'),
        sa.Column('seq', sa.Integer(), nullable=False, comment='工序顺序号，从1开始'),
        sa.ForeignKeyConstraint(['process_id'], ['processes.id']),
        sa.ForeignKeyConstraint(['route_id'], ['process_routes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('route_id', 'seq', name='uq_process_route_item_route_seq'),
    )
    op.create_index('ix_process_route_item_process', 'process_route_items', ['process_id'])


def downgrade():
    # MySQL 5.5 不允许先删被外键引用的索引，drop_table 会连同索引一起删除。
    op.drop_table('process_route_items')
    op.drop_table('process_routes')
