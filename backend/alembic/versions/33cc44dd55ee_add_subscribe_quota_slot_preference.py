"""add subscribe_quota slot_preference

Revision ID: 33cc44dd55ee
Revises: 22bb33cc44dd
Create Date: 2026-08-11 11:05:02.650793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '33cc44dd55ee'
down_revision: Union[str, None] = '22bb33cc44dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对：只新增 subscribe_quotas.slot_preference 一列（默认 morning，
    # 存量行为不变——现有行自动视为晨讯槽位）。autogenerate 额外探测到的
    # horoscope_history 类型/FK 漂移与本任务无关，已剔除。
    op.add_column(
        'subscribe_quotas',
        sa.Column(
            'slot_preference',
            sa.String(length=16),
            server_default='morning',
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('subscribe_quotas', 'slot_preference')
