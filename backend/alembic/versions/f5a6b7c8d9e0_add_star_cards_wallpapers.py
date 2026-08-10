"""add star_cards and wallpapers

Revision ID: f5a6b7c8d9e0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-11 11:30:00.000000

P0-3 星尘签到收集体系（设计缺口 1）：users 表新增两列收藏品字段。

- star_cards: 稀有星卡集合（7 日连续签到发放，78 张牌按 user_id 确定性选取）。
  存储 JSON 数组字符串：[{"card_id": 12, "date": "2026-08-11",
  "tier": "gold", "orientation": "upright"}, ...]（正位金卡）
- wallpapers: 星光壁纸达成日期集合（30 日连续签到发放）。
  存储 JSON 数组字符串：["2026-08-11", ...]

均为收藏品，不消耗任何额度；读写统一走 app.services.star_collectibles
（脏数据解析安全回退空列表）。Text + nullable 与 annual_report_data 先例一致。
手工核对：仅加两列，不动其他表；downgrade 仅删两列。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 手工核对：users 表新增 star_cards / wallpapers 两列（Text, 可空），幂等单次执行。
    op.add_column('users', sa.Column('star_cards', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('wallpapers', sa.Text(), nullable=True))


def downgrade() -> None:
    # 手工核对：仅删除本迁移新增的两列，保留其余字段。
    op.drop_column('users', 'wallpapers')
    op.drop_column('users', 'star_cards')
