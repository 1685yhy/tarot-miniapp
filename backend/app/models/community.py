from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import CHAR
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
    """Post on a daily topic. Posts are displayed anonymously, but the
    author is tracked (user_id) for moderation / account deletion.

    user_id is nullable to keep historical anonymous rows valid; new posts
    always set it.
    """
    __tablename__ = "community_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("community_topics.id"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    topic: Mapped["Topic"] = relationship(back_populates="posts")
    user: Mapped["User | None"] = relationship("User")
