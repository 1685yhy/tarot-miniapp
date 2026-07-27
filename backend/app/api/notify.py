"""
Push notification subscription and sending endpoints.

- ``POST /notify/subscribe`` — record a user's push subscription preference.
- ``POST /notify/send-daily`` — admin-triggered batch send of daily card push.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.push import (
    TEMPLATE_DAILY_CARD,
    TEMPLATE_MEMBER_EXPIRE,
    TEMPLATE_ANNUAL_REPORT,
    send_subscribe_message,
    build_daily_card_data,
    build_member_expire_data,
    build_annual_report_data,
)
from app.utils.auth import get_current_user

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
# POST /notify/send-daily — admin-triggered daily card push
# ---------------------------------------------------------------------------


@router.post("/send-daily", response_model=SendDailyResponse)
async def trigger_daily_push(
    admin_id: str = Header(..., alias="x-admin-user-id"),
    db: AsyncSession = Depends(get_db),
):
    """Admin-triggered: send daily card push to all subscribed users.

    WeChat limit: 1 000 sends per hour per template. This endpoint sends
    to all currently-subscribed users for the daily-card template.
    """
    # Check admin auth
    from app.config import settings

    if not admin_id or admin_id not in settings.SUPER_ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden: not a super-admin")

    # Fetch all subscribed users for daily card
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.template_id == TEMPLATE_DAILY_CARD,
            PushSubscription.subscribed == True,  # noqa: E712
        )
    )
    subscriptions = result.scalars().all()

    if not subscriptions:
        return SendDailyResponse(sent=0, failed=0)

    # Respect WeChat hourly limit (cap at 1000)
    batch = subscriptions[:1000]

    sent = 0
    failed = 0
    for sub in batch:
        try:
            data = build_daily_card_data(
                card_name="今日塔罗",
                keyword="查看今日指引",
                date_str="",
                hint="你的每日一牌已就绪",
            )
            resp = await send_subscribe_message(
                openid=sub.openid,
                template_id=TEMPLATE_DAILY_CARD,
                data=data,
                page="pages/daily-card/daily-card",
            )
            if resp.get("errcode") == 0:
                sent += 1
            else:
                failed += 1
        except Exception:
            logger.exception("send-daily push failed for user=%s", sub.user_id)
            failed += 1

    logger.info("send-daily complete: sent=%d failed=%d", sent, failed)
    return SendDailyResponse(sent=sent, failed=failed)
