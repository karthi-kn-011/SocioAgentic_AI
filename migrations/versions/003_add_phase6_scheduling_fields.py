"""Add Phase 6 scheduling and publisher fields

Revision ID: 003_add_phase6_scheduling_fields
Revises: 002_add_phase5_workflow_fields
Create Date: 2026-10-06 14:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003_add_phase6_scheduling_fields'
down_revision: Union[str, None] = '002_add_phase5_workflow_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table('scheduled_posts') as batch_op:
        batch_op.add_column(sa.Column('platform', sa.String(length=50), server_default='TWITTER', nullable=False))
        batch_op.add_column(sa.Column('scheduled_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('published_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('cancelled_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=128), nullable=True))
        batch_op.create_index('ix_scheduled_posts_idempotency_key', ['idempotency_key'], unique=True)
        batch_op.create_index('ix_scheduled_posts_scheduled_at', ['scheduled_at'])

    with op.batch_alter_table('publish_logs') as batch_op:
        batch_op.add_column(sa.Column('schedule_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('provider', sa.String(length=100), server_default='MockPublisher', nullable=True))
        batch_op.add_column(sa.Column('is_mock', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('attempted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_publish_logs_schedule_id', ['schedule_id'])

    # Data migration: copy run_at to scheduled_at where scheduled_at is null
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE scheduled_posts SET scheduled_at = run_at WHERE scheduled_at IS NULL AND run_at IS NOT NULL"))

def downgrade() -> None:
    with op.batch_alter_table('publish_logs') as batch_op:
        batch_op.drop_index('ix_publish_logs_schedule_id')
        batch_op.drop_column('completed_at')
        batch_op.drop_column('attempted_at')
        batch_op.drop_column('idempotency_key')
        batch_op.drop_column('retry_count')
        batch_op.drop_column('is_mock')
        batch_op.drop_column('provider')
        batch_op.drop_column('schedule_id')

    with op.batch_alter_table('scheduled_posts') as batch_op:
        batch_op.drop_index('ix_scheduled_posts_scheduled_at')
        batch_op.drop_index('ix_scheduled_posts_idempotency_key')
        batch_op.drop_column('idempotency_key')
        batch_op.drop_column('cancelled_at')
        batch_op.drop_column('published_at')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('scheduled_at')
        batch_op.drop_column('platform')
