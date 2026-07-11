from sqlalchemy import String, Text, Boolean, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class TarotCard(Base):
    __tablename__ = "tarot_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_zh: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name_en: Mapped[str] = mapped_column(String(64), nullable=False)
    card_number: Mapped[int] = mapped_column(Integer, nullable=False)
    arcana: Mapped[str] = mapped_column(String(16), nullable=False)  # 'major' or 'minor'
    suit: Mapped[str | None] = mapped_column(String(16), nullable=True)  # wands/cups/swords/pentacles
    element: Mapped[str | None] = mapped_column(String(8), nullable=True)
    image_description: Mapped[str] = mapped_column(Text, nullable=False)
    keywords_upright: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array string
    keywords_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    meaning_upright: Mapped[str] = mapped_column(Text, nullable=False)
    meaning_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    love_upright: Mapped[str] = mapped_column(Text, nullable=False)
    love_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    career_upright: Mapped[str] = mapped_column(Text, nullable=False)
    career_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    finance_upright: Mapped[str] = mapped_column(Text, nullable=False)
    finance_reversed: Mapped[str] = mapped_column(Text, nullable=False)
    health_upright: Mapped[str] = mapped_column(Text, nullable=False)
    health_reversed: Mapped[str] = mapped_column(Text, nullable=False)
