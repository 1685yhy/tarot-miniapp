"""add birthchart fields

Revision ID: f4a5b6c7d8e9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-09 10:00:00.000000

本命星盘三要素 + 深度报告付费（开发 05）：
- users 表新增 birthchart_paid（购买 birthchart_report 商品置位，独立于会员）
- users 表新增 birthchart_json（三要素 AI 文案缓存，含指纹）
- users 表新增 birthchart_report（深度报告缓存）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add birthchart paid-flag and JSON caches to users."""
    op.add_column('users', sa.Column('birthchart_paid', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('birthchart_json', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('birthchart_report', sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the birthchart columns."""
    op.drop_column('users', 'birthchart_report')
    op.drop_column('users', 'birthchart_json')
    op.drop_column('users', 'birthchart_paid')
