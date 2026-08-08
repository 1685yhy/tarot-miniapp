"""星座能量历史表 — 供平滑约束（与昨日差 ≤15）与未来周报使用。"""
import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Integer, Text, Date, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base


class HoroscopeHistory(Base):
    __tablename__ = "horoscope_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    energy: Mapped[dict] = mapped_column(JSON, nullable=False)   # {love, career, social, health}
    factors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    astral: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tip: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_horoscope_user_date"),
    )
