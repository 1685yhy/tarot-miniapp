"""add star_reports

Revision ID: 88bb99cc00dd
Revises: 77aa88bb99cc
Create Date: 2026-08-11

星象月报缓存表（设计 2.3 SQL 原样）：周/月共用一张表，按人按周期一份
（UNIQUE uq_user_type_period），仿 star_monthly_reviews 缓存模式。

注：autogenerate 会夹带既有模型/库漂移（checkins.milestones_claimed、
horoscope_history 类型等），已手工核对剔除，本迁移只含 star_reports 表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '88bb99cc00dd'
down_revision: Union[str, None] = '77aa88bb99cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 星象报告缓存（周/月共用；report_type=week|month，period_key='2026-W33'|'2026-08'）
    op.create_table(
        'star_reports',
        sa.Column('id', mysql.CHAR(length=36), nullable=False),
        sa.Column('user_id', mysql.CHAR(length=36), nullable=False),
        sa.Column('report_type', sa.String(length=8), nullable=False, comment='week | month'),
        sa.Column('period_key', sa.String(length=12), nullable=False, comment="'2026-W33' | '2026-08'"),
        sa.Column('data', sa.Text(), nullable=False, comment='报告 JSON（统计段 + AI 文案段）'),
        sa.Column('source', sa.String(length=8), nullable=False, comment='ai | fallback'),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'report_type', 'period_key', name='uq_user_type_period'),
    )
    op.create_index(
        op.f('ix_star_reports_user_id'),
        'star_reports',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_star_reports_user_id'), table_name='star_reports')
    op.drop_table('star_reports')
