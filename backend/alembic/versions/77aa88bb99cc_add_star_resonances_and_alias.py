"""add star_resonances and alias

Revision ID: 77aa88bb99cc
Revises: 79212bdba9b2
Create Date: 2026-08-11 20:24:14.659869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '77aa88bb99cc'
down_revision: Union[str, None] = '79212bdba9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对（T8-1）：只新增 star_resonances 表（共鸣幂等落库，设计 3.3 SQL
    # 原样，uq_from_to_date 唯一约束）与 users 两列（resonance_visible 默认参与 /
    # star_alias 脱敏星名）。autogenerate 额外探测到的 push_subscriptions 建表、
    # checkins.milestones_claimed、community_posts FK、horoscope_history user_id
    # 类型/FK 漂移均与本任务无关（create_all-only 模型/历史漂移），已剔除
    # （与 55ee66ff77aa / 79212bdba9b2 等迁移同样的核对口径）。
    op.create_table('star_resonances',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('from_user_id', mysql.CHAR(length=36), nullable=False),
    sa.Column('to_user_id', mysql.CHAR(length=36), nullable=False),
    sa.Column('resonate_date', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['to_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('from_user_id', 'to_user_id', 'resonate_date', name='uq_from_to_date')
    )
    op.create_index(op.f('ix_star_resonances_from_user_id'), 'star_resonances', ['from_user_id'], unique=False)
    op.create_index(op.f('ix_star_resonances_to_user_id'), 'star_resonances', ['to_user_id'], unique=False)
    op.add_column('users', sa.Column('resonance_visible', sa.Boolean(), server_default='1', nullable=False))
    op.add_column('users', sa.Column('star_alias', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'star_alias')
    op.drop_column('users', 'resonance_visible')
    op.drop_index(op.f('ix_star_resonances_to_user_id'), table_name='star_resonances')
    op.drop_index(op.f('ix_star_resonances_from_user_id'), table_name='star_resonances')
    op.drop_table('star_resonances')
