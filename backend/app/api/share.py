"""
Share / viral-tracking API endpoints.

- POST  /share/track   – log a share event and reward the sharer
- GET   /share/stats   – (optional) share analytics for the current user
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.services.share import get_share_stats, record_share
from app.utils.auth import get_current_user

router = APIRouter(prefix="/share", tags=["分享裂变"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class TrackShareRequest(BaseModel):
    sharer_id: str | None = None
    channel: str | None = None  # e.g. "wechat_friend", "wechat_moments", "qq", "link"
    share_type: str | None = None  # e.g. "reading", "card", "diary"
    ref_id: str | None = None  # optional: reading_id / card_id being shared


class TrackShareResponse(BaseModel):
    success: bool = True
    rewarded: bool = False
    free_readings_remaining: int | None = None


class ShareStatsResponse(BaseModel):
    total_shares: int = 0
    channels: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/track", response_model=TrackShareResponse)
async def track_share(
    body: TrackShareRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Track a share event.

    If *sharer_id* is provided the user receives a reward (one free reading
    returned). No authentication is required so the event can be recorded even
    before the user logs in (e.g. from a cached card-share page).
    """
    result = await record_share(
        db,
        sharer_id=body.sharer_id,
        channel=body.channel,
        share_type=body.share_type,
        ref_id=body.ref_id,
    )
    return TrackShareResponse(
        success=True,
        rewarded=result["rewarded"],
        free_readings_remaining=result["free_readings_remaining"],
    )


@router.get("/stats", response_model=ShareStatsResponse)
async def share_stats(
    days: int = 7,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return share-analytics for the authenticated user.

    *days* controls the look-back window (default 7).
    """
    return await get_share_stats(db, sharer_id=user.id, days=days)
