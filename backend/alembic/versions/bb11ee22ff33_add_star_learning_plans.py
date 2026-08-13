"""add star_learning_plans

Revision ID: bb11ee22ff33
Revises: aa00dd11ee22
Create Date: 2026-08-13

星灵学堂（SDD P2 阶段3 · T6-2）：star_learning_plans 学习计划表（设计 1.3 SQL 原样）。

1 用户 1 条（user_id 主键，无独立 id；cards_per_day=0 视为未开启）：
- cards_per_day：每日学牌目标（0=关闭 | 1|3|5，默认 0）
- reminder_on：学习提醒开关（默认关闭）
- path：当前学习路径（major|minor|random|related，默认 major）
- cursor_pos：路径游标（major 0-21 / minor 0-55；random|related 按日派生忽略游标）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'bb11ee22ff33'
down_revision: Union[str, None] = 'aa00dd11ee22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'star_learning_plans',
        sa.Column('user_id', mysql.CHAR(length=36), nullable=False),
        sa.Column('cards_per_day', sa.Integer(), nullable=False, server_default='0', comment='0=关闭 | 1|3|5'),
        sa.Column('reminder_on', sa.Boolean(), nullable=False, server_default='0', comment='学习提醒开关（默认关）'),
        sa.Column('path', sa.String(length=16), nullable=False, server_default='major', comment='major|minor|random|related'),
        sa.Column('cursor_pos', sa.Integer(), nullable=False, server_default='0', comment='路径游标（major 0-21 / minor 0-55）'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('star_learning_plans')
