"""add subscribe quota

Revision ID: c2d3e4f5a6b7c8d9
Revises: 96dab641fe3d
Create Date: 2026-08-10 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7c8d9'
down_revision: Union[str, None] = '96dab641fe3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对：只新增 subscribe_quotas 一张表（星光晨讯订阅额度，Task 5）。
    op.create_table(
        'subscribe_quotas',
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('quota_available', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_sent_date', sa.Date(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('subscribe_quotas')
