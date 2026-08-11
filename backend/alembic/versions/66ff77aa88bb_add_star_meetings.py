"""add star_meetings

Revision ID: 66ff77aa88bb
Revises: 55ee66ff77aa
Create Date: 2026-08-11 16:34:03.283559

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '66ff77aa88bb'
down_revision: Union[str, None] = '55ee66ff77aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对：只新增 star_meetings 表（相遇记录，SDD P1 T2-2）。
    # autogenerate 额外探测到的 horoscope_history user_id 类型/FK 漂移与本任务无关，
    # 已剔除（与 T3-3/T4-1/T4-2 迁移同样的核对口径）。
    op.create_table('star_meetings',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('initiator_id', mysql.CHAR(length=36), nullable=False),
    sa.Column('friend_user_id', mysql.CHAR(length=36), nullable=True),
    sa.Column('relation', sa.String(length=16), nullable=False),
    sa.Column('a_zodiac', sa.String(length=16), nullable=False),
    sa.Column('a_moon', sa.String(length=16), nullable=True),
    sa.Column('a_rising', sa.String(length=16), nullable=True),
    sa.Column('b_zodiac', sa.String(length=16), nullable=False),
    sa.Column('b_moon', sa.String(length=16), nullable=True),
    sa.Column('b_rising', sa.String(length=16), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='completed', nullable=False),
    sa.Column('result_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['initiator_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_star_meetings_initiator_id'), 'star_meetings', ['initiator_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_star_meetings_initiator_id'), table_name='star_meetings')
    op.drop_table('star_meetings')
