"""add_depth_and_reflection_question

Revision ID: 8eea6b0e6bef
Revises: d527f8eddb43
Create Date: 2026-07-30 16:13:49.869517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '8eea6b0e6bef'
down_revision: Union[str, None] = 'd527f8eddb43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add depth and reflection_question columns to readings table."""
    op.add_column('readings', sa.Column('depth', sa.String(length=16), nullable=True))
    op.add_column('readings', sa.Column('reflection_question', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove depth and reflection_question columns from readings table."""
    op.drop_column('readings', 'reflection_question')
    op.drop_column('readings', 'depth')
