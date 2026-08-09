"""订单权益发放 — 支付回调(JSAPI)与 xpay 发货通知共用的唯一实现。

``fulfill_order`` 是幂等的: 订单已 paid 时直接返回 False(不重复发权益),
返回 True 表示本次实际发放了权益并更新订单状态。
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.auth import utc_aware

logger = logging.getLogger(__name__)


async def fulfill_order(
    db: AsyncSession,
    order,
    user,
    txn_meta: dict | None = None,
) -> bool:
    """Grant the order's benefit to the user (idempotent).

    Parameters
    ----------
    order : Order
        The order to fulfill (must be paid / paid-attested).
    user : User
        The order owner.
    txn_meta : dict, optional
        Optional transaction metadata (e.g. {"channel": "xpay", "env": 0})
        recorded on the order for audit; defaults to None.

    Returns
    -------
    bool
        True when benefits were granted in this call, False when the order
        was already fulfilled (idempotent no-op).
    """
    if order.status == "paid":
        return False

    txn_meta = txn_meta or {}
    channel = txn_meta.get("channel")
    if channel and not order.pay_channel:
        order.pay_channel = channel
    if txn_meta.get("env") is not None and order.env is None:
        order.env = int(txn_meta["env"])

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

    order.status = "paid"
    order.paid_at = now
    order.delivered_at = now
    await db.flush()
    return True
