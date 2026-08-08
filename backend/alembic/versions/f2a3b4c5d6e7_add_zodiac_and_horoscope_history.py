"""add zodiac columns and horoscope_history

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-08 15:00:00.000000

星座能量引擎（星光映照）：
- users 表新增 zodiac / birth_date / birth_time / birth_city（birth 二期星盘计算用，先存）
- 新表 horoscope_history：能量历史（user_id+date 唯一），供平滑约束与未来周报
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add zodiac/birth columns and the horoscope_history table."""
    op.add_column('users', sa.Column('zodiac', sa.String(length=16), nullable=True))
    op.add_column('users', sa.Column('birth_date', sa.String(length=16), nullable=True))
    op.add_column('users', sa.Column('birth_time', sa.String(length=16), nullable=True))
    op.add_column('users', sa.Column('birth_city', sa.String(length=64), nullable=True))

    op.create_table(
        'horoscope_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('energy', sa.JSON(), nullable=False),
        sa.Column('factors', sa.JSON(), nullable=True),
        sa.Column('astral', sa.JSON(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('tip', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='uq_horoscope_user_date'),
    )
    op.create_index(
        op.f('ix_horoscope_history_user_id'),
        'horoscope_history',
        ['user_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_horoscope_history_date'),
        'horoscope_history',
        ['date'],
        unique=False,
    )


def downgrade() -> None:
    """Drop the zodiac columns and the horoscope_history table."""
    op.drop_index(op.f('ix_horoscope_history_date'), table_name='horoscope_history')
    op.drop_index(op.f('ix_horoscope_history_user_id'), table_name='horoscope_history')
    op.drop_table('horoscope_history')
    op.drop_column('users', 'birth_city')
    op.drop_column('users', 'birth_time')
    op.drop_column('users', 'birth_date')
    op.drop_column('users', 'zodiac')
