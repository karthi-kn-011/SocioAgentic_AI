"""Initial schema creation

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-05 10:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Posts table
    op.create_table(
        'posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=False),
        sa.Column('tone', sa.String(length=100), server_default='Professional & Engaging', nullable=False),
        sa.Column('raw_content', sa.Text(), nullable=True),
        sa.Column('platform_contents', sa.JSON(), nullable=True),
        sa.Column('target_platforms', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='DRAFT', nullable=False),
        sa.Column('review_score', sa.Integer(), server_default='0', nullable=True),
        sa.Column('review_feedback', sa.Text(), nullable=True),
        sa.Column('review_passed', sa.Boolean(), server_default=sa.text('0'), nullable=True),
        sa.Column('scheduled_time', sa.DateTime(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('thread_id', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_posts_id'), 'posts', ['id'], unique=False)
    op.create_index(op.f('ix_posts_status'), 'posts', ['status'], unique=False)
    op.create_index(op.f('ix_posts_scheduled_time'), 'posts', ['scheduled_time'], unique=False)
    op.create_index(op.f('ix_posts_thread_id'), 'posts', ['thread_id'], unique=False)

    # 2. Approval Requests table
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=50), server_default='web', nullable=True),
        sa.Column('message_ts', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='PENDING', nullable=True),
        sa.Column('reviewer', sa.String(length=100), nullable=True),
        sa.Column('feedback', sa.Text(), nullable=True),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approval_requests_id'), 'approval_requests', ['id'], unique=False)
    op.create_index(op.f('ix_approval_requests_post_id'), 'approval_requests', ['post_id'], unique=False)

    # 3. Social Accounts table
    op.create_table(
        'social_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('account_name', sa.String(length=150), nullable=False),
        sa.Column('account_id', sa.String(length=150), nullable=True),
        sa.Column('encrypted_access_token', sa.Text(), nullable=True),
        sa.Column('encrypted_refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_social_accounts_id'), 'social_accounts', ['id'], unique=False)
    op.create_index(op.f('ix_social_accounts_platform'), 'social_accounts', ['platform'], unique=False)

    # 4. Scheduled Posts table
    op.create_table(
        'scheduled_posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(length=100), nullable=True),
        sa.Column('run_at', sa.DateTime(), nullable=False),
        sa.Column('timezone', sa.String(length=50), server_default='UTC', nullable=True),
        sa.Column('status', sa.String(length=50), server_default='PENDING', nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    op.create_index(op.f('ix_scheduled_posts_id'), 'scheduled_posts', ['id'], unique=False)
    op.create_index(op.f('ix_scheduled_posts_post_id'), 'scheduled_posts', ['post_id'], unique=False)
    op.create_index(op.f('ix_scheduled_posts_run_at'), 'scheduled_posts', ['run_at'], unique=False)

    # 5. Publish Logs table
    op.create_table(
        'publish_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('external_post_id', sa.String(length=255), nullable=True),
        sa.Column('response_payload', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_publish_logs_id'), 'publish_logs', ['id'], unique=False)
    op.create_index(op.f('ix_publish_logs_post_id'), 'publish_logs', ['post_id'], unique=False)
    op.create_index(op.f('ix_publish_logs_platform'), 'publish_logs', ['platform'], unique=False)

    # 6. Analytics Metrics table
    op.create_table(
        'analytics_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),
        sa.Column('metric_value', sa.Integer(), server_default='0', nullable=True),
        sa.Column('data_source', sa.String(length=50), server_default='platform_api', nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analytics_metrics_id'), 'analytics_metrics', ['id'], unique=False)
    op.create_index(op.f('ix_analytics_metrics_post_id'), 'analytics_metrics', ['post_id'], unique=False)

    # 7. Activity Logs table
    op.create_table(
        'activity_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('details', sa.String(length=500), nullable=True),
        sa.Column('actor', sa.String(length=100), server_default='System', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activity_logs_id'), 'activity_logs', ['id'], unique=False)
    op.create_index(op.f('ix_activity_logs_post_id'), 'activity_logs', ['post_id'], unique=False)

    # 8. OAuth States table (Database-backed state persistence)
    op.create_table(
        'oauth_states',
        sa.Column('state', sa.String(length=128), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('code_verifier', sa.Text(), nullable=True),
        sa.Column('redirect_uri', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('state')
    )
    op.create_index(op.f('ix_oauth_states_state'), 'oauth_states', ['state'], unique=True)

def downgrade() -> None:
    op.drop_table('oauth_states')
    op.drop_table('activity_logs')
    op.drop_table('analytics_metrics')
    op.drop_table('publish_logs')
    op.drop_table('scheduled_posts')
    op.drop_table('social_accounts')
    op.drop_table('approval_requests')
    op.drop_table('posts')
