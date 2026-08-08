"""add_performance_events

Revision ID: e1f2a3b4c5d6
Revises: c9d3e4f5a6b7
Create Date: 2026-08-08 12:00:00.000000

埋点落库表：前端性能指标 + JS 错误共用（metric='js_error' 为错误行）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'c9d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'performance_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('page', sa.String(length=255), nullable=True),
        sa.Column('metric', sa.String(length=64), nullable=False),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_performance_events_created_at'),
        'performance_events',
        ['created_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_performance_events_metric'),
        'performance_events',
        ['metric'],
        unique=False,
    )
    op.create_index(
        op.f('ix_performance_events_user_id'),
        'performance_events',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_performance_events_user_id'), table_name='performance_events')
    op.drop_index(op.f('ix_performance_events_metric'), table_name='performance_events')
    op.drop_index(op.f('ix_performance_events_created_at'), table_name='performance_events')
    op.drop_table('performance_events')
