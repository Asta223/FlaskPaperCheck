"""L1 轻量排产迁移：工单倒排计划字段 + 优先级 + 人工覆盖标记。

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-18

变更清单：
- add_column: work_orders.plan_start_date / plan_end_date（可空，历史行留 NULL，不回填）
- add_column: work_orders.priority（非空，server_default='normal'）
- add_column: work_orders.plan_manual（非空，server_default=0）

设计约定（架构文档 §7）：
- 两个日期列不加 server_default，禁止伪造历史计划；
- 取值域 high/normal/low 由表单 choices + service 兜底，不在数据库加 CHECK（MySQL 5.5 会忽略）；
- 本增量无新表、无新索引；downgrade 按逆序 drop_column。
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plan_start_date', sa.Date(), nullable=True,
                                      comment='计划开工日（倒推的最晚开工日）'))
        batch_op.add_column(sa.Column('plan_end_date', sa.Date(), nullable=True,
                                      comment='计划完工日（=交期）'))
        batch_op.add_column(sa.Column('priority', sa.String(length=10), nullable=False,
                                      server_default='normal', comment='优先级 high/normal/low'))
        batch_op.add_column(sa.Column('plan_manual', sa.Boolean(), nullable=False,
                                      server_default=sa.text('0'), comment='人工覆盖标记'))


def downgrade():
    with op.batch_alter_table('work_orders', schema=None) as batch_op:
        batch_op.drop_column('plan_manual')
        batch_op.drop_column('priority')
        batch_op.drop_column('plan_end_date')
        batch_op.drop_column('plan_start_date')
