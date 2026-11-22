"""客户档案与供应商档案：两张独立往来单位主数据表。

Revision ID: d0e1f2a4b5c6
Revises: c9d0e1f2a4b5
Create Date: 2026-11-23

变更清单：
- create_table: customers（客户档案）
- create_table: suppliers（供应商档案）
- add_column: work_orders.customer_id（关联客户，可空）+ customer_name（名称快照）
- add_column: stock_documents.supplier_id（关联供应商，可空）

约定：
- 编码/名称唯一性只校验未删除记录，数据库不加 UNIQUE；
- 两个关联外键均可空，历史工单/单据不受影响；
- 名称快照列保证客户改名/删除后历史工单显示不受影响。
"""
from alembic import op
import sqlalchemy as sa

revision = 'd0e1f2a4b5c6'
down_revision = 'c9d0e1f2a4b5'
branch_labels = None
depends_on = None


def _create_partner_table(table_name, comment):
    op.create_table(
        table_name,
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False, comment='档案编号'),
        sa.Column('name', sa.String(length=128), nullable=False, comment='单位名称'),
        sa.Column('contact', sa.String(length=64), nullable=False, server_default='',
                  comment='联系人'),
        sa.Column('phone', sa.String(length=64), nullable=False, server_default='',
                  comment='联系电话'),
        sa.Column('address', sa.String(length=255), nullable=False, server_default='',
                  comment='地址'),
        sa.Column('tax_no', sa.String(length=64), nullable=False, server_default='',
                  comment='税号'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1'),
                  comment='是否启用'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                  comment='软删除标记'),
        sa.Column('remark', sa.String(length=255), nullable=False, server_default='',
                  comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
        comment=comment,
    )
    op.create_index('ix_%s_is_deleted' % table_name, table_name, ['is_deleted'])


def upgrade():
    _create_partner_table('customers', '客户档案')
    _create_partner_table('suppliers', '供应商档案')

    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True,
                                      comment='关联客户档案（可空）'))
        batch_op.add_column(sa.Column('customer_name', sa.String(length=128), nullable=False,
                                      server_default='', comment='客户名称快照'))
        batch_op.create_index('ix_work_orders_customer_id', ['customer_id'])
        batch_op.create_foreign_key('fk_work_orders_customer', 'customers',
                                    ['customer_id'], ['id'])

    with op.batch_alter_table('stock_documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('supplier_id', sa.Integer(), nullable=True,
                                      comment='关联供应商档案（可空）'))
        batch_op.create_index('ix_stock_documents_supplier_id', ['supplier_id'])
        batch_op.create_foreign_key('fk_stock_documents_supplier', 'suppliers',
                                    ['supplier_id'], ['id'])


def downgrade():
    with op.batch_alter_table('stock_documents', schema=None) as batch_op:
        batch_op.drop_constraint('fk_stock_documents_supplier', type_='foreignkey')
        batch_op.drop_index('ix_stock_documents_supplier_id')
        batch_op.drop_column('supplier_id')
    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_work_orders_customer', type_='foreignkey')
        batch_op.drop_index('ix_work_orders_customer_id')
        batch_op.drop_column('customer_name')
        batch_op.drop_column('customer_id')
    op.drop_table('suppliers')
    op.drop_table('customers')
