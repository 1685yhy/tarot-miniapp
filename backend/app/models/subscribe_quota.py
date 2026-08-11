"""
SubscribeQuota model — 星光晨讯订阅额度（Task 5）。

微信订阅消息为一次性订阅：用户每授权 1 次 = 1 条额度。
- user_id：用户主键（与 users.id 对应，无外键约束保持轻量）
- quota_available：剩余可发送条数（grant +1；晨讯发送成功后 -1）
- last_sent_date：该用户最近一次收到晨讯的日期（同日最多 1 条）
- slot_preference：推送槽位偏好（"morning" 晨讯 / "night" 星语，默认 morning）
- updated_at：最近更新时间
"""

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SubscribeQuota(Base):
    __tablename__ = "subscribe_quotas"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    quota_available: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    last_sent_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 推送槽位偏好：morning=星光晨讯 / night=晚间星语（默认 morning）
    slot_preference: Mapped[str] = mapped_column(
        String(16), default="morning", server_default="morning", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
