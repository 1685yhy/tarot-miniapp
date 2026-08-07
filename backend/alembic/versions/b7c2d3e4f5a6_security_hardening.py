"""security_hardening

Revision ID: b7c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-08-07

Adds security-hardening columns:
- users.token_version           — JWT invalidation (logout / account deletion)
- users.reinterpret_count_today — daily AI reinterpret quota (non-members)
- users.diary_ai_count_today    — daily diary-AI quota (non-members)
- users.quota_reset_date        — last day the daily AI quotas were reset
- community_posts.user_id       — post author tracking (anonymous display)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c2d3e4f5a6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the security-hardening schema changes."""
    op.add_column(
        'users',
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'users',
        sa.Column('reinterpret_count_today', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'users',
        sa.Column('diary_ai_count_today', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'users',
        sa.Column('quota_reset_date', sa.Date(), nullable=True),
    )
    op.add_column(
        'community_posts',
        sa.Column('user_id', sa.CHAR(length=36), nullable=True),
    )
    op.create_index(
        op.f('ix_community_posts_user_id'),
        'community_posts',
        ['user_id'],
        unique=False,
    )
    # DB-level FK is enforced on MySQL (production); SQLite cannot ALTER-ADD
    # constraints, so skip it there (ORM-level FK still applies).
    if op.get_bind().dialect.name != 'sqlite':
        op.create_foreign_key(
            op.f('fk_community_posts_user_id_users'),
            'community_posts',
            'users',
            ['user_id'],
            ['id'],
        )


def downgrade() -> None:
    """Revert the security-hardening schema changes."""
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_constraint(
            op.f('fk_community_posts_user_id_users'),
            'community_posts',
            type_='foreignkey',
        )
    op.drop_index(op.f('ix_community_posts_user_id'), table_name='community_posts')
    op.drop_column('community_posts', 'user_id')
    op.drop_column('users', 'quota_reset_date')
    op.drop_column('users', 'diary_ai_count_today')
    op.drop_column('users', 'reinterpret_count_today')
    op.drop_column('users', 'token_version')
