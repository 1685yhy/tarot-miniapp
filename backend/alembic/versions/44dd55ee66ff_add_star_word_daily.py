"""add star_word_daily

Revision ID: 44dd55ee66ff
Revises: 33cc44dd55ee
Create Date: 2026-08-11 11:17:01.506188

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '44dd55ee66ff'
down_revision: Union[str, None] = '33cc44dd55ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对：只新增 star_word_daily 表（睡前星语同日缓存，T4-2）。
    # autogenerate 额外探测到的 horoscope_history 类型/FK 漂移与本任务无关，已剔除
    # （与 T4-1 迁移 33cc44dd55ee 同样的核对口径）。
    op.create_table('star_word_daily',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('user_id', mysql.CHAR(length=36), nullable=False),
    sa.Column('word_date', sa.Date(), nullable=False, comment='星语日期'),
    sa.Column('data', sa.Text(), nullable=False, comment='星语 JSON（phrase）'),
    sa.Column('source', sa.CHAR(length=8), nullable=False, comment='生成来源 ai|fallback'),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'word_date', name='uq_user_word_date')
    )
    op.create_index(op.f('ix_star_word_daily_user_id'), 'star_word_daily', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_star_word_daily_user_id'), table_name='star_word_daily')
    op.drop_table('star_word_daily')
