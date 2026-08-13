"""add academy_chat_count

Revision ID: cc22ff33aa44
Revises: bb11ee22ff33
Create Date: 2026-08-13

星灵学堂（SDD P2 阶段3 · T6-4）：users.academy_chat_count_today 陪学小星
AI 对话每日计数列。

独立计数字段——与 free_chats_today（占卜追问）分离，互不挤占；日复位
复用 quota_reset_date 日复位管线（app/utils/quota.py 的
reset_ai_quota_if_new_day），本迁移只加一列。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cc22ff33aa44'
down_revision: Union[str, None] = 'bb11ee22ff33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对：只新增 users.academy_chat_count_today 一列（独立于 free_chats_today）。
    op.add_column(
        'users',
        sa.Column(
            'academy_chat_count_today',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='陪学小星对话每日计数（非会员，独立于占卜追问）',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'academy_chat_count_today')
