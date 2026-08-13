"""星灵学堂学习进度表（SDD P2 阶段3 · T6-1，设计 1.3 SQL 原样）。

每行 = 用户已学的一张卡牌（学一张牌 = 点亮一颗星）。
幂等：UNIQUE(user_id, card_id)（uq_user_card），与 astral_activity_logs 的
uq_user_event_date 同款唯一约束模式 —— 重复 POST /academy/learned 不会产生
第二行，已学即返回 learned=false 不重复奖励（+ academy_milestones 账本双保险）。
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class StarLearningProgress(Base):
    __tablename__ = "star_learning_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_user_card"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey("tarot_cards.id"), nullable=False)
    learned_at: Mapped[date] = mapped_column(Date, nullable=False)  # 学习当天 YYYY-MM-DD
    review_count: Mapped[int] = mapped_column(Integer, default=0)  # 复习次数（仅计数不设奖励，防刷）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
