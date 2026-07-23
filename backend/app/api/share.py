"""
Share / viral-tracking API endpoints.

- POST  /share/track       – log a share event and reward the sharer
- GET   /share/stats       – (optional) share analytics for the current user
- GET   /share/wxa-code    – generate a mini-program code image (wxacode)
"""

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.services.share import get_share_stats, record_share
from app.services.wxacode import get_wxacode
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


@router.get("/wxa-code")
async def wxa_code(
    page: str = Query("pages/index/index", description="Mini-program page path"),
    width: int = Query(280, ge=200, le=1280, description="QR code width in px"),
    scene: str = Query("", description="Scene string (max 32 chars)"),
):
    """
    Generate a WeChat mini-program code (unlimited) image.

    Calls WeChat's ``wxacode.getUnlimited`` API under the hood and returns
    the raw PNG bytes directly, so the client can display it on a canvas or
    save it.

    - **page**  — path to the published page (default: ``pages/index/index``)
    - **width** — image width in px (200–1280, default: 280)
    - **scene** — optional scene string passed to the mini-program on scan
    """
    try:
        png_bytes = await get_wxacode(scene=scene, page=page, width=width)
        return Response(content=png_bytes, media_type="image/png")
    except RuntimeError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=str(exc))
