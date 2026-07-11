import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base


class ShareLog(Base):
    """Record of a user sharing content from the app (viral tracking)."""

    __tablename__ = "share_logs"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sharer_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    channel: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="wechat_friend / wechat_moments / qq / link / image / other")
    share_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="reading / card / diary / mini_program")
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="optional reference — reading_id / card_id etc.")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
