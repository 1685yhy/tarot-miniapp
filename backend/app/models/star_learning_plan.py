"""星灵学堂学习计划表（SDD P2 阶段3 · T6-2，设计 1.3 SQL 原样）。

1 用户 1 条（user_id 主键，无独立 id；cards_per_day=0 视为未开启）。
- cards_per_day：每日学牌目标（0=关闭 | 1|3|5）
- reminder_on：学习提醒开关（默认关闭；开启需已有订阅额度，引导授权不硬拦）
- path：当前学习路径（major 愚者之旅 / minor 四元素庭院 / random 今日之牌 /
  related 与你相遇的牌）
- cursor_pos：路径游标（major 0-21 / minor 0-55；random|related 按日派生，忽略游标）
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class StarLearningPlan(Base):
    __tablename__ = "star_learning_plans"

    user_id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    cards_per_day: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 0=关闭 | 1|3|5
    reminder_on: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # 学习提醒（默认关）
    path: Mapped[str] = mapped_column(String(16), default="major", server_default="major")  # major|minor|random|related
    cursor_pos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # major 0-21 / minor 0-55
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
