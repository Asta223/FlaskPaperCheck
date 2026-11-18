"""P2-2 增量迁移：物料档案增加存放位置（仓位/货位）。

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-18

变更清单：
- add_column: materials.storage_location（存放位置/货位，文本，可空）

设计约定：
- 单一文本字段描述"什么仓库的什么货位"（如「原材料仓 A区-03排-2层」），
  贴合小型工厂线上留痕定位；出入库单据/领料下拉直接带出该提示，便于人员定位；
- 不引入独立的库位表或多维度关联，避免与库存（仓库×物料）维度的冗余。
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('storage_location', sa.String(length=128),
                                      nullable=False, default='',
                                      server_default='', comment='存放位置（仓位/货位）'))


def downgrade():
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.drop_column('storage_location')
