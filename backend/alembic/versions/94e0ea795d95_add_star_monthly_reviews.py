"""add star_monthly_reviews

Revision ID: 94e0ea795d95
Revises: f5a6b7c8d9e0
Create Date: 2026-08-11 09:29:20.773215

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '94e0ea795d95'
down_revision: Union[str, None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 月度星光复盘缓存（仿 moon_reviews：每人每月一份，避免重复 AI 调用）
    op.create_table(
        'star_monthly_reviews',
        sa.Column('id', mysql.CHAR(length=36), nullable=False),
        sa.Column('user_id', mysql.CHAR(length=36), nullable=False),
        sa.Column('month', sa.CHAR(length=7), nullable=False, comment="月份 'YYYY-MM'"),
        sa.Column(
            'data',
            sa.Text(),
            nullable=False,
            comment='复盘 JSON（stats/mood_series/star_color_counts/top_cards/trend_summary/insight/next_guide/source）',
        ),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'month', name='uq_user_month'),
    )
    op.create_index(
        op.f('ix_star_monthly_reviews_user_id'),
        'star_monthly_reviews',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_star_monthly_reviews_user_id'), table_name='star_monthly_reviews'
    )
    op.drop_table('star_monthly_reviews')
