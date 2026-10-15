"""Add Phase 5 workflow fields for HITL orchestration and persistence

Revision ID: 002_add_phase5_workflow_fields
Revises: 001_initial_schema
Create Date: 2026-10-05 18:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_add_phase5_workflow_fields'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table('posts') as batch_op:
        batch_op.add_column(sa.Column('theme', sa.String(length=100), server_default='Thought Leadership', nullable=True))
        batch_op.add_column(sa.Column('regeneration_count', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('generation_version', sa.Integer(), server_default='1', nullable=False))

    with op.batch_alter_table('approval_requests') as batch_op:
        batch_op.add_column(sa.Column('rejection_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('review_notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('requested_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('reviewed_at', sa.DateTime(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table('approval_requests') as batch_op:
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('requested_at')
        batch_op.drop_column('review_notes')
        batch_op.drop_column('rejection_reason')

    with op.batch_alter_table('posts') as batch_op:
        batch_op.drop_column('generation_version')
        batch_op.drop_column('regeneration_count')
        batch_op.drop_column('theme')
