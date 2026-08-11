"""add astral_activity_logs

Revision ID: 55ee66ff77aa
Revises: 44dd55ee66ff
Create Date: 2026-08-11 13:16:20.074110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '55ee66ff77aa'
down_revision: Union[str, None] = '44dd55ee66ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对：只新增 astral_activity_logs 表（节点打卡幂等日志，T3-3）。
    # autogenerate 额外探测到的 horoscope_history 类型/FK 漂移与本任务无关，已剔除
    # （与 T4-1/T4-2 迁移同样的核对口径）。
    op.create_table('astral_activity_logs',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('user_id', mysql.CHAR(length=36), nullable=False),
    sa.Column('event_key', sa.String(length=32), nullable=False),
    sa.Column('event_date', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'event_key', 'event_date', name='uq_user_event_date')
    )
    op.create_index(op.f('ix_astral_activity_logs_user_id'), 'astral_activity_logs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_astral_activity_logs_user_id'), table_name='astral_activity_logs')
    op.drop_table('astral_activity_logs')
