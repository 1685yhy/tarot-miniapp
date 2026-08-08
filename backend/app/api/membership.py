"""
Membership-status, product-listing, and coupon-redeem endpoints.

- GET  /membership/status   – current user's membership info
- GET  /membership/products – available products to purchase
- POST /membership/redeem   – redeem a coupon code for trial membership
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.user import User
from app.services.payment import PRODUCTS
from app.utils.auth import get_current_user

router = APIRouter(prefix="/membership", tags=["会员"])


@router.get("/status")
async def membership_status(user: User = Depends(get_current_user)):
    """Return the current user's membership details."""
    return {
        "is_member": user.is_member,
        "expires_at": user.member_expires_at,
        "free_readings_today": user.free_readings_today,
        "free_chats_today": user.free_chats_today,
        # P0-1: standalone annual-report purchase entitlement (frontend
        # merges this into its cached user via checkLogin({refresh:true}))
        "annual_report_paid": user.annual_report_paid,
        # 开发 05: standalone birth-chart report purchase entitlement
        "birthchart_paid": user.birthchart_paid,
        "free_quota": {
            "daily_readings": settings.FREE_DAILY_READINGS,
            "daily_chats": settings.FREE_CHAT_MESSAGES,
            "readings_used_today": user.free_readings_today,
            "chats_used_today": user.free_chats_today,
        },
    }


@router.get("/products")
async def list_products():
    """List all purchasable products."""
    return [
        {"id": k, "name": v["name"], "price": v["price"], "type": v.get("type", "single_purchase")}
        for k, v in PRODUCTS.items()
    ]


@router.post("/redeem")
async def redeem_coupon(
    code: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Redeem a coupon code for trial membership."""
    REVIEW_CODES = {
        "REVIEW2026": 7,  # 7 days trial for WeChat review
    }
    days = REVIEW_CODES.get(code)
    if not days:
        raise HTTPException(status_code=400, detail="无效的优惠码")

    now = datetime.utcnow()
    if user.is_member and user.member_expires_at:
        user.member_expires_at = max(
            user.member_expires_at,
            now + timedelta(days=days),
        )
    else:
        user.member_expires_at = now + timedelta(days=days)
        user.is_member = True

    await db.commit()
    return {"ok": True, "expires_at": user.member_expires_at.isoformat()}
