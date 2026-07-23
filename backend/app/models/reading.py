import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, Text, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base


class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    spread_type: Mapped[str] = mapped_column(String(32), nullable=False)  # daily/triangle/celtic_cross/etc
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme: Mapped[str | None] = mapped_column(String(16), nullable=True)  # love/career/finance/general
    interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    persona: Mapped[str | None] = mapped_column(String(32), nullable=True)  # gentle_star / wise_moon / frank_sun
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="readings")
    drawn_cards: Mapped[list["DrawnCard"]] = relationship(back_populates="reading", cascade="all, delete-orphan")
    chat_messages: Mapped[list["ChatMessage"]] = relationship(back_populates="reading", cascade="all, delete-orphan")


class DrawnCard(Base):
    __tablename__ = "drawn_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("readings.id"), nullable=False)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey("tarot_cards.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 牌阵中的位置
    position_name: Mapped[str] = mapped_column(String(32), nullable=False)
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False)

    reading: Mapped["Reading"] = relationship(back_populates="drawn_cards")
    card: Mapped["TarotCard"] = relationship()


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("readings.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    reading: Mapped["Reading"] = relationship(back_populates="chat_messages")
