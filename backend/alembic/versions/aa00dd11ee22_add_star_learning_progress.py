"""add star_learning_progress

Revision ID: aa00dd11ee22
Revises: 88bb99cc00dd
Create Date: 2026-08-13

星灵学堂（SDD P2 阶段3 · T6-1）：star_learning_progress 学习进度表 +
users.academy_milestones 里程碑账本列。

幂等：uq_user_card（user_id, card_id）唯一约束（同 astral_activity_logs 模式）；
账本列记录已领里程碑 key（JSON 数组字符串，仿 journal_streak_reward_week 语义）。

注：本迁移只含上述新表 + 一列（手工核对，autogenerate 夹带的既有库漂移剔除）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'aa00dd11ee22'
down_revision: Union[str, None] = '88bb99cc00dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对：只新增 star_learning_progress 表 + users.academy_milestones 一列。
    op.create_table(
        'star_learning_progress',
        sa.Column('id', mysql.CHAR(length=36), nullable=False),
        sa.Column('user_id', mysql.CHAR(length=36), nullable=False),
        sa.Column('card_id', sa.Integer(), nullable=False),
        sa.Column('learned_at', sa.Date(), nullable=False, comment='学习当天 YYYY-MM-DD'),
        sa.Column('review_count', sa.Integer(), nullable=False, comment='复习次数（仅计数不设奖励，防刷）'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['card_id'], ['tarot_cards.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'card_id', name='uq_user_card'),
    )
    op.create_index(
        op.f('ix_star_learning_progress_user_id'),
        'star_learning_progress',
        ['user_id'],
        unique=False,
    )
    # 已领里程碑账本（JSON 数组字符串，幂等锚，仿 journal_streak_reward_week 语义）
    op.add_column('users', sa.Column('academy_milestones', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'academy_milestones')
    op.drop_index(op.f('ix_star_learning_progress_user_id'), table_name='star_learning_progress')
    op.drop_table('star_learning_progress')
