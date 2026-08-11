import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import CHAR as MyCHAR
from app.db.database import Base


class StarReport(Base):
    """星象报告缓存（设计 2.3 SQL 原样）：周/月共用一张表。

    仿 ``StarMonthlyReview`` 按人按周期缓存模式：每人每周/每月各一份；
    ``data`` 保存完整报告 JSON（统计段 + AI 文案段），``source`` 标记
    ai 或 fallback；``report_type`` = week | month，``period_key`` 形如
    '2026-W33' / '2026-08'（UNIQUE uq_user_type_period）。
    """

    __tablename__ = "star_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "report_type", "period_key", name="uq_user_type_period"),
    )

    id: Mapped[str] = mapped_column(MyCHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(MyCHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(8), nullable=False, comment="week | month")
    period_key: Mapped[str] = mapped_column(String(12), nullable=False, comment="'2026-W33' | '2026-08'")
    data: Mapped[str] = mapped_column(Text, nullable=False, comment="报告 JSON（统计段 + AI 文案段）")
    source: Mapped[str] = mapped_column(String(8), nullable=False, comment="ai | fallback")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
