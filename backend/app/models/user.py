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
    # xpay 前端签名用的 session_key（AES-GCM 加密落库，回归修复：按 alembic a5f6b7c8d9e0 恢复）
    session_key_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
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
    # ── 星尘 / 星阶（星光映照 P0：签到收集星尘，名片展示星阶）──
    # stardust_total：累计星尘（只增不减，签到/任务奖励写入）
    # star_tier：星阶索引，由 stardust_total 经 app.services.stardust.tier_for 推导；
    #   NULL 表示未推导（card-info 等读取处用 tier_for(stardust_total) 兜底，
    #   见 app/api/share.py；tasks.py 亦用 `or 0` 防御）。可空与 share.py 的
    #   `is not None` 分支一致（最终审查 F-5 补 NULL 推导测试）。
    # server_default 与迁移文件一致（SQLite/MySQL 均需默认值）
    stardust_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    star_tier: Mapped[int | None] = mapped_column(Integer, default=0, server_default="0")
    # ── 手账连续 7 天星尘奖励周键（P1 T1-3）──
    # journal_streak_reward_week：ISO 周键 "YYYY-Www"（如 2026-W33），记录
    #   连续 7 天记录奖励最后一次发放所在的周；同周再次达标不重复发放（幂等）。
    #   写入模式与签到星尘一致（stardust_total += 1; star_tier = tier_for(...)）。
    journal_streak_reward_week: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # ── 星卡收藏 / 星光壁纸（P0-3：7 日稀有星卡 · 30 日星光壁纸）──
    # star_cards：JSON 数组字符串 [{"card_id": int, "date": "YYYY-MM-DD",
    #   "tier": "gold", "orientation": "upright"}, ...]（收藏品，不消耗额度）
    # wallpapers：JSON 数组字符串 ["YYYY-MM-DD", ...]（30 日壁纸达成日期）
    # 读写统一走 app.services.star_collectibles（脏数据解析安全回退空列表）
    star_cards: Mapped[str | None] = mapped_column(Text, nullable=True)
    wallpapers: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ── 星座能量（星光映照）──
    # zodiac: 12 星座 key（aries/taurus/...）；birth_* 二期星盘计算用，先存
    zodiac: Mapped[str | None] = mapped_column(String(16), nullable=True)
    birth_date: Mapped[str | None] = mapped_column(String(16), nullable=True)  # YYYY-MM-DD
    birth_time: Mapped[str | None] = mapped_column(String(16), nullable=True)  # HH:MM 或 HH:MM:SS
    birth_city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 开发 05：本命星盘三要素 + 深度报告付费
    # birthchart_paid：购买 birthchart_report 商品后置位（独立于会员）
    birthchart_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    # birthchart_json：三要素 AI 文案缓存（含指纹，出生信息变化时失效）
    birthchart_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # birthchart_report：深度报告缓存（首次生成后复用；重新生成需再付费或会员）
    birthchart_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ── 星友圈（SDD P2 · T8-1）：隐身开关 + 脱敏星名 ──
    # resonance_visible：默认 true（参与共鸣墙展示）；false = 一键隐身
    #   （共鸣墙聚合处过滤，见 Task 2）。server_default 与迁移文件一致
    #   （SQLite/MySQL 均需默认值，存量用户默认参与）。
    # star_alias：系统生成脱敏星名（"星星·晚风"式，40 词库确定性生成），
    #   首次访问 GET /resonance/alias 时落库（幂等）；对外展示只出星名，
    #   真实昵称/头像永不外泄。
    resonance_visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    star_alias: Mapped[str | None] = mapped_column(String(16), nullable=True)
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
