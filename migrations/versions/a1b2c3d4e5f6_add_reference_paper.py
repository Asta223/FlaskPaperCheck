"""add reference_paper

Revision ID: a1b2c3d4e5f6
Revises: 799e2ab02d72
Create Date: 2026-08-27

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '799e2ab02d72'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reference_papers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('content_text', sa.Text(), nullable=True),
        sa.Column('file_path', sa.String(length=400), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reference_papers_content_hash',
                    'reference_papers', ['content_hash'], unique=False)


def downgrade():
    op.drop_index('ix_reference_papers_content_hash', table_name='reference_papers')
    op.drop_table('reference_papers')
