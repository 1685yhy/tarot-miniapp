"""
Push notification subscription and sending endpoints.

- ``POST /notify/subscribe`` — record a user's push subscription preference.
- ``POST /notify/subscribe-grant`` — 星光晨讯额度发放（用户授权订阅消息后调用，quota+1）。
- ``POST /notify/send-daily`` — admin-triggered 星光晨讯（按额度消费发送）。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.push_subscription import PushSubscription
from app.models.subscribe_quota import SubscribeQuota
from app.models.user import User
from app.services.push import (
    TEMPLATE_DAILY_CARD,
    TEMPLATE_MEMBER_EXPIRE,
    TEMPLATE_ANNUAL_REPORT,
    is_template_configured,
)
from app.utils.auth import get_current_user, get_user_from_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notify", tags=["推送"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class SubscribeRequest(BaseModel):
    openid: str
    template_id: str
    accept: bool


class SubscribeResponse(BaseModel):
    ok: bool


class SubscribeGrantResponse(BaseModel):
    ok: bool
    quota_available: int


class SendDailyRequest(BaseModel):
    """Admin-triggered daily push (optional — if body is empty, defaults apply)."""


class SendDailyResponse(BaseModel):
    sent: int
    failed: int


# ---------------------------------------------------------------------------
# POST /notify/subscribe — record subscription preference
# ---------------------------------------------------------------------------


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_push(
    req: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a user's push subscription preference for a given template.

    If ``accept`` is True, creates or reactivates a PushSubscription row.
    If ``accept`` is False, deactivates (sets subscribed=False) any existing row.
    """
    # Validate template_id against known templates
    known_templates = {TEMPLATE_DAILY_CARD, TEMPLATE_MEMBER_EXPIRE, TEMPLATE_ANNUAL_REPORT}
    if req.template_id not in known_templates:
        raise HTTPException(status_code=400, detail=f"Unknown template_id: {req.template_id}")

    # P0-4: without a real (approved) template ID configured the push service
    # is not open — refuse the subscription instead of storing dead rows.
    if not is_template_configured(req.template_id):
        raise HTTPException(status_code=400, detail="推送服务未开通")

    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.template_id == req.template_id,
        )
    )
    sub = result.scalar_one_or_none()

    if sub:
        sub.subscribed = req.accept
        sub.openid = req.openid
    else:
        sub = PushSubscription(
            user_id=user.id,
            openid=req.openid,
            template_id=req.template_id,
            subscribed=req.accept,
        )
        db.add(sub)

    await db.flush()
    logger.info(
        "Push subscription %s for user=%s template=%s",
        "accepted" if req.accept else "rejected",
        user.id,
        req.template_id,
    )
    return SubscribeResponse(ok=True)


# ---------------------------------------------------------------------------
# POST /notify/subscribe-grant — 星光晨讯额度发放
# ---------------------------------------------------------------------------


@router.post("/subscribe-grant", response_model=SubscribeGrantResponse)
async def subscribe_grant(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """星光晨讯额度发放：用户授权微信订阅消息后调用，quota+1。

    微信订阅消息为一次性订阅 —— 授权 1 次 = 1 条发送额度。额度由 daily_push
    在每天 7:37 发送「今日星光」时消费（成功发送后 -1、记 last_sent_date）。
    """
    result = await db.execute(
        select(SubscribeQuota).where(SubscribeQuota.user_id == user.id)
    )
    quota = result.scalar_one_or_none()
    if quota:
        quota.quota_available += 1
    else:
        quota = SubscribeQuota(user_id=user.id, quota_available=1)
        db.add(quota)
    await db.commit()
    logger.info(
        "星光晨讯额度发放：user=%s quota=%d", user.id, quota.quota_available
    )
    return SubscribeGrantResponse(ok=True, quota_available=quota.quota_available)


# ---------------------------------------------------------------------------
# POST /notify/send-daily — admin-triggered 星光晨讯（按额度消费发送）
# ---------------------------------------------------------------------------


@router.post("/send-daily", response_model=SendDailyResponse)
async def trigger_daily_push(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Admin-triggered: 星光晨讯按额度消费发送（与 7:37 定时任务同一逻辑）。

    WeChat limit: 1 000 sends per hour per template. 每成功发送 1 条消耗
    1 条订阅额度（quota-1）并记 last_sent_date。
    """
    # Admin auth: valid JWT whose user id is in SUPER_ADMIN_IDS (same policy as /admin)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        raise HTTPException(status_code=403, detail="Forbidden: not a super-admin")
    admin = await get_user_from_token(auth_header.replace("Bearer ", ""), db)
    if admin.id not in settings.super_admin_ids():
        raise HTTPException(status_code=403, detail="Forbidden: not a super-admin")

    # P0-4: real template ID must be configured, otherwise the service is closed.
    if not is_template_configured(TEMPLATE_DAILY_CARD):
        raise HTTPException(
            status_code=400,
            detail="推送服务未开通（请在 .env 配置 WX_TEMPLATE_DAILY_CARD 真实模板 ID）",
        )

    from app.services.daily_push import send_starlight_morning_if_due

    result = await send_starlight_morning_if_due(db)
    if result["status"] == "skipped_config":
        raise HTTPException(
            status_code=400,
            detail="推送服务未开通（请在 .env 配置 WX_TEMPLATE_DAILY_CARD 真实模板 ID）",
        )
    logger.info("send-daily complete: %s", result)
    return SendDailyResponse(sent=result.get("sent", 0), failed=result.get("failed", 0))
