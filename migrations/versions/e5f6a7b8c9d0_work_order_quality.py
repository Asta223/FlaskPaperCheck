"""P2-6 迁移：不良原因主数据 + 工单质量记录字段。

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-18

变更清单：
- create_table: defect_reasons（不良原因主数据，支持软删除/回收站）
- add_column: work_orders 成品/良品/不良数量、良率、不良率、不良原因、质量备注、记录人/时间
- add_index / FK: work_orders.defect_reason_id → defect_reasons.id

设计约定：
- 所有新增数字列给 server_default，兼容 MySQL 5.5 已有数据；
- 良率/不良率由应用层 record_quality() 统一计算后写入，不在数据库做触发器；
- 历史工单质量字段默认为 0/空，不回溯推导，避免把历史完工数据误判为质量已记录。
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'defect_reasons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False, comment='原因编码，如 DR01'),
        sa.Column('name', sa.String(length=64), nullable=False, comment='不良原因名称'),
        sa.Column('category', sa.String(length=64), nullable=False, server_default='',
                  comment='原因分类，如来料/工艺/设备'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1'),
                  comment='是否启用'),
        sa.Column('remark', sa.String(length=255), nullable=False, server_default='',
                  comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                  comment='软删除标记：页面默认不显示，可在回收站恢复'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_defect_reasons_is_deleted', 'defect_reasons', ['is_deleted'])

    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('output_qty', sa.Integer(), nullable=False,
                                      server_default='0', comment='成品数量（良品+不良）'))
        batch_op.add_column(sa.Column('good_qty', sa.Integer(), nullable=False,
                                      server_default='0', comment='合格数量'))
        batch_op.add_column(sa.Column('defect_qty', sa.Integer(), nullable=False,
                                      server_default='0', comment='不良数量'))
        batch_op.add_column(sa.Column('yield_rate', sa.Float(), nullable=False,
                                      server_default='0', comment='良率(%)'))
        batch_op.add_column(sa.Column('defect_rate', sa.Float(), nullable=False,
                                      server_default='0', comment='不良率(%)'))
        batch_op.add_column(sa.Column('defect_reason_id', sa.Integer(), nullable=True,
                                      comment='不良原因（引用主数据）'))
        batch_op.add_column(sa.Column('quality_remark', sa.String(length=500), nullable=False,
                                      server_default='', comment='质量备注'))
        batch_op.add_column(sa.Column('quality_recorded_at', sa.DateTime(), nullable=True,
                                      comment='质量记录时间'))
        batch_op.add_column(sa.Column('quality_recorded_by', sa.Integer(), nullable=True,
                                      comment='质量记录人'))
        batch_op.create_foreign_key('fk_wo_defect_reason', 'defect_reasons',
                                    ['defect_reason_id'], ['id'])
        batch_op.create_foreign_key('fk_wo_quality_recorder', 'users',
                                    ['quality_recorded_by'], ['id'])
        batch_op.create_index('ix_wo_defect_reason', ['defect_reason_id'], unique=False)
        batch_op.create_index('ix_wo_quality_recorder', ['quality_recorded_by'], unique=False)


def downgrade():
    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.drop_index('ix_wo_quality_recorder')
        batch_op.drop_index('ix_wo_defect_reason')
        batch_op.drop_constraint('fk_wo_quality_recorder', type_='foreignkey')
        batch_op.drop_constraint('fk_wo_defect_reason', type_='foreignkey')
        for column in ('quality_recorded_by', 'quality_recorded_at', 'quality_remark',
                       'defect_reason_id', 'defect_rate', 'yield_rate', 'defect_qty',
                       'good_qty', 'output_qty'):
            batch_op.drop_column(column)
    op.drop_index('ix_defect_reasons_is_deleted', table_name='defect_reasons')
    op.drop_table('defect_reasons')
