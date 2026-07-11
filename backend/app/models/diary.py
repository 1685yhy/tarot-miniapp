import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Integer, Text, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base


class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    mood: Mapped[str | None] = mapped_column(String(16), nullable=True)
    card_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tarot_cards.id"), nullable=True)
    reflection: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="diary_entries")
    card: Mapped["TarotCard"] = relationship()
