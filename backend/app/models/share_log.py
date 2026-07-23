import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
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


class Invite(Base):
    """Track user-to-user invites for the viral share system."""

    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    inviter_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invitee_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    reward_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    inviter: Mapped["User"] = relationship(foreign_keys=[inviter_id])  # noqa: F821
    invitee: Mapped["User"] = relationship(foreign_keys=[invitee_id])  # noqa: F821
