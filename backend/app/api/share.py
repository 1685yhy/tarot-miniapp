"""
Share / viral-tracking API endpoints.

- POST  /share/track       – log a share event and reward the sharer
- POST  /share/invite      – accept invite code from new user, reward both
- GET   /share/stats       – share analytics for the current user
- GET   /share/invite-code – generate/return user's unique invite code
- GET   /share/wxa-code    – generate a mini-program code image (wxacode)
- GET   /share/wxacode     – user's 星光名片 mini-program code (scene=invite_code,
                             env_version=trial, 7-day cache, login required)
- GET   /share/card-info   – look up star-card profile by invite code (public,
                             for the scan landing page)
- GET   /share/zodiac-match – relationship tarot card for a zodiac pairing (fun share)
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.card import TarotCard
from app.models.user import User
from app.services.ai_engine import ZODIAC_CN, generate_zodiac_match
from app.services.share import (
    get_share_stats,
    record_share,
    get_or_create_invite_code,
    process_invite,
)
from app.services.stardust import tier_for, tier_name
from app.services.wxacode import get_wxacode
from app.utils.auth import get_current_user

# ── 星光名片小程序码缓存：每用户 7 天，避免高频重复调用微信接口 ──
_WXACODE_CACHE_TTL = 7 * 24 * 3600
_wxacode_cache: dict[str, tuple[float, bytes]] = {}

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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Track a share event (requires login).

    The sharer is always the authenticated user — any ``sharer_id`` sent
    in the body is ignored (prevents inflating other accounts' rewards).
    """
    result = await record_share(
        db,
        sharer_id=user.id,  # forced — body.sharer_id is ignored
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

    Gives BOTH the inviter and the invitee +1 free deep reading each.
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
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# 星光名片（Task 7）：小程序码 + 扫码落地页信息
# ---------------------------------------------------------------------------


@router.get("/wxacode")
async def star_card_wxacode(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    生成当前用户的星光名片小程序码（需要登录）。

    调用微信 ``getwxacodeunlimit``：
      - scene        = user.invite_code（好友扫码后落地 card-landing）
      - page         = pages/card-landing/card-landing
      - env_version  = trial（体验版构建即可扫码打开）
    结果按用户缓存 7 天（内存 dict），避免重复调用微信接口。

    Returns: PNG 字节流（image/png）
    """
    code = await get_or_create_invite_code(db, user)

    now = time.time()
    cached = _wxacode_cache.get(user.id)
    if cached and cached[0] > now:
        return Response(content=cached[1], media_type="image/png")

    try:
        png_bytes = await get_wxacode(
            scene=code,
            page="pages/card-landing/card-landing",
            width=430,
            env_version="trial",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    _wxacode_cache[user.id] = (now + _WXACODE_CACHE_TTL, png_bytes)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/card-info")
async def star_card_info(
    code: str = Query(..., description="邀请码 STAR-XXXX"),
    db: AsyncSession = Depends(get_db),
):
    """
    按邀请码查星光名片信息（公开接口：扫码落地页无需登录）。

    仅返回海报上已公开的展示字段——昵称 / 星阶 / 星光值，
    不泄露任何联系方式或账号敏感信息。
    """
    result = await db.execute(select(User).where(User.invite_code == code))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    tier = user.star_tier if user.star_tier is not None else tier_for(user.stardust_total or 0)
    return {
        "invite_code": user.invite_code,
        "nickname": user.nickname or "一位星光旅人",
        "star_tier": tier,
        "star_tier_name": tier_name(tier),
        "stardust_total": user.stardust_total or 0,
    }


# ---------------------------------------------------------------------------
# Zodiac match — fun relationship tarot card (v1.5 viral feature)
# ---------------------------------------------------------------------------

# Local fallback blurbs, used when the AI service is unavailable.
# Tone: light and playful — the card is a fun lens on a pairing,
# never "destiny" language. {cn1} {cn2} {card} are format placeholders.
_FALLBACK_MATCH_TEXTS = [
    "「{card}」为你们点题：{cn1}负责开场白，{cn2}负责接梗，话匣子一开就关不上。",
    "这对组合像鸳鸯锅：{cn1}爱涮辣的，{cn2}爱涮清的，口味不同，但一桌吃得开心。今天的主题曲是「{card}」。",
    "「{card}」说：{cn1}负责想点子，{cn2}负责兜底，一个敢想一个敢接，玩起来刚刚好。",
    "{cn1}加{cn2}，像奶茶加珍珠——本来就挺好喝，加上彼此更有嚼劲。「{card}」表示很看好你们这局。",
]


@router.get("/zodiac-match")
async def zodiac_match(
    sign1: str = Query(..., description="第一个星座 key，如 aries"),
    sign2: str = Query(..., description="第二个星座 key，如 taurus"),
    db: AsyncSession = Depends(get_db),
):
    """
    星座契合度 · 塔罗关系牌（轻松玩法，用于分享裂变）。

    随机抽一张塔罗牌作为这对星座组合的「关系牌」，并让 AI 生成一段
    简短、有趣、温暖的契合度解读。

    Tone: fun and light — 是「你们的塔罗关系牌」，不是「你们的命运」。
    不提供任何奖励承诺，避免诱导分享。

    Returns:
        {
          "card_id": int,
          "card_name": str,            # 中文牌名
          "name_en": str,              # 英文牌名（前端据此计算牌图路径）
          "arcana": str, "card_number": int, "suit": str | None,
          "compatibility_text": str,   # AI 生成的契合度解读
          "share_text": str,           # 海报分享文案
        }
    """
    cn1 = ZODIAC_CN.get(sign1.lower())
    cn2 = ZODIAC_CN.get(sign2.lower())
    if not cn1 or not cn2:
        raise HTTPException(status_code=400, detail="星座参数无效，请使用 aries 等标准 key")

    # Randomly draw the "relationship card" for this pairing
    result = await db.execute(select(TarotCard).order_by(func.random()).limit(1))
    card = result.scalar_one_or_none()
    if card is None:
        raise HTTPException(status_code=500, detail="卡牌数据为空")

    compatibility_text = await generate_zodiac_match(sign1, sign2, card.name_zh)
    if not compatibility_text:
        import random
        template = random.choice(_FALLBACK_MATCH_TEXTS)
        compatibility_text = template.format(cn1=cn1, cn2=cn2, card=card.name_zh)

    share_text = (
        f"{cn1} + {cn2} 的塔罗关系牌是「{card.name_zh}」，"
        f"看看你和谁的星座最契合 ✦"
    )

    return {
        "card_id": card.id,
        "card_name": card.name_zh,
        "name_en": card.name_en,
        "arcana": card.arcana,
        "card_number": card.card_number,
        "suit": card.suit,
        "compatibility_text": compatibility_text,
        "share_text": share_text,
    }
