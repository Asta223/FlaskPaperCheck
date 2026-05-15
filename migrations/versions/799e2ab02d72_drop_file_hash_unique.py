"""drop_file_hash_unique

Revision ID: 799e2ab02d72
Revises: 0068aba96b3c
Create Date: 2026-05-15 22:42:33.600176

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '799e2ab02d72'
down_revision = '0068aba96b3c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('papers', schema=None) as batch_op:
        # 删除旧索引（如果存在）
        batch_op.drop_index('ix_papers_file_hash')
        # 重新创建不加唯一约束的索引（可选）
        batch_op.create_index('ix_papers_file_hash', ['file_hash'])


def downgrade():
    with op.batch_alter_table('papers', schema=None) as batch_op:
        # 在回滚时，先删除新索引，再恢复旧的唯一索引
        batch_op.drop_index('ix_papers_file_hash')
        batch_op.create_index('ix_papers_file_hash', ['file_hash'], unique=True)
