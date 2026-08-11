"""add friend_user_id index to star_meetings

Revision ID: 79212bdba9b2
Revises: 66ff77aa88bb
Create Date: 2026-08-11 16:45:04.274290

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '79212bdba9b2'
down_revision: Union[str, None] = '66ff77aa88bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对：只新增 ix_star_meetings_friend_user_id 索引（T2-2 审查 Minor 3）。
    # autogenerate 额外探测到的 horoscope_history user_id 类型/FK 漂移与本任务无关，
    # 已剔除（与 66ff77aa88bb 等迁移同样的核对口径）。
    op.create_index(op.f('ix_star_meetings_friend_user_id'), 'star_meetings', ['friend_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_star_meetings_friend_user_id'), table_name='star_meetings')
