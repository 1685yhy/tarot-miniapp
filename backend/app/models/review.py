import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Date, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base


class MoonReview(Base):
    """满月复盘缓存：每人每天一份（当天第一次生成后缓存，避免重复 AI 调用）。"""

    __tablename__ = "moon_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "review_date", name="uq_user_review_date"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    review_date: Mapped[date] = mapped_column(Date, nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False, comment="复盘 JSON（wishes/review/tips）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
