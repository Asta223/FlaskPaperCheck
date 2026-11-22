"""站内聊天增量：会话从最近列表移除标记。

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-22

变更清单：
- add_column: conversation_reads.is_hidden（非空，server_default=0）

设计约定：
- 只隐藏本端最近会话入口，不删除 ChatMessage，也不影响对方会话；
- 新消息到达（未读>0）时列表自动绕过隐藏标记，打开会话后由服务层复位；
- 位点表已有 UNIQUE(user_id, peer_id)，无需新增索引；downgrade 逆序删列。
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation_reads', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'is_hidden', sa.Boolean(), nullable=False,
            server_default=sa.text('0'),
            comment='是否从最近会话移除（消息保留，新消息到达后重现）'))


def downgrade():
    with op.batch_alter_table('conversation_reads', schema=None) as batch_op:
        batch_op.drop_column('is_hidden')
