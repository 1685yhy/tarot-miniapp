"""节点活动打卡日志（SDD P1 · T3-3）。

用户在节点活动日（新月许愿 / 满月复盘 / 水逆指南）打卡，每次事件 +1 星尘。
幂等：UNIQUE(user_id, event_key, event_date)（uq_user_event_date），
与签到表 checkins 的 uq_user_checkin_date 同款唯一约束模式。

event_key 落库为「事件类型-日期」，如 new_moon-2026-08-12（同一事件一次机会，
水逆区间事件每天都是独立事件日，可每天打卡）。
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AstralActivityLog(Base):
    __tablename__ = "astral_activity_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "event_key", "event_date", name="uq_user_event_date"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(32), nullable=False)  # 如 new_moon-2026-08-12
    event_date: Mapped[date] = mapped_column(Date, nullable=False)  # 打卡当天 YYYY-MM-DD
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
