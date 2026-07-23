from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


class Topic(Base):
    """Daily community topic — one per day, optionally inspired by a tarot card."""
    __tablename__ = "community_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Date, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    card_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tarot_cards.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    card: Mapped["TarotCard | None"] = relationship("TarotCard")
    posts: Mapped[list["Post"]] = relationship(
        back_populates="topic", order_by="Post.created_at.desc()"
    )


class Post(Base):
    """Anonymous post on a daily topic — no user identity stored."""
    __tablename__ = "community_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("community_topics.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    topic: Mapped["Topic"] = relationship(back_populates="posts")
