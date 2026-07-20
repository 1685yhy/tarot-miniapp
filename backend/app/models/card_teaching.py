from sqlalchemy import Integer, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class CardTeaching(Base):
    """卡牌教学数据：牌面符号解读、历史典故、实用关键词"""

    __tablename__ = "card_teaching"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tarot_cards.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # JSON array: [{"symbol": "白玫瑰", "meaning": "纯洁与超越世俗的爱"}, ...]
    symbols: Mapped[str] = mapped_column(Text, nullable=False)
    # Historical/mythological background text
    story: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON array: ["探索", "可能性", "勇气"]
    keywords_learning: Mapped[str] = mapped_column(Text, nullable=False)
    # One sentence connecting this card to daily life
    life_connection: Mapped[str] = mapped_column(Text, nullable=False)
    # Element association description
    element_association: Mapped[str] = mapped_column(Text, nullable=False)
