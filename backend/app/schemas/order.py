"""
Pydantic schemas for the orders / payment API.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CreateOrderRequest(BaseModel):
    """Request body when the user creates a new order."""

    product_type: str = Field(..., description="商品类型, 如 membership_lifetime")


class CreateOrderResponse(BaseModel):
    """Returned immediately after a new order is created."""

    order_id: str
    order_no: str
    amount: Decimal
    product_name: str
    payment_params: dict | None = None  # wx.requestPayment payload


class PaymentCallbackRequest(BaseModel):
    """WeChat Pay callback notification body (simplified)."""

    out_trade_no: str | None = None
    transaction_id: str | None = None
    result_code: str | None = None
    openid: str | None = None


class OrderResponse(BaseModel):
    """Full order model returned to the client."""

    id: str
    order_no: str
    product_type: str
    amount: Decimal
    status: str
    paid_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
