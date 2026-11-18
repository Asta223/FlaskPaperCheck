"""P2 增量迁移：工序主数据 + 工单工序引用/消耗工时。

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-18

变更清单：
- create_table: processes（工序档案主数据）
- add_column: work_order_steps.process_id（引用工序档案，历史可空）
- add_column: work_order_steps.labor_hours（消耗工时，历史默认 0）
- add_index: processes.code/name 唯一约束随表创建；ix_step_process 索引

设计约定：
- 历史工单步骤的 name 快照保留，process_id 留空，不回溯绑定；
- 生产侧不引入审批流，仅做状态流转与留痕（人事请假审批保持不变）。
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'processes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False, comment='工序编码，如 OP01'),
        sa.Column('name', sa.String(length=64), nullable=False, comment='工序名称'),
        sa.Column('standard_hours', sa.Float(), nullable=False, default=0,
                  comment='参考工时（小时）'),
        sa.Column('sort_order', sa.Integer(), nullable=False, default=0, comment='排序号'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True, comment='是否启用'),
        sa.Column('remark', sa.String(length=255), nullable=False, default='', comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.UniqueConstraint('name'),
    )

    with op.batch_alter_table('work_order_steps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('process_id', sa.Integer(), nullable=True,
                                      comment='引用的工序档案（历史数据可空）'))
        batch_op.add_column(sa.Column('labor_hours', sa.Float(), nullable=False, default=0,
                                      comment='消耗工时（小时）'))
        batch_op.create_foreign_key('fk_step_process', 'processes', ['process_id'], ['id'])
        batch_op.create_index('ix_step_process', ['process_id'], unique=False)


def downgrade():
    with op.batch_alter_table('work_order_steps', schema=None) as batch_op:
        batch_op.drop_index('ix_step_process')
        batch_op.drop_constraint('fk_step_process', type_='foreignkey')
        batch_op.drop_column('labor_hours')
        batch_op.drop_column('process_id')
    op.drop_table('processes')
