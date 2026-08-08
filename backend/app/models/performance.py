"""埋点事件模型 —— 前端性能指标与 JS 错误统一落库。

两类数据共用一张表：
- 性能埋点：metric 为指标名（如 firstPageReady、pageReady:pages/...），value 为时长（ms）
- 前端 JS 错误：metric 固定为 "js_error"，value 为 NULL，message/stack 存在 extra

表按 created_at 保留最近 30 天，写入时惰性清理（见 monitor.py）。
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PerformanceEvent(Base):
    __tablename__ = "performance_events"
    __table_args__ = (
        Index("ix_performance_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # 预留：登录后带 token 上报时填充
    page: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 页面路径，如 pages/index/index
    metric: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # 指标名 / "js_error"
    value: Mapped[float | None] = mapped_column(Float, nullable=True)  # 时长 ms；错误事件为 NULL
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # platform / sdk / message / stack 等
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
