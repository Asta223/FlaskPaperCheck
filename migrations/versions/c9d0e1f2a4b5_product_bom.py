"""产品档案与单层 BOM：生产主数据补齐。

Revision ID: c9d0e1f2a4b5
Revises: b8c9d0e1f2a4
Create Date: 2026-11-22

变更清单：
- create_table: products（编号/名称/规格/单位/启用/软删/备注/创建时间）
- create_table: bom_items（产品FK + 物料FK + 单件用量 + 单位快照 + 软删）
- add_column: process_routes.product_id（关联产品，可空，历史路线保留自由文本）
- add_column: work_orders.product_id（关联产品，可空，历史工单保留自由文本）

约定：
- 产品编码/名称唯一性只校验未删除记录，数据库不加 UNIQUE；
- bom_items(product_id, material_id) 唯一；明细编辑为物理替换，软删标记随产品同步；
- 两个关联外键均可空，保证历史数据迁移后不受影响。
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f2a4b5'
down_revision = 'b8c9d0e1f2a4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False, comment='产品编号，如 PRD001'),
        sa.Column('name', sa.String(length=128), nullable=False, comment='产品名称'),
        sa.Column('spec', sa.String(length=128), nullable=False, server_default='', comment='规格型号'),
        sa.Column('unit', sa.String(length=16), nullable=False, server_default='个', comment='计量单位'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1'),
                  comment='是否启用'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                  comment='软删除标记'),
        sa.Column('remark', sa.String(length=255), nullable=False, server_default='', comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_products_is_deleted', 'products', ['is_deleted'])

    op.create_table(
        'bom_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False, comment='所属产品'),
        sa.Column('material_id', sa.Integer(), nullable=False, comment='引用的物料档案'),
        sa.Column('quantity', sa.Float(), nullable=False, server_default='1',
                  comment='单件标准用量'),
        sa.Column('unit', sa.String(length=16), nullable=False, server_default='', comment='单位快照'),
        sa.Column('remark', sa.String(length=255), nullable=False, server_default='', comment='备注'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                  comment='软删除标记：随产品一起隐藏'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['material_id'], ['materials.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'material_id', name='uq_bom_product_material'),
    )
    op.create_index('ix_bom_item_material', 'bom_items', ['material_id'])
    op.create_index('ix_bom_items_is_deleted', 'bom_items', ['is_deleted'])

    with op.batch_alter_table('process_routes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('product_id', sa.Integer(), nullable=True,
                                      comment='关联产品档案（可空）'))
        batch_op.create_index('ix_process_routes_product_id', ['product_id'])
        batch_op.create_foreign_key('fk_process_routes_product', 'products',
                                    ['product_id'], ['id'])

    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('product_id', sa.Integer(), nullable=True,
                                      comment='关联产品档案（可空）'))
        batch_op.create_index('ix_work_orders_product_id', ['product_id'])
        batch_op.create_foreign_key('fk_work_orders_product', 'products',
                                    ['product_id'], ['id'])


def downgrade():
    # MySQL 5.5 不支持先删被外键引用的索引；drop_table 会连同索引一起删除。
    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_work_orders_product', type_='foreignkey')
        batch_op.drop_index('ix_work_orders_product_id')
        batch_op.drop_column('product_id')
    with op.batch_alter_table('process_routes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_process_routes_product', type_='foreignkey')
        batch_op.drop_index('ix_process_routes_product_id')
        batch_op.drop_column('product_id')
    op.drop_table('bom_items')
    op.drop_table('products')
