import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, Text, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    openid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    unionid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_member: Mapped[bool] = mapped_column(Boolean, default=False)
    member_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    free_readings_today: Mapped[int] = mapped_column(Integer, default=0)
    free_chats_today: Mapped[int] = mapped_column(Integer, default=0)
    paid_readings_balance: Mapped[int] = mapped_column(Integer, default=0)
    # P0-1: standalone annual-report purchase (annual_report product) unlocks
    # GET /report/annual for non-members (independent of membership)
    annual_report_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    last_reading_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    annual_report_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    annual_report_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Viral share / invite fields
    invite_code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True, index=True)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    free_deep_readings: Mapped[int] = mapped_column(Integer, default=0)
    reward_tier: Mapped[int] = mapped_column(Integer, default=0)
    # ── 星座能量（星光映照）──
    # zodiac: 12 星座 key（aries/taurus/...）；birth_* 二期星盘计算用，先存
    zodiac: Mapped[str | None] = mapped_column(String(16), nullable=True)
    birth_date: Mapped[str | None] = mapped_column(String(16), nullable=True)  # YYYY-MM-DD
    birth_time: Mapped[str | None] = mapped_column(String(16), nullable=True)  # HH:MM 或 HH:MM:SS
    birth_city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Auth: bumped on logout/account-deletion to invalidate previously issued JWTs
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    # Daily AI-extras quota (reinterpret / diary AI), reset when the day changes
    reinterpret_count_today: Mapped[int] = mapped_column(Integer, default=0)
    diary_ai_count_today: Mapped[int] = mapped_column(Integer, default=0)
    quota_reset_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    readings: Mapped[list["Reading"]] = relationship(back_populates="user")
    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    diary_entries: Mapped[list["DiaryEntry"]] = relationship(back_populates="user")
    checkins: Mapped[list["CheckIn"]] = relationship(back_populates="user")  # noqa: F821
