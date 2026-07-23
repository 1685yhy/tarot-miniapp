"""
Share / viral-tracking API endpoints.

- POST  /share/track       – log a share event and reward the sharer
- POST  /share/invite      – accept invite code from new user, reward both
- GET   /share/stats       – share analytics for the current user
- GET   /share/invite-code – generate/return user's unique invite code
- GET   /share/wxa-code    – generate a mini-program code image (wxacode)
"""

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.services.share import (
    get_share_stats,
    record_share,
    get_or_create_invite_code,
    process_invite,
)
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
    share_count: int = 0
    reward_tier: int | None = None


class InviteRequest(BaseModel):
    invite_code: str


class InviteResponse(BaseModel):
    success: bool
    error: str | None = None
    inviter_reward: int | None = None
    invitee_reward: int | None = None
    inviter_name: str | None = None


class InviteCodeResponse(BaseModel):
    invite_code: str


class ShareStatsResponse(BaseModel):
    total_shares: int = 0
    share_count: int = 0
    channels: dict[str, int] = {}
    total_invites: int = 0
    friends_joined: int = 0
    free_deep_readings: int = 0
    free_readings_earned: int = 0
    reward_tier: int = 0
    next_reward_tier: dict | None = None
    invite_code: str | None = None


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

    If *sharer_id* is provided the user's share_count increments and
    tier-based rewards are evaluated.
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
        share_count=result["share_count"],
        reward_tier=result["reward_tier"],
    )


@router.post("/invite", response_model=InviteResponse)
async def invite(
    body: InviteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept an invite code from a new user.

    Gives BOTH the inviter and the invitee +3 free deep readings each.
    """
    result = await process_invite(db, inviter_code=body.invite_code, invitee_user=user)
    if not result["success"]:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result["error"])
    return InviteResponse(
        success=True,
        inviter_reward=result["inviter_reward"],
        invitee_reward=result["invitee_reward"],
        inviter_name=result["inviter_name"],
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


@router.get("/invite-code", response_model=InviteCodeResponse)
async def get_invite_code(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's unique invite code (generates if not yet created)."""
    code = await get_or_create_invite_code(db, user)
    return InviteCodeResponse(invite_code=code)


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
