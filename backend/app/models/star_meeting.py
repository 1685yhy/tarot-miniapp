"""
星辰相遇：相遇记录表（星光映照 · P1 T2-2）。

一次合盘一条记录（快速版 /meet/quick 也落库，便于「我的相遇」回顾与分享）。
字段严格按设计 2.4 SQL：id/initiator_id/friend_user_id/relation/
a_zodiac/a_moon/a_rising/b_zodiac/b_moon/b_rising/status/result_json/created_at/updated_at。

PII 最小化：只存派生星座 key（a_*/b_*），不存出生日期/时间明文；
完整结果（score/levels/factors/cards/tips）缓存于 result_json。
friend_user_id 由邀请版（T2-3 /meet/join）好友注册后回填，用于裂变追踪。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class StarMeeting(Base):
    __tablename__ = "star_meetings"

    id: Mapped[str] = mapped_column(
        CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    initiator_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), index=True, nullable=False
    )
    # 好友注册后回填（裂变追踪，T2-3 /meet/join）；未参与时为 NULL
    friend_user_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    relation: Mapped[str] = mapped_column(String(16), nullable=False)  # friend|love|family|work
    # ── 双方派生星座 key（PII 最小化：不存出生日期明文）──
    a_zodiac: Mapped[str] = mapped_column(String(16), nullable=False)
    a_moon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    a_rising: Mapped[str | None] = mapped_column(String(16), nullable=True)
    b_zodiac: Mapped[str] = mapped_column(String(16), nullable=False)
    b_moon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    b_rising: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="completed", server_default="completed"
    )  # pending（邀请版）| completed
    # 结果缓存（score/levels/factors/cards/tips），详情/海报直接读
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
