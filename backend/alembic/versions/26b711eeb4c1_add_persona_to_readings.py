"""add persona column to readings

Revision ID: 26b711eeb4c1
Revises: 075703a2057d
Create Date: 2026-07-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26b711eeb4c1'
down_revision: Union[str, None] = '075703a2057d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'readings',
        sa.Column('persona', sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('readings', 'persona')