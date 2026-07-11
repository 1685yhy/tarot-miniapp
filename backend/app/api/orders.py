"""
Order & payment-callback API endpoints.

- POST /orders          – create a new order
- POST /orders/callback – WeChat Pay payment notification
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.order import Order
from app.models.user import User
from app.schemas.order import CreateOrderRequest, CreateOrderResponse
from app.services.payment import PRODUCTS, generate_order_no
from app.utils.auth import get_current_user

router = APIRouter(prefix="/orders", tags=["支付订单"])


@router.post("", response_model=CreateOrderResponse)
async def create_order(
    body: CreateOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new order and return basic payment information."""
    product = PRODUCTS.get(body.product_type)
    if not product:
        raise HTTPException(status_code=400, detail="无效的商品类型")

    order = Order(
        user_id=user.id,
        order_no=generate_order_no(),
        product_type=body.product_type,
        amount=product["price"],
        status="pending",
    )
    db.add(order)
    await db.flush()

    return CreateOrderResponse(
        order_id=order.id,
        order_no=order.order_no,
        amount=order.amount,
        product_name=product["name"],
    )


@router.post("/callback")
async def payment_callback(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """WeChat Pay payment notification callback.

    Receives an encrypted payment-result payload from WeChat.
    This simplified implementation assumes the body contains
    ``out_trade_no`` and updates the order / user state accordingly.
    """
    order_no = body.get("out_trade_no")
    if not order_no:
        raise HTTPException(status_code=400, detail="缺少订单号")

    result = await db.execute(select(Order).where(Order.order_no == order_no))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    if order.status == "paid":
        # Idempotent — WeChat may resend the same notification
        return {"code": "SUCCESS"}

    order.status = "paid"
    order.paid_at = datetime.now(timezone.utc)

    # ── Apply benefit according to product_type ──────────────────────
    user_result = await db.execute(select(User).where(User.id == order.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    now = datetime.now(timezone.utc)

    if order.product_type == "single_reading":
        pass  # Credits / reading allowance handled elsewhere

    elif order.product_type == "membership_monthly":
        if user.member_expires_at and user.member_expires_at > now:
            user.member_expires_at += timedelta(days=30)
        else:
            user.member_expires_at = now + timedelta(days=30)
        user.is_member = True

    elif order.product_type == "membership_yearly":
        if user.member_expires_at and user.member_expires_at > now:
            user.member_expires_at += timedelta(days=365)
        else:
            user.member_expires_at = now + timedelta(days=365)
        user.is_member = True

    elif order.product_type == "membership_lifetime":
        user.is_member = True
        user.member_expires_at = None  # Never expires

    # annual_report – no membership benefit, handled by report system

    return {"code": "SUCCESS"}
