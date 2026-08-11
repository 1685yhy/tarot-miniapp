"""StarWordDaily model — 睡前星语同日缓存（T4-2）。"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CHAR, Date, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import CHAR as MyCHAR

from app.db.database import Base


class StarWordDaily(Base):
    """睡前星语同日缓存：每人每天一份（第一次生成后缓存，避免重复 AI 调用）。

    仿 ``StarMonthlyReview`` 按人按周期缓存模式：
    - ``data`` 保存完整星语 JSON（{"phrase": "..."}）
    - ``source`` 标记生成来源（ai 或 fallback）
    唯一约束 uq_user_word_date(user_id, word_date)：同日同人仅一条。
    """

    __tablename__ = "star_word_daily"
    __table_args__ = (
        UniqueConstraint("user_id", "word_date", name="uq_user_word_date"),
    )

    id: Mapped[str] = mapped_column(MyCHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(MyCHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    word_date: Mapped[date] = mapped_column(Date, nullable=False, comment="星语日期")
    data: Mapped[str] = mapped_column(Text, nullable=False, comment="星语 JSON（phrase）")
    source: Mapped[str] = mapped_column(CHAR(8), nullable=False, comment="生成来源 ai|fallback")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
