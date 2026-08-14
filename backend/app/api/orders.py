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

from app.config import settings
from app.db.database import get_db
from app.models.order import Order
from app.models.user import User
from app.schemas.order import CreateOrderRequest, CreateOrderResponse
from app.services.payment import (
    PRODUCTS,
    create_order_params,
    generate_order_no,
    sign_xpay_params,
    sign_xpay_signature,
)
from app.utils.auth import get_current_user, utc_aware

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["支付订单"])


async def create_order_for_user(
    db: AsyncSession, user: User, product_type: str
) -> CreateOrderResponse:
    """创建订单（POST /orders 端点与 POST /report/{type}/unlock 共用；T7-3）。

    xpay 虚拟支付通道（回归修复：按 tests/test_xpay.py 契约恢复）。
    """
    product = PRODUCTS.get(product_type)
    if not product:
        raise HTTPException(status_code=400, detail="无效的商品类型")

    # xpay 虚拟支付通道
    if settings.PAY_CHANNEL == "xpay":
        try:
            product_map = json.loads(settings.XPAY_PRODUCT_MAP or "{}") or {}
        except Exception:
            product_map = {}
        product_id = product_map.get(product_type)
        if not product_id:
            # 虚拟支付道具未配置 → 前端展示「商品即将上线」降级提示
            raise HTTPException(status_code=400, detail="该商品即将上线,敬请期待")
        if not user.session_key_encrypted:
            raise HTTPException(status_code=400, detail="登录凭证缺失,请重新登录")

        from app.services.session_key import decrypt_session_key

        try:
            session_key = decrypt_session_key(user.session_key_encrypted)
        except Exception:
            # 密文损坏/密钥变更/版本不符等 — 视为登录凭证缺失, 返回 400 引导重新登录
            logger.warning("decrypt_session_key failed for user %s", user.id, exc_info=True)
            session_key = None
        if not session_key:
            raise HTTPException(status_code=400, detail="登录凭证缺失,请重新登录")

        app_key = (
            settings.WX_XPAY_APPKEY_PROD
            if settings.WX_XPAY_ENV == 0
            else settings.WX_XPAY_APPKEY_SANDBOX
        )
        order_no = generate_order_no()
        env = int(settings.WX_XPAY_ENV or 0)
        goods_price = int(round(product["price"] * 100))

        sign_data = json.dumps(
            {
                "offerId": settings.WX_XPAY_OFFER_ID,
                "buyQuantity": 1,
                "env": env,
                "currencyType": "CNY",
                "productId": product_id,
                "goodsPrice": goods_price,
                "outTradeNo": order_no,
                "attach": product_type,
            },
            separators=(",", ":"),
        )

        order = Order(
            user_id=user.id,
            order_no=order_no,
            product_type=product_type,
            amount=product["price"],
            status="pending",
            pay_channel="xpay",
            env=env,
        )
        db.add(order)
        await db.flush()

        xpay_params = {
            "mode": "short_series_goods",
            "offerId": settings.WX_XPAY_OFFER_ID,
            "buyQuantity": 1,
            "env": env,
            "currencyType": "CNY",
            "productId": product_id,
            "goodsPrice": goods_price,
            "outTradeNo": order_no,
            "attach": product_type,
            "signData": sign_data,
            "paySig": sign_xpay_params(app_key, sign_data),
            "signature": sign_xpay_signature(session_key, sign_data),
        }
        return CreateOrderResponse(
            order_id=order.id,
            order_no=order.order_no,
            amount=order.amount,
            product_name=product["name"],
            payment_params=None,
            xpay_params=xpay_params,
        )

    order = Order(
        user_id=user.id,
        order_no=generate_order_no(),
        product_type=product_type,
        amount=product["price"],
        status="pending",
    )
    db.add(order)
    await db.flush()

    # Generate WeChat Pay JSAPI parameters
    payment_params = create_order_params(
        openid=user.openid,
        product_type=product_type,
        order_no=order.order_no,
    )

    if payment_params is None:
        raise HTTPException(
            status_code=503,
            detail="微信支付接口调用失败，请确认商户号已开通JSAPI支付产品权限",
        )

    return CreateOrderResponse(
        order_id=order.id,
        order_no=order.order_no,
        amount=order.amount,
        product_name=product["name"],
        payment_params=payment_params,
    )


@router.post("", response_model=CreateOrderResponse)
async def create_order(
    body: CreateOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new order and return WeChat Pay JSAPI payment parameters."""
    return await create_order_for_user(db, user, body.product_type)


@router.post("/callback")
async def payment_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """WeChat Pay payment notification callback.

    Security requirements (mandatory, no dev bypass):
    1. All four V3 signature headers must be present — otherwise 401.
    2. The ``Wechatpay-Signature`` must verify against the configured
       WeChat platform certificate — otherwise 401.
    3. After decryption the transaction must report ``trade_state ==
       "SUCCESS"``, the ``amount.total`` (fen) must equal the order
       amount, and ``out_trade_no`` must resolve to an order belonging
       to the payer — any mismatch returns 4xx and nothing is fulfilled.
    """
    # ── Read raw body as bytes (needed for signature verification) ──
    body_bytes = await request.body()

    # ── Extract V3 signature headers — ALL of them are mandatory ──
    wechatpay_signature = request.headers.get("Wechatpay-Signature", "")
    wechatpay_timestamp = request.headers.get("Wechatpay-Timestamp", "")
    wechatpay_nonce = request.headers.get("Wechatpay-Nonce", "")
    wechatpay_serial = request.headers.get("Wechatpay-Serial", "")

    required_headers = {
        "Wechatpay-Signature": wechatpay_signature,
        "Wechatpay-Timestamp": wechatpay_timestamp,
        "Wechatpay-Nonce": wechatpay_nonce,
        "Wechatpay-Serial": wechatpay_serial,
    }
    missing = [name for name, value in required_headers.items() if not value]
    if missing:
        logger.warning(
            "WeChat Pay callback rejected: missing required signature headers: %s",
            missing,
        )
        raise HTTPException(status_code=401, detail="缺少支付回调签名头")

    # ── Parse JSON body ──
    try:
        body_dict = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的JSON请求体")

    # ── Verify signature (mandatory) ──
    from app.services.payment import verify_wechat_v3_signature, decrypt_wechat_v3_resource

    if not (settings.WECHAT_PLATFORM_CERT_SERIAL and settings.WECHAT_PLATFORM_CERT):
        # Config TODO: platform cert must be uploaded before production go-live.
        # Code stays strict — callbacks cannot be verified without it.
        logger.error(
            "WeChat Pay callback rejected: WECHAT_PLATFORM_CERT_SERIAL / "
            "WECHAT_PLATFORM_CERT are not configured — cannot verify signature"
        )
        raise HTTPException(status_code=401, detail="签名验证失败")

    sign_str = f"{wechatpay_timestamp}\n{wechatpay_nonce}\n{body_bytes.decode('utf-8')}\n"
    if not verify_wechat_v3_signature(sign_str, wechatpay_signature, wechatpay_serial):
        logger.warning("WeChat Pay callback signature verification failed")
        raise HTTPException(status_code=401, detail="签名验证失败")

    # ── Decrypt the V3 resource (required) ──
    resource = body_dict.get("resource")
    if not resource:
        raise HTTPException(status_code=400, detail="缺少 resource")
    try:
        decrypted = decrypt_wechat_v3_resource(
            ciphertext=resource.get("ciphertext", ""),
            associated_data=resource.get("associated_data", ""),
            nonce=resource.get("nonce", ""),
        )
        txn = json.loads(decrypted)
    except Exception as exc:
        logger.exception("Failed to decrypt WeChat resource: %s", exc)
        raise HTTPException(status_code=400, detail="资源解密失败")

    # ── Business validation: trade_state must be SUCCESS ──
    trade_state = txn.get("trade_state")
    if trade_state != "SUCCESS":
        logger.warning(
            "WeChat callback trade_state=%s — order not fulfilled",
            trade_state,
        )
        raise HTTPException(status_code=400, detail="交易未成功")

    # ── Business validation: out_trade_no must exist and belong to the payer ──
    order_no = txn.get("out_trade_no")
    if not order_no:
        raise HTTPException(status_code=400, detail="缺少订单号")

    result = await db.execute(select(Order).where(Order.order_no == order_no))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # ── Business validation: amount.total (fen) must match the order ──
    amount = txn.get("amount") or {}
    total_fen = amount.get("total")
    expected_fen = int(round(float(order.amount) * 100))
    if total_fen is None or int(total_fen) != expected_fen:
        logger.warning(
            "WeChat callback amount mismatch for order %s: got %s fen, expected %s fen",
            order_no, total_fen, expected_fen,
        )
        raise HTTPException(status_code=400, detail="金额不匹配")

    user_result = await db.execute(select(User).where(User.id == order.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # ── Business validation: payer openid must be the order owner ──
    payer_openid = (txn.get("payer") or {}).get("openid")
    if payer_openid and payer_openid != user.openid:
        logger.warning(
            "WeChat callback payer openid mismatch for order %s: got %s, expected %s",
            order_no, payer_openid, user.openid,
        )
        raise HTTPException(status_code=400, detail="支付者与订单不一致")

    if order.status == "paid":
        # Idempotent — WeChat may resend the same notification
        return {"code": "SUCCESS"}

    order.status = "paid"
    order.paid_at = datetime.now(timezone.utc)

    # ── Apply benefit according to product_type ──────────────────────
    now = datetime.now(timezone.utc)

    if order.product_type == "single_reading":
        # Single-阅读 purchase: grant 1 paid reading credit
        user.paid_readings_balance = (user.paid_readings_balance or 0) + 1

    elif order.product_type == "membership_monthly":
        if utc_aware(user.member_expires_at) and utc_aware(user.member_expires_at) > now:
            user.member_expires_at += timedelta(days=30)
        else:
            user.member_expires_at = now + timedelta(days=30)
        user.is_member = True

    elif order.product_type == "membership_yearly":
        if utc_aware(user.member_expires_at) and utc_aware(user.member_expires_at) > now:
            user.member_expires_at += timedelta(days=365)
        else:
            user.member_expires_at = now + timedelta(days=365)
        user.is_member = True

    elif order.product_type == "membership_student":
        if utc_aware(user.member_expires_at) and utc_aware(user.member_expires_at) > now:
            user.member_expires_at += timedelta(days=30)
        else:
            user.member_expires_at = now + timedelta(days=30)
        user.is_member = True

    elif order.product_type == "membership_lifetime":
        user.is_member = True
        user.member_expires_at = None  # Never expires

    elif order.product_type == "reading_pack_3":
        user.paid_readings_balance = (user.paid_readings_balance or 0) + 3

    elif order.product_type == "reading_pack_10":
        user.paid_readings_balance = (user.paid_readings_balance or 0) + 10

    elif order.product_type == "annual_report":
        # P0-1 fix: standalone annual-report purchase unlocks the user's
        # /report/annual access (independent of membership).
        user.annual_report_paid = True

    elif order.product_type == "birthchart_report":
        # 开发 05: standalone birth-chart deep-report purchase unlocks
        # POST /user/birthchart/report (independent of membership).
        user.birthchart_paid = True

    elif order.product_type == "weekly_report":
        # SDD P2 · T7-3: standalone weekly-report purchase (¥4.90) unlocks
        # GET /report/week full access (independent of membership).
        user.weekly_report_unlocked = True

    elif order.product_type == "monthly_report":
        # SDD P2 · T7-3: standalone monthly-report purchase (¥19.90) unlocks
        # GET /report/month full access (independent of membership).
        user.monthly_report_unlocked = True

    await db.flush()
    return {"code": "SUCCESS"}


@router.get("/{order_no}/status")
async def order_status(
    order_no: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询订单状态（支付后前端确认用）。仅订单所属用户可查询。"""
    result = await db.execute(select(Order).where(Order.order_no == order_no))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该订单")
    # xpay 远程状态查询（remote=true 时向微信虚拟支付查询，不回退本地权益）
    if order.pay_channel == "xpay" and (request.query_params.get("remote") == "true"):
        from app.services.xpay_api import XPAY_STATUS_TO_LOCAL, query_order

        try:
            remote = await query_order(
                out_trade_no=order.order_no,
                env=order.env if order.env is not None else int(settings.WX_XPAY_ENV or 0),
                openid=user.openid,
            )
        except Exception:
            remote = None
        remote_state = None
        if remote:
            # 小程序虚拟支付官方契约: 状态在 order.status (3/4=已支付 5/8=已退款 6=已取消)
            state = (remote.get("order") or {}).get("status")
            remote_state = XPAY_STATUS_TO_LOCAL.get(state)

        # 远程已退款 → 本地标记 refunded（权益已发放的订单永不回退状态）
        if remote_state == "refunded" and order.status not in ("paid",):
            order.refund_status = "refunded"
            order.status = "refunded"
            await db.flush()

        return {
            "order_no": order.order_no,
            "status": order.status,
            "paid": order.status == "paid",
            "amount": float(order.amount),
            "product_type": order.product_type,
            "paid_at": order.paid_at,
            "remote": True,
            "remote_state": remote_state,
        }

    return {
        "order_no": order.order_no,
        "status": order.status,
        "paid": order.status == "paid",
        "amount": float(order.amount),
        "product_type": order.product_type,
        "paid_at": order.paid_at,
    }
