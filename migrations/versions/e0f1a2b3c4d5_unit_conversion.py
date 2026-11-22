"""计量单位档案、物料换算关系，以及出入库单据的录入单位快照。

Revision ID: e0f1a2b3c4d5
Revises: d0e1f2a4b5c6
Create Date: 2026-11-23

变更清单：
- create_table: units（计量单位主数据，含量纲 dimension）
- create_table: unit_conversions（物料换算：1 单位 = factor 基本单位）
- add_column: stock_documents.unit_id / unit_name / factor / input_quantity

约定：
- 库存与流水始终以物料基本单位记账；单据额外保存用户录入数量、单位与系数快照；
- 历史单据 input_quantity 回填为 quantity，unit_id 留空表示按基本单位收发；
- 单位/换算关系可软删，回收站可恢复；编码名称唯一性只在应用层校验未删除记录。
"""
from alembic import op
import sqlalchemy as sa

revision = 'e0f1a2b3c4d5'
down_revision = 'd0e1f2a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'units',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False, comment='单位编码'),
        sa.Column('name', sa.String(length=32), nullable=False, comment='单位名称'),
        sa.Column('dimension', sa.String(length=16), nullable=False, server_default='quantity',
                  comment='量纲：quantity/weight/length/volume'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1'),
                  comment='是否启用'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                  comment='软删除标记'),
        sa.Column('remark', sa.String(length=255), nullable=False, server_default='',
                  comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_units_is_deleted', 'is_deleted'),
        comment='计量单位档案',
    )
    op.create_table(
        'unit_conversions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('material_id', sa.Integer(), nullable=False, comment='物料'),
        sa.Column('unit_id', sa.Integer(), nullable=False, comment='换算单位'),
        sa.Column('factor', sa.Float(), nullable=False,
                  comment='1 换算单位 = factor 基本单位'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                  comment='软删除标记'),
        sa.Column('remark', sa.String(length=255), nullable=False, server_default='',
                  comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['material_id'], ['materials.id'],
                                name='fk_unit_conversion_material'),
        sa.ForeignKeyConstraint(['unit_id'], ['units.id'], name='fk_unit_conversion_unit'),
        sa.UniqueConstraint('material_id', 'unit_id', name='uq_unit_conversion_mat_unit'),
        sa.Index('ix_unit_conversion_material', 'material_id'),
        sa.Index('ix_unit_conversion_unit', 'unit_id'),
        sa.Index('ix_unit_conversion_is_deleted', 'is_deleted'),
        comment='物料单位换算关系',
    )

    with op.batch_alter_table('stock_documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('unit_id', sa.Integer(), nullable=True,
                                      comment='录入单位（换算单位，可空=基本单位）'))
        batch_op.add_column(sa.Column('unit_name', sa.String(length=32), nullable=False,
                                      server_default='', comment='录入单位名称快照'))
        batch_op.add_column(sa.Column('factor', sa.Float(), nullable=True,
                                      comment='录入时换算系数快照'))
        batch_op.add_column(sa.Column('input_quantity', sa.Integer(), nullable=True,
                                      comment='用户录入数量（基本单位数量见 quantity）'))
        batch_op.create_index('ix_stock_documents_unit_id', ['unit_id'])
        batch_op.create_foreign_key('fk_stock_documents_unit', 'units', ['unit_id'], ['id'])

    op.execute('UPDATE stock_documents SET input_quantity = quantity WHERE input_quantity IS NULL')


def downgrade():
    with op.batch_alter_table('stock_documents', schema=None) as batch_op:
        batch_op.drop_constraint('fk_stock_documents_unit', type_='foreignkey')
        batch_op.drop_index('ix_stock_documents_unit_id')
        batch_op.drop_column('input_quantity')
        batch_op.drop_column('factor')
        batch_op.drop_column('unit_name')
        batch_op.drop_column('unit_id')
    op.drop_table('unit_conversions')
    op.drop_table('units')
