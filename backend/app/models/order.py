import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import Integer, String, DateTime, ForeignKey, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import CHAR
from app.db.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("users.id"), nullable=False, index=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # 微信支付订单号
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)  # single_reading/membership/annual_report
    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/paid/refunded/cancelled
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    # xpay 虚拟支付字段（回归修复：外部还原丢失的 WIP 集成，按 alembic a5f6b7c8d9e0 恢复）
    pay_channel: Mapped[str | None] = mapped_column(String(16), nullable=True)  # jsapi / xpay
    env: Mapped[int | None] = mapped_column(Integer, nullable=True)  # xpay 环境: 0=正式 1=沙箱
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # xpay 发货回执时间
    refund_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # refunded 等

    user: Mapped["User"] = relationship(back_populates="orders")
