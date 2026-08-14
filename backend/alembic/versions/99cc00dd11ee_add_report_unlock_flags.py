"""add report unlock flags

Revision ID: 99cc00dd11ee
Revises: cc22ff33aa44
Create Date: 2026-08-14 14:00:00.000000

星象月报解锁权益（SDD P2 · T7-3）：
- users 表新增 weekly_report_unlocked（购买 weekly_report 商品 4.9 元置位）
- users 表新增 monthly_report_unlocked（购买 monthly_report 商品 19.9 元置位）

仿 annual_report_paid / birthchart_paid 单次购买 entitlement 模式：
支付回调置位、独立于会员、会员到期后旧解锁仍有效。
手工核对：仅加两列，不动其他表；downgrade 仅删两列。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99cc00dd11ee'
down_revision: Union[str, None] = 'cc22ff33aa44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the weekly/monthly report unlock entitlement columns to users."""
    op.add_column(
        'users',
        sa.Column('weekly_report_unlocked', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('monthly_report_unlocked', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Drop the report unlock entitlement columns."""
    op.drop_column('users', 'monthly_report_unlocked')
    op.drop_column('users', 'weekly_report_unlocked')
