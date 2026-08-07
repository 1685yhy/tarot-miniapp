"""add annual_report_paid

Revision ID: c9d3e4f5a6b7
Revises: b7c2d3e4f5a6
Create Date: 2026-08-07

Adds users.annual_report_paid — standalone "年度运势报告" (annual_report
product) purchase entitlement, so a non-member who bought the ¥29.90
report is allowed to access GET /report/annual (P0-1 fix).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d3e4f5a6b7'
down_revision: Union[str, None] = 'b7c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the annual-report purchase entitlement column."""
    op.add_column(
        'users',
        sa.Column(
            'annual_report_paid',
            sa.Boolean(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    """Drop the annual-report purchase entitlement column."""
    op.drop_column('users', 'annual_report_paid')
