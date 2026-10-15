"""Add target_platforms to scheduled_posts

Revision ID: 004_add_scheduled_post_target_platforms
Revises: 003_add_phase6_scheduling_fields
Create Date: 2026-10-07 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '004_add_scheduled_post_target_platforms'
down_revision: Union[str, None] = '003_add_phase6_scheduling_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table('scheduled_posts') as batch_op:
        batch_op.add_column(sa.Column('target_platforms', sa.JSON(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table('scheduled_posts') as batch_op:
        batch_op.drop_column('target_platforms')
