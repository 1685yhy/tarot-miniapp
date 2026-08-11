import uuid
from datetime import datetime, timezone
from sqlalchemy import CHAR, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import CHAR as MyCHAR
from app.db.database import Base


class StarMonthlyReview(Base):
    """月度星光复盘缓存：每人每月一份（当月第一次生成后缓存，避免重复 AI 调用）。

    仿 ``MoonReview``（moon_reviews）按人按周期缓存模式；``data`` 保存完整
    复盘 JSON（stats/mood_series/star_color_counts/top_cards/trend_summary/
    insight/next_guide/source），``source`` 标记 ai 或 fallback。
    """

    __tablename__ = "star_monthly_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "month", name="uq_user_month"),
    )

    id: Mapped[str] = mapped_column(MyCHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(MyCHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    month: Mapped[str] = mapped_column(CHAR(7), nullable=False, comment="月份 'YYYY-MM'")
    data: Mapped[str] = mapped_column(Text, nullable=False, comment="复盘 JSON（stats/mood_series/star_color_counts/top_cards/trend_summary/insight/next_guide/source）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
