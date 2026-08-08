import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base

# 愿望状态枚举（与 app/api/wishes.py 的 WISH_STATUSES 保持一致）
WISH_STATUS_ACTIVE = "active"    # 生长中（月亮保管中）
WISH_STATUS_GROWN = "grown"      # 已生长（满月复盘中标记为已长出痕迹）
WISH_STATUS_ANSWERED = "answered"  # 待回应（月亮收下了，还在它该在的路上）


class Wish(Base):
    __tablename__ = "wishes"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=WISH_STATUS_ACTIVE)
    moon_phase: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="许愿时的月相（new_moon 等）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
