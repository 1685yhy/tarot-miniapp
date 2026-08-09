"""add xpay order fields and session_key storage

Revision ID: a5f6b7c8d9e0
Revises: f4a5b6c7d8e9
Create Date: 2026-08-09 12:00:00.000000

虚拟支付(xpay)改造:
- orders 表新增 pay_channel(jsapi/xpay)、env(xpay 环境 0正式/1沙箱)、
  delivered_at(xpay 发货回执时间)、refund_status(退款状态)
- users 表新增 session_key_encrypted(xpay 签名用 session_key,AES-GCM 加密存储)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5f6b7c8d9e0'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add xpay order columns and session_key storage to users."""
    op.add_column('orders', sa.Column('pay_channel', sa.String(length=16), nullable=True))
    op.add_column('orders', sa.Column('env', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('delivered_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('refund_status', sa.String(length=16), nullable=True))
    op.add_column('users', sa.Column('session_key_encrypted', sa.String(length=512), nullable=True))


def downgrade() -> None:
    """Drop the xpay columns."""
    op.drop_column('users', 'session_key_encrypted')
    op.drop_column('orders', 'refund_status')
    op.drop_column('orders', 'delivered_at')
    op.drop_column('orders', 'env')
    op.drop_column('orders', 'pay_channel')
