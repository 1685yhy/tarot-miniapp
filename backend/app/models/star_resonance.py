"""星友圈共鸣记录（SDD P2 · T8-1）：零 UGC 共鸣墙的「谁共鸣了谁」幂等落库。

设计 3.3 SQL 原样：``UNIQUE(from_user_id, to_user_id, resonate_date)``
（``uq_from_to_date``）——同一天同一对用户只记一次共鸣（幂等防重，
与 astral_activity_logs 的 uq_user_event_date 同款唯一约束模式）。

共鸣 = 今日已活跃（同星座 / 同星光数 / 同牌分组内）用户之间的星辉触碰；
不产星尘、零 UGC 内容。隐身开关 resonance_visible 在 users 表
（默认参与展示，可一键隐身——见 Task 2 共鸣墙聚合）。
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class StarResonance(Base):
    __tablename__ = "star_resonances"
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", "resonate_date", name="uq_from_to_date"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    from_user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    to_user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    resonate_date: Mapped[date] = mapped_column(Date, nullable=False)  # 共鸣当天 YYYY-MM-DD
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
