"""add_image_url_to_diary

Revision ID: a1b2c3d4e5f6
Revises: 8eea6b0e6bef
Create Date: 2026-07-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '8eea6b0e6bef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'diary_entries',
        sa.Column('image_url', sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('diary_entries', 'image_url')
