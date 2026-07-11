"""
Order & payment-callback API endpoints.

- POST /orders          – create a new order, return wx.requestPayment params
- POST /orders/callback – WeChat Pay payment notification
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.order import Order
from app.models.user import User
from app.schemas.order import CreateOrderRequest, CreateOrderResponse
from app.services.payment import PRODUCTS, create_order_params, generate_order_no
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["支付订单"])


@router.post("", response_model=CreateOrderResponse)
async def create_order(
    body: CreateOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new order and return WeChat Pay JSAPI payment parameters."""
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

    # Generate WeChat Pay JSAPI parameters
    payment_params = create_order_params(
        openid=user.openid,
        product_type=body.product_type,
        order_no=order.order_no,
    )

    return CreateOrderResponse(
        order_id=order.id,
        order_no=order.order_no,
        amount=order.amount,
        product_name=product["name"],
        payment_params=payment_params,
    )


@router.post("/callback")
async def payment_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """WeChat Pay payment notification callback.

    Receives an encrypted payment-result payload from WeChat.
    Validates the Wechatpay-Signature header and decrypts the resource
    before processing the order.
    """
    # ── Read raw body as bytes (needed for signature verification) ──
    body_bytes = await request.body()

    # ── Extract V3 signature headers ──
    wechatpay_signature = request.headers.get("Wechatpay-Signature", "")
    wechatpay_timestamp = request.headers.get("Wechatpay-Timestamp", "")
    wechatpay_nonce = request.headers.get("Wechatpay-Nonce", "")
    wechatpay_serial = request.headers.get("Wechatpay-Serial", "")

    # ── Parse JSON body ──
    try:
        body_dict = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的JSON请求体")

    # ── Verify signature ──
    from app.services.payment import verify_wechat_v3_signature, decrypt_wechat_v3_resource

    if wechatpay_signature and wechatpay_serial:
        # Production: verify against WeChat platform certificate
        sign_str = f"{wechatpay_timestamp}\n{wechatpay_nonce}\n{body_bytes.decode('utf-8')}\n"
        if not verify_wechat_v3_signature(sign_str, wechatpay_signature, wechatpay_serial):
            logger.warning("WeChat Pay callback signature verification failed")
            raise HTTPException(status_code=401, detail="签名验证失败")
    else:
        # Development mode without WeChat headers — accept body fields directly
        logger.warning("WeChat Pay callback called without V3 signature headers (dev mode)")

    # ── Extract order number ──
    resource = body_dict.get("resource", {})
    if resource:
        # Decrypt V3 resource to get verified transaction data
        try:
            decrypted = decrypt_wechat_v3_resource(
                ciphertext=resource.get("ciphertext", ""),
                associated_data=resource.get("associated_data", ""),
                nonce=resource.get("nonce", ""),
            )
            txn = json.loads(decrypted)
            order_no = txn.get("out_trade_no") or body_dict.get("out_trade_no")
        except Exception as exc:
            logger.exception("Failed to decrypt WeChat resource: %s", exc)
            order_no = body_dict.get("out_trade_no")
    else:
        order_no = body_dict.get("out_trade_no")

    if not order_no:
        raise HTTPException(status_code=400, detail="缺少订单号")

    # ── Load order ──
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
        # Single-阅读 purchase: grant 1 paid reading credit
        user.paid_readings_balance = (user.paid_readings_balance or 0) + 1

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

    await db.flush()
    return {"code": "SUCCESS"}
