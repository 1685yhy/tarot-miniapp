"""
星辰相遇（SDD P1 · T2-2）API — 相遇记录表 + 快速合盘 + 结果详情/列表/海报。

四端点（全部 get_current_user 鉴权，全局限流中间件覆盖）：
- POST /meet/quick            快速合盘：发起人三要素（users.zodiac + birthchart 派生）
                               + b 三要素（b_birth_date → sun/moon，b_birth_time → rising）
                               → 合盘（compute_compatibility）→ 三牌 + 相处提示
                               → 落库 status=completed + result_json → 完整结果
- GET  /meet/list             我的相遇列表（发起或参与，created_at 倒序）
- GET  /meet/{meet_id}        结果详情（鉴权：initiator 或 friend_user_id，否则 404）
- GET  /meet/{meet_id}/poster 脱敏海报数据（昵称/星座/score/level/牌面摘要/分享文案）

确定性：合盘三牌 seed = f"{a 出生日期}|{b 出生日期}|{今天}"（同日同人恒定，
与 pick_daily_card 同哲学）；相处提示由 MEET_TIPS 池确定性轮选。

PII 最小化：落库只存派生星座 key（a_zodiac/a_moon/a_rising/b_zodiac/b_moon/b_rising），
不存出生日期/时间明文；result_json 只含分数/牌面/提示。

合规：输出全部走「相处方式描述」框架（相合度分数 + 相处提示），
禁 注定/天生一对 类措辞（测试禁词扫描）；结果页固定免责行由前端渲染。
"""

import hashlib
import json
import logging
import re
import time
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.rate_limit import meet_info_rate_limit
from app.models.card import TarotCard
from app.models.star_meeting import StarMeeting
from app.models.user import User
from app.schemas.meet import (
    MeetDetailResponse,
    MeetInviteRequest,
    MeetJoinRequest,
    MeetJoinResponse,
    MeetListResponse,
    MeetPosterResponse,
    MeetPublicResponse,
    QuickMeetRequest,
)
from app.services.birthchart import (
    ZODIAC_KEYS,
    ZODIAC_NAMES_ZH,
    moon_sign,
    rising_sign,
    sun_sign,
)
from app.services.compatibility import compute_compatibility
from app.services.share import process_invite
from app.services.stardust import tier_for, tier_name
from app.services.wxacode import get_wxacode
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meet", tags=["星辰相遇"])

# 关系类型（设计 2.1：朋友/恋人/家人/同事）
RELATIONS = frozenset({"friend", "love", "family", "work"})


# ─────────────────────────────────────────────────────────────────────────────
# 相处提示模板库（≥10 条，开放积极向；全部合规——无 注定/天生一对 类措辞）
# ─────────────────────────────────────────────────────────────────────────────

MEET_TIPS: list[str] = [
    "你们的星光节奏是慢热的——先并肩走一段，再慢慢看清彼此的方向。",
    "给彼此留一点安静的空间，想念反而会自己长出来。",
    "有话慢慢说，把心里的小事讲出来，星光会替你传话。",
    "先做一对玩得来的朋友，很多答案会自己浮出水面。",
    "偶尔一起做点没做过的小事，默契往往在新鲜感里发芽。",
    "你们的相处像双人舞——有人进，就有人退，步调总会合上。",
    "把期待放低一点，把好奇放高一点，认识一个人是慢慢发生的事。",
    "分歧时先按下暂停，等星光安静下来再继续说话。",
    "你们各有各的光，不必为了同频而熄灭自己的那一盏。",
    "一起把日子过成小确幸的合集，比任何预言都可靠。",
    "慢一点也没关系，你们的星光喜欢按自己的节拍亮起来。",
    "试着把「我在乎你」说出口，温暖需要被听见才会回响。",
]

# 牌意截取长度（meaning_snippet：可解释，不落全文）
_SNIPPET_LEN = 50


# ─────────────────────────────────────────────────────────────────────────────
# 确定性三牌（seed 哈希驱动，与 pick_daily_card 同哲学）
# ─────────────────────────────────────────────────────────────────────────────


def pick_meet_cards(cards: list[TarotCard], seed_str: str) -> list[TarotCard]:
    """按 seed 从牌库确定性抽 3 张去重牌。

    同 seed（同日同人）恒同输出，无需落库；牌库不足 3 张时全量返回。
    """
    if len(cards) <= 3:
        return list(cards)
    picked: list[TarotCard] = []
    used_ids: set[int] = set()
    salt = 0
    while len(picked) < 3:
        digest = hashlib.sha256(f"{seed_str}:{salt}".encode("utf-8")).digest()
        idx = int.from_bytes(digest[:8], "big") % len(cards)
        card = cards[idx]
        if card.id not in used_ids:
            used_ids.add(card.id)
            picked.append(card)
        salt += 1
    return picked


def _hash_mod(text: str, mod: int) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big") % mod


def _meet_seed(a_birth_date: str, b_birth_date: str, day: date | None = None) -> str:
    """合盘牌阵 seed：f"{a 出生日期}|{b 出生日期}|{今天}"（同日同人恒定）。"""
    return f"{a_birth_date or ''}|{b_birth_date or ''}|{(day or date.today()).isoformat()}"


def _pick_tips(seed_str: str, n: int = 2) -> list[str]:
    """从 MEET_TIPS 池确定性轮选 n 条（去重：步长 ∈ [1, len-1]）。"""
    pool = len(MEET_TIPS)
    if pool <= n:
        return list(MEET_TIPS)
    start = _hash_mod(f"{seed_str}:tips", pool)
    step = 1 + _hash_mod(f"{seed_str}:tips:step", pool - 1)
    return [MEET_TIPS[(start + i * step) % pool] for i in range(n)]


def _snippet(text: str) -> str:
    """meaning_upright 截取：可解释的一句话，不落全文。"""
    text = (text or "").strip()
    if not text:
        return ""
    return text if len(text) <= _SNIPPET_LEN else text[:_SNIPPET_LEN] + "…"


async def _build_cards(db: AsyncSession, seed_str: str) -> tuple[list[dict], list[str]]:
    """合盘三牌：关系之牌 / 星光之牌（对方眼中的你）/ 相处之牌（相处提示合规框架）。"""
    result = await db.execute(select(TarotCard).order_by(TarotCard.id))
    cards = list(result.scalars().all())
    if len(cards) < 3:
        raise HTTPException(status_code=500, detail="卡牌数据为空")
    tips = _pick_tips(seed_str)
    rel, star, getalong = pick_meet_cards(cards, seed_str)
    return [
        {
            "position": "关系之牌",
            "card_id": rel.id,
            "name_zh": rel.name_zh,
            "meaning_snippet": _snippet(rel.meaning_upright),
            "tip": f"这段关系的星光之牌是「{rel.name_zh}」——{_snippet(rel.meaning_upright)}",
        },
        {
            "position": "星光之牌",
            "card_id": star.id,
            "name_zh": star.name_zh,
            "meaning_snippet": _snippet(star.meaning_upright),
            "tip": f"在对方眼中，你是「{star.name_zh}」——{_snippet(star.meaning_upright)}",
        },
        {
            "position": "相处之牌",
            "card_id": getalong.id,
            "name_zh": getalong.name_zh,
            "meaning_snippet": tips[0],
            "tip": tips[0],
        },
    ], tips


# ─────────────────────────────────────────────────────────────────────────────
# 入参/派生 helpers
# ─────────────────────────────────────────────────────────────────────────────

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")


def _parse_birth_date(value: str) -> tuple[int, int] | None:
    """YYYY-MM-DD（补零）→ (month, day)；非法返回 None。"""
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None
    return dt.month, dt.day


def _element(key: str) -> dict:
    """单要素响应：脏 key（非 12 星座）name_zh 兜底为 key 本身，不 KeyError。"""
    return {"zodiac": key, "name_zh": ZODIAC_NAMES_ZH.get(key, key)}


def _side(zodiac: str, moon: str | None, rising: str | None) -> dict:
    """一方三要素响应结构：sun 必有；moon/rising 缺要素为 None（前端标注估算）。"""
    return {
        "zodiac": zodiac,
        "name_zh": ZODIAC_NAMES_ZH.get(zodiac, zodiac),
        "sun": _element(zodiac),
        "moon": _element(moon) if moon else None,
        "rising": _element(rising) if rising else None,
    }


def _parse_meet_time(value: str | None) -> bool:
    """出生时间格式校验（HH:MM 或 HH:MM:SS）。"""
    return bool(value and _TIME_RE.match(value.strip()))


def _compute_safe(**kwargs) -> dict:
    """compute_compatibility 包装：星座 key 非法（脏数据）→ 400 而非 500。"""
    try:
        return compute_compatibility(**kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"星座数据无效：{exc}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /meet/quick — 快速合盘（只输对方星座，可选出生信息提升精确度）
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/quick", response_model=MeetDetailResponse)
async def quick_meet(
    payload: QuickMeetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """快速合盘：发起人三要素 + b 三要素 → 合盘 → 落库 → 完整结果。

    PII 最小化：落库只存派生星座 key，不存出生日期/时间明文。
    """
    if payload.relation not in RELATIONS:
        raise HTTPException(status_code=400, detail="关系类型无效，仅支持 friend/love/family/work")
    if payload.zodiac_b not in ZODIAC_KEYS:
        raise HTTPException(status_code=400, detail="星座参数无效，请使用 aries 等标准 key")
    if payload.b_birth_date is not None and _parse_birth_date(payload.b_birth_date) is None:
        raise HTTPException(status_code=400, detail="对方出生日期格式无效，应为 YYYY-MM-DD")
    if payload.b_birth_time and not _parse_meet_time(payload.b_birth_time):
        raise HTTPException(status_code=400, detail="对方出生时间格式无效，应为 HH:MM")
    if payload.b_birth_date is None and payload.b_birth_time:
        raise HTTPException(status_code=400, detail="对方出生时间需要配合出生日期一起填写")

    # ── 发起人三要素（users.zodiac + birthchart 派生）──
    a_sun = user.zodiac
    a_moon: str | None = None
    if user.birth_date:
        a_parts = _parse_birth_date(user.birth_date)
        if a_parts:
            a_sun = a_sun or sun_sign(a_parts[0], a_parts[1])
            a_moon = moon_sign(a_parts[0], a_parts[1], user.birth_time)[0]
    if not a_sun:
        raise HTTPException(status_code=400, detail="请先完善你的星座信息（设置星座或出生日期）")
    a_rising = rising_sign(a_sun, user.birth_time, user.birth_city)

    # ── b 三要素（b_birth_date → sun/moon；b_birth_time → rising）──
    b_sun = payload.zodiac_b
    b_moon: str | None = None
    b_rising: str | None = None
    if payload.b_birth_date is not None:
        b_parts = _parse_birth_date(payload.b_birth_date)
        b_sun = sun_sign(b_parts[0], b_parts[1])
        b_moon = moon_sign(b_parts[0], b_parts[1], payload.b_birth_time)[0]
    if payload.b_birth_time:
        b_rising = rising_sign(b_sun, payload.b_birth_time)
        if b_rising is None:
            raise HTTPException(status_code=400, detail="对方出生时间格式无效，应为 HH:MM")

    # ── 合盘（T2-1 三要素加权）──
    compat = _compute_safe(
        a_sun=a_sun, b_sun=b_sun,
        a_moon=a_moon, b_moon=b_moon,
        a_rising=a_rising, b_rising=b_rising,
    )

    # ── 确定性三牌 + 相处提示 ──
    seed_str = _meet_seed(user.birth_date or "", payload.b_birth_date or "")
    cards, tips = await _build_cards(db, seed_str)

    # ── 落库（PII 最小化：只存星座 key + 结果缓存）──
    meet_id = str(uuid.uuid4())
    result = {
        "score": compat["score"],
        "level_name": compat["level_name"],
        "factors": compat["factors"],
        "used": compat["used"],
        "estimated": compat["estimated"],
        "estimate_note": compat["estimate_note"],
        "cards": cards,
        "tips": tips,
    }
    db.add(
        StarMeeting(
            id=meet_id,
            initiator_id=user.id,
            relation=payload.relation,
            a_zodiac=a_sun, a_moon=a_moon, a_rising=a_rising,
            b_zodiac=b_sun, b_moon=b_moon, b_rising=b_rising,
            status="completed",
            result_json=json.dumps(result, ensure_ascii=False),
        )
    )
    await db.flush()

    return {
        "meet_id": meet_id,
        "relation": payload.relation,
        "a": _side(a_sun, a_moon, a_rising),
        "b": _side(b_sun, b_moon, b_rising),
        **result,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 归属校验（详情/海报共用）：仅 initiator 或 friend_user_id 可见
# ─────────────────────────────────────────────────────────────────────────────


def _check_access(row: StarMeeting, user_id: str) -> None:
    if not (row.initiator_id == user_id or (row.friend_user_id and row.friend_user_id == user_id)):
        # 404 而非 403：不泄露记录存在性
        raise HTTPException(status_code=404, detail="相遇记录不存在")


# ─────────────────────────────────────────────────────────────────────────────
# GET /meet/list — 我的相遇（发起或参与）
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/list", response_model=MeetListResponse)
async def list_meets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """我的相遇列表：本人发起（initiator_id）或参与（friend_user_id）的记录。"""
    result = await db.execute(
        select(StarMeeting)
        .where(or_(StarMeeting.initiator_id == user.id, StarMeeting.friend_user_id == user.id))
        .order_by(StarMeeting.created_at.desc(), StarMeeting.id.desc())
    )
    meetings = []
    for row in result.scalars().all():
        parsed = json.loads(row.result_json) if row.result_json else {}
        meetings.append(
            {
                "meet_id": row.id,
                "relation": row.relation,
                "b_name": ZODIAC_NAMES_ZH.get(row.b_zodiac, row.b_zodiac),
                "score": parsed.get("score"),
                "level_name": parsed.get("level_name"),
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
        )
    return {"meetings": meetings}


# ─────────────────────────────────────────────────────────────────────────────
# GET /meet/{meet_id} — 结果详情（读 result_json）
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{meet_id}", response_model=MeetDetailResponse)
async def get_meet(
    meet_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """相遇结果详情：完整结果（与 quick 返回同构）。

    防御性读取：result_json 为空或部分 JSON（T2-3 邀请行形态）时
    结果字段为空而非 KeyError 500——与同文件 list/poster 的 .get() 口径一致。
    """
    row = await db.get(StarMeeting, meet_id)
    if row is None:
        raise HTTPException(status_code=404, detail="相遇记录不存在")
    _check_access(row, user.id)
    result = json.loads(row.result_json) if row.result_json else {}
    return {
        "meet_id": row.id,
        "relation": row.relation,
        "a": _side(row.a_zodiac, row.a_moon, row.a_rising),
        "b": _side(row.b_zodiac, row.b_moon, row.b_rising),
        "score": result.get("score"),
        "level_name": result.get("level_name"),
        "factors": result.get("factors"),
        "cards": result.get("cards"),
        "tips": result.get("tips"),
        "estimated": result.get("estimated"),
        "estimate_note": result.get("estimate_note"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /meet/{meet_id}/poster — 脱敏海报数据
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{meet_id}/poster",
    response_model=MeetPosterResponse,
    response_model_exclude_none=True,
)
async def meet_poster(
    meet_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """脱敏海报数据：昵称/星座/score/level/牌面摘要/分享文案，无日记类原文。"""
    row = await db.get(StarMeeting, meet_id)
    if row is None:
        raise HTTPException(status_code=404, detail="相遇记录不存在")
    _check_access(row, user.id)
    result = json.loads(row.result_json) if row.result_json else {}
    score = result.get("score")
    initiator = await db.get(User, row.initiator_id)
    nickname = (initiator.nickname if initiator else None) or "一位星光旅人"
    return {
        "meet_id": row.id,
        "relation": row.relation,
        "a": {
            "zodiac": row.a_zodiac,
            "name_zh": ZODIAC_NAMES_ZH.get(row.a_zodiac, row.a_zodiac),
            "nickname": nickname,
        },
        "b": {
            "zodiac": row.b_zodiac,
            "name_zh": ZODIAC_NAMES_ZH.get(row.b_zodiac, row.b_zodiac),
        },
        "score": score,
        "level_name": result.get("level_name"),
        "cards": [
            {"position": c["position"], "name_zh": c["name_zh"]}
            for c in result.get("cards", [])
        ],
        "share_text": (
            f"我和TA的星辰共鸣度是 {score} · 看看你和谁星光相映 ✦"
            if score is not None
            else "我和TA的星光相遇了 · 看看你和谁星光相映 ✦"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# T2-3 邀请版：/meet/invite + /meet/public/{id} + /meet/join
# ─────────────────────────────────────────────────────────────────────────────
# 邀请小程序码缓存：按 meet_id 缓存 7 天（与 /share/wxacode 同款有界缓存，
# 最终审查 F-4：条目上限 _MEET_WXACODE_CACHE_MAX，超限逐出最旧；已过 TTL
# 的条目在每次写入时惰性清理——进程内存不会随 meet 数无限增长）。

_MEET_WXACODE_CACHE_TTL = 7 * 24 * 3600
_MEET_WXACODE_CACHE_MAX = 500
_meet_wxacode_cache: dict[str, tuple[float, bytes]] = {}


def _prune_meet_wxacode_cache(now: float) -> None:
    """惰性清理：删除已过 TTL（7 天）的缓存条目。"""
    for key in [k for k, (expires, _) in _meet_wxacode_cache.items() if expires <= now]:
        del _meet_wxacode_cache[key]


def _evict_meet_wxacode_cache() -> None:
    """条目数超上限时逐出最旧条目（dict 保持插入序，首键即最旧）。"""
    while len(_meet_wxacode_cache) > _MEET_WXACODE_CACHE_MAX:
        del _meet_wxacode_cache[next(iter(_meet_wxacode_cache))]


# ─────────────────────────────────────────────────────────────────────────────
# POST /meet/invite — 发起人邀请好友加入（meet → pending + 小程序码 PNG）
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/invite")
async def meet_invite(
    payload: MeetInviteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """邀请好友加入：meet → status=pending → 返回 meet-landing 小程序码 PNG。

    小程序码 scene=m:{meet_id}（好友扫码落到 meet-landing 页，凭 meet_id 查
    公开信息并加入）；按 meet_id 缓存 7 天，重复邀请命中缓存不再调微信接口。

    归属：仅发起人（非发起人 404 不泄露存在性）；好友已加入后再次邀请 → 400。
    """
    row = await db.get(StarMeeting, payload.meet_id)
    if row is None or row.initiator_id != user.id:
        raise HTTPException(status_code=404, detail="相遇记录不存在")
    if row.friend_user_id:
        raise HTTPException(status_code=400, detail="好友已加入，无需再次邀请")
    if row.status != "pending":
        row.status = "pending"  # 邀请中：好友 join 后回填并完成
        await db.flush()

    now = time.time()
    cached = _meet_wxacode_cache.get(row.id)
    if cached and cached[0] > now:
        return Response(content=cached[1], media_type="image/png")

    try:
        png_bytes = await get_wxacode(
            scene=f"m:{row.id}",
            page="pages/meet-landing/meet-landing",
            width=430,
            env_version="trial",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    _prune_meet_wxacode_cache(now)  # 惰性清理过期条目（F-4）
    _meet_wxacode_cache[row.id] = (now + _MEET_WXACODE_CACHE_TTL, png_bytes)
    _evict_meet_wxacode_cache()  # 超上限逐出最旧（F-4）
    return Response(content=png_bytes, media_type="image/png")


# ─────────────────────────────────────────────────────────────────────────────
# GET /meet/public/{meet_id} — 扫码落地页公开信息（脱敏 + 限流）
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/public/{meet_id}",
    response_model=MeetPublicResponse,
    dependencies=[Depends(meet_info_rate_limit)],
)
async def meet_public_info(
    meet_id: str,
    db: AsyncSession = Depends(get_db),
):
    """扫码落地页公开信息（无需登录）。

    仅返回 5 个已公开展示字段：meet_id / 发起人 nickname / 星座中文名 /
    星阶名称 / meet 状态。脱敏：无联系方式、无出生信息、无 invite_code。

    安全：公开且按可枚举输入（meet_id）确认记录存在 → 挂 30 次/分/IP 的
    meet_info_rate_limit（仿 /share/card-info），压低离线枚举。
    """
    row = await db.get(StarMeeting, meet_id)
    if row is None:
        raise HTTPException(status_code=404, detail="相遇记录不存在")
    initiator = await db.get(User, row.initiator_id)
    zodiac = initiator.zodiac if initiator else None
    tier = (
        initiator.star_tier
        if initiator and initiator.star_tier is not None
        else tier_for((initiator.stardust_total or 0) if initiator else 0)
    )
    return {
        "meet_id": row.id,
        "nickname": (initiator.nickname if initiator else None) or "一位星光旅人",
        "zodiac_cn": ZODIAC_NAMES_ZH.get(zodiac or "", zodiac or "未设置"),
        "star_tier_name": tier_name(tier),
        "status": row.status,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /meet/join — 好友加入：回填 b 三要素 + friend_user_id + 双向奖励
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/join", response_model=MeetJoinResponse)
async def meet_join(
    payload: MeetJoinRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """好友加入邀请版相遇：按好友的星座/出生信息重算合盘并回填落库。

    - 仅 status=pending（已邀请）的相遇可加入；发起人自己不能加入（同人防刷）；
      已完成（含重复加入/第三人）→ 400
    - 回填 b 三要素 + friend_user_id + status=completed + result_json（a 侧复用
      落库派生三要素；b 侧为好友真实信息，与 quick 同口径派生）
    - 并发安全（T2-3 审查修复）：认领走条件 UPDATE（WHERE status='pending'
      同语句翻转 status + 回填全部字段，rowcount==1 才放行）——两个并发 join
      只有一人成功，另一人 rowcount==0 → 幂等 400，杜绝"双读 pending 双双回填
      覆盖 + 双发奖励"。
    - 奖励：发起人有 invite_code 且为首次 pending→completed → process_invite
      （双方各 +1 免费解读）。幂等三保险：原子认领（首完成只发生一次）+
      process_invite 自身校验（invitee 唯一，已接受过不重复）+ 并发兜底
      （Invite.invitee_id 唯一约束冲突在 SAVEPOINT 内接住 → 幂等提示不 500）。
    """
    if payload.zodiac_b not in ZODIAC_KEYS:
        raise HTTPException(status_code=400, detail="星座参数无效，请使用 aries 等标准 key")
    if payload.b_birth_date is not None and _parse_birth_date(payload.b_birth_date) is None:
        raise HTTPException(status_code=400, detail="对方出生日期格式无效，应为 YYYY-MM-DD")
    if payload.b_birth_time and not _parse_meet_time(payload.b_birth_time):
        raise HTTPException(status_code=400, detail="对方出生时间格式无效，应为 HH:MM")
    if payload.b_birth_date is None and payload.b_birth_time:
        raise HTTPException(status_code=400, detail="对方出生时间需要配合出生日期一起填写")

    row = await db.get(StarMeeting, payload.meet_id)
    if row is None:
        raise HTTPException(status_code=404, detail="相遇记录不存在")
    if row.initiator_id == user.id:
        raise HTTPException(status_code=400, detail="不能加入自己的相遇")
    # 注意：不再做 row.status 的"读后写"预检查（T2-3 审查并发竞态——
    # 两个请求都读到 pending 会双双通过）。是否可加入由下方的
    # 条件 UPDATE（WHERE status='pending'）原子认领裁决。

    # ── b 三要素（与 quick 的 b 侧同口径）──
    b_sun = payload.zodiac_b
    b_moon: str | None = None
    b_rising: str | None = None
    if payload.b_birth_date is not None:
        b_parts = _parse_birth_date(payload.b_birth_date)
        b_sun = sun_sign(b_parts[0], b_parts[1])
        b_moon = moon_sign(b_parts[0], b_parts[1], payload.b_birth_time)[0]
    if payload.b_birth_time:
        b_rising = rising_sign(b_sun, payload.b_birth_time)
        if b_rising is None:
            raise HTTPException(status_code=400, detail="对方出生时间格式无效，应为 HH:MM")

    # ── 合盘（a 侧复用落库三要素；T2-1 三要素加权）──
    compat = _compute_safe(
        a_sun=row.a_zodiac, b_sun=b_sun,
        a_moon=row.a_moon, b_moon=b_moon,
        a_rising=row.a_rising, b_rising=b_rising,
    )

    # ── 确定性三牌（seed 与 quick 同口径：发起人生日|好友生日|今天）──
    initiator = await db.get(User, row.initiator_id)
    seed_str = _meet_seed(
        (initiator.birth_date if initiator else None) or "", payload.b_birth_date or ""
    )
    cards, tips = await _build_cards(db, seed_str)

    result = {
        "score": compat["score"],
        "level_name": compat["level_name"],
        "factors": compat["factors"],
        "used": compat["used"],
        "estimated": compat["estimated"],
        "estimate_note": compat["estimate_note"],
        "cards": cards,
        "tips": tips,
    }

    # ── 原子认领（T2-3 审查修复）：条件 UPDATE 同语句完成 status 翻转 + 全部
    #    回填（status 变化与 result 回填同一语句，WHERE status='pending' 裁决）：
    #    两个并发 join 只有一个 rowcount==1 放行；rowcount==0 视为已被占 →
    #    幂等 400。修复前"读后写"会让两个请求都读到 pending 双双回填（后写覆盖
    #    前写）+ 各自 process_invite → 发起人 +2 免费解读（应 +1）。──
    claim = await db.execute(
        update(StarMeeting)
        .where(StarMeeting.id == payload.meet_id, StarMeeting.status == "pending")
        .values(
            b_zodiac=b_sun,
            b_moon=b_moon,
            b_rising=b_rising,
            friend_user_id=user.id,
            status="completed",
            result_json=json.dumps(result, ensure_ascii=False),
        )
    )
    if claim.rowcount != 1:
        raise HTTPException(status_code=400, detail="该相遇未在邀请中或已完成")
    await db.refresh(row)  # ORM 行同步回填值（响应 a/b 侧读取）

    # ── 邀请奖励：发起人有 invite_code 且为首次完成（process_invite 自身幂等；
    #    并发兜底：同一好友并发 join 两个 meet → Invite.invitee_id 唯一约束冲突，
    #    在子事务（SAVEPOINT）内接住 → 幂等提示，不 500，也不回滚已认领的 meet）──
    reward_granted = False
    reward_note: str | None = None
    if initiator is not None and initiator.invite_code:
        try:
            async with db.begin_nested():  # 奖励子事务：冲突只回滚奖励，保留认领
                invite_result = await process_invite(
                    db, inviter_code=initiator.invite_code, invitee_user=user
                )
                await db.flush()  # 让 Invite 唯一约束在此浮出（而非 get_db commit 阶段 500）
            reward_granted = bool(invite_result.get("success", False))
            if not reward_granted:
                reward_note = invite_result.get("error")
        except IntegrityError:
            reward_granted = False
            reward_note = "你已经接受过邀请"

    return {
        "meet_id": row.id,
        "relation": row.relation,
        "a": _side(row.a_zodiac, row.a_moon, row.a_rising),
        "b": _side(row.b_zodiac, row.b_moon, row.b_rising),
        **result,
        "reward_granted": reward_granted,
        "reward_note": reward_note,
    }
