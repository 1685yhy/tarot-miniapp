"""星友圈（SDD P2）API — 星名 + 共鸣墙 + 送出/统计/隐身/海报。

- ``GET /resonance/alias``（T8-1）：返回当前用户脱敏星名（首次生成落库，
  此后恒定；确定性 + 幂等）。星友圈=零 UGC 共鸣墙，星名是唯一对外
  展示身份（真实昵称/头像永不外泄）。
- ``GET /resonance/wall``（T8-2）：共鸣墙实时聚合——今日活跃用户（脱敏
  星名）按 同星座 / 同星光数 / 同今日牌 三分组 + 「同星光的星」兜底组。
  公开免登录，独立限流（30 次/分/IP，与 meet 公开接口同策略）。
- T8-3 四端点（均鉴权）：
  ``POST /resonance/give`` 送出共鸣（幂等唯一约束 + 每日 10 次上限 +
  不产星尘，三重防刷）；``GET /resonance/stats`` 我的统计（角标数据源）；
  ``POST /resonance/visibility`` 隐身开关（关闭即时生效）；
  ``GET /resonance/poster`` 共鸣海报数据（全脱敏 + 固定文案过内容安全，
  T2-6 同款接线）。

T8-2 聚合设计：
- 墙零快照表：star_number 由 build_today_guidance（日期确定性）派生、
  今日牌由 pick_daily_card（用户+日期确定性）派生、星阶由 stardust 推导
  复用——全部与名片/每日一牌同源，同日同人恒定。
- 今日活跃 = 今日（北京时间日界）有 horoscope_history / diary / checkin /
  star_resonances 任一记录 且 resonance_visible=true 且 star_alias 已落库
  （星名是唯一对外身份，未生成星名者不上墙）——与 schemas 中
  today_active_criteria 纯函数同口径（SQL EXISTS 落实）。
- 三分组：zodiac（同星座，zodiac 未设置者不入该维）/ number（同星光数）/
  card（同今日牌）；组内共鸣数降序 + 日种子轮换头部防固化
  （``(day.toordinal() + group_idx) % len(members)`` 起点）+ 每组 Top 20。
- 兜底组：任何维度内不足 3 人的组，其成员合并进「同星光的星」兜底组
  （跨维合并去重；空则不显）；成员可同时出现在 ≥3 人组与兜底组。
- 脱敏：members 仅含系统生成字段 + 内部 uid（仅共鸣/海报用途），
  零 UGC、零可联系字段（测试键集断言钉住）。
"""

import logging
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.rate_limit import resonance_wall_rate_limit
from app.models.card import TarotCard
from app.models.checkin import CheckIn
from app.models.diary import DiaryEntry
from app.models.horoscope import HoroscopeHistory
from app.models.star_resonance import StarResonance
from app.models.user import User
from app.schemas.resonance import (
    AliasResponse,
    GiveRequest,
    GiveResponse,
    MyCard,
    PosterResponse,
    StatsResponse,
    VisibilityRequest,
    VisibilityResponse,
    WallCard,
    WallGroup,
    WallMember,
    WallResponse,
)
from app.services.compliance import find_forbidden
from app.services.daily_card import pick_daily_card
from app.services.energy_engine import ZODIAC_NAMES_ZH, build_today_guidance
from app.services.msg_check import msg_sec_check
from app.services.resonance import generate_alias, get_or_create_alias
from app.services.stardust import tier_for, tier_name
from app.services.star_words import beijing_today
from app.utils.auth import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resonance", tags=["今日星光共鸣"])

_WALL_GROUP_TOP = 20          # 每组最多展示人数
_WALL_MIN_GROUP = 3           # 组内不足 3 人 → 合并进兜底组
_WALL_FALLBACK_LABEL = "同星光的星"

# ── 共鸣送出防刷 / 海报固定文案（T8-3）────────────────────────────────────
_RESONANCE_DAILY_LIMIT = 10    # 每日送出上限（from_user 当日计数，超限 400）
_RESONANCE_CAPTION = "两颗星在同一片夜空相遇 ✦"
# 内容安全兜底句：静态无变量文案，恒过 compliance 双表扫描（测试钉住）
_RESONANCE_CAPTION_FALLBACK = "两颗星在这一刻同频 ✦"
_RESONANCE_DISCLAIMER = "仅供娱乐 · 星光映照"


@router.get("/alias", response_model=AliasResponse)
async def get_alias(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """脱敏星名：首次生成落库，此后恒定（同日同人同值，幂等）。"""
    alias = await get_or_create_alias(db, user)
    return AliasResponse(alias=alias)


@router.get(
    "/wall",
    response_model=WallResponse,
    dependencies=[Depends(resonance_wall_rate_limit)],
)
async def resonance_wall(
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """共鸣墙：今日活跃用户三分组实时聚合（公开免登录，独立限流）。

    响应零 UGC、零敏感字段；my_card 仅登录时返回本人卡片。
    """
    today = beijing_today()
    day_ordinal = today.toordinal()

    # ── 今日活跃可见用户（与 today_active_criteria 同口径，SQL EXISTS 落实）──
    # 仅 star_alias 已落库者上墙：星名是唯一对外展示身份，未生成者不可见。
    active_result = await db.execute(
        select(User).where(
            User.resonance_visible.is_(True),
            User.star_alias.isnot(None),
            or_(
                exists(select(HoroscopeHistory.id).where(
                    HoroscopeHistory.user_id == User.id,
                    HoroscopeHistory.date == today,
                )),
                exists(select(DiaryEntry.id).where(
                    DiaryEntry.user_id == User.id,
                    DiaryEntry.entry_date == today,
                )),
                exists(select(CheckIn.id).where(
                    CheckIn.user_id == User.id,
                    CheckIn.checkin_date == today,
                )),
                exists(select(StarResonance.id).where(
                    or_(
                        StarResonance.from_user_id == User.id,
                        StarResonance.to_user_id == User.id,
                    ),
                    StarResonance.resonate_date == today,
                )),
            ),
        )
    )
    active_users = active_result.scalars().all()

    # ── 今日每人收到共鸣数（to_user 聚合）──
    count_result = await db.execute(
        select(StarResonance.to_user_id, func.count(StarResonance.id))
        .where(StarResonance.resonate_date == today)
        .group_by(StarResonance.to_user_id)
    )
    received = {to_uid: n for to_uid, n in count_result.all()}

    # ── 我今日给出过的 uid 集合（resonated_by_me；未登录为空集）──
    given_to: set[str] = set()
    if user:
        given_result = await db.execute(
            select(StarResonance.to_user_id).where(
                StarResonance.from_user_id == user.id,
                StarResonance.resonate_date == today,
            )
        )
        given_to = {row[0] for row in given_result.all()}

    # ── 今日牌库（与 /cards/daily 同序：order by id，确定性同源）──
    card_result = await db.execute(select(TarotCard).order_by(TarotCard.id))
    cards = list(card_result.scalars().all())
    if not cards:
        raise HTTPException(status_code=500, detail="卡牌数据为空")

    def _tier_for(user: User) -> int:
        # star_tier 可空（历史数据），空时按星尘总量推导（与 share.py 同兜底）
        if user.star_tier is not None:
            return user.star_tier
        return tier_for(user.stardust_total or 0)

    def _member(user: User) -> WallMember:
        tier = _tier_for(user)
        card = pick_daily_card(cards, user.id, today)
        return WallMember(
            uid=user.id,
            alias=user.star_alias or generate_alias(user.id, today),
            zodiac=user.zodiac,
            star_number=build_today_guidance(today, user.zodiac)["star_number"],
            card=WallCard(card_id=card.id, name_zh=card.name_zh),
            tier=tier,
            tier_name=tier_name(tier),
            resonate_count=received.get(user.id, 0),
            resonated_by_me=user.id in given_to,
        )

    members = [_member(u) for u in active_users]

    # ── 三分组 + 兜底合并 ──────────────────────────────────────────────
    def _partition(key_fn) -> dict:
        groups: dict = defaultdict(list)
        for m in members:
            groups[key_fn(m)].append(m)
        return groups

    def _order(members_: list[WallMember], group_idx: int) -> list[WallMember]:
        """共鸣数降序（同数按 uid 稳定）+ 日种子轮换头部防固化 + Top 20。"""
        ordered = sorted(members_, key=lambda m: (-m.resonate_count, m.uid))
        start = (day_ordinal + group_idx) % len(ordered)
        return (ordered[start:] + ordered[:start])[:_WALL_GROUP_TOP]

    # (type, label, members) 有序列表；group_idx = 最终 groups 列表下标
    raw_groups: list[tuple[str, str, list[WallMember]]] = []

    # 同星座：zodiac 未设置的用户不入该维（无星座可同）
    zodiac_groups = _partition(lambda m: m.zodiac)
    for key in sorted(k for k in zodiac_groups if k is not None):
        ms = zodiac_groups[key]
        if len(ms) >= _WALL_MIN_GROUP:
            raw_groups.append(("zodiac", f"同星座的星光 · {ZODIAC_NAMES_ZH.get(key, key)}", ms))

    # 同星光数：build_today_guidance 日期确定性派生，同日全站同数
    number_groups = _partition(lambda m: m.star_number)
    for key in sorted(number_groups):
        ms = number_groups[key]
        if len(ms) >= _WALL_MIN_GROUP:
            raw_groups.append(("number", f"同星光数的星光 · {key}", ms))

    # 同今日牌：pick_daily_card 用户+日期确定性派生
    card_groups = _partition(lambda m: m.card.card_id)
    for key in sorted(card_groups):
        ms = card_groups[key]
        if len(ms) >= _WALL_MIN_GROUP:
            raw_groups.append(("card", f"同一张牌的星光 · {ms[0].card.name_zh}", ms))

    # 兜底：任何维度内不足 3 人的组成员合并进「同星光的星」（跨维去重，空则不显）
    fallback_pool: dict[str, WallMember] = {}
    for key, ms in zodiac_groups.items():
        if key is None:
            continue  # 未设置星座者不入「同星座」维度（无星座可同，也不经该维合并）
        if len(ms) < _WALL_MIN_GROUP:
            for m in ms:
                fallback_pool[m.uid] = m
    for key, ms in number_groups.items():
        if len(ms) < _WALL_MIN_GROUP:
            for m in ms:
                fallback_pool[m.uid] = m
    for key, ms in card_groups.items():
        if len(ms) < _WALL_MIN_GROUP:
            for m in ms:
                fallback_pool[m.uid] = m

    groups: list[WallGroup] = []
    for idx, (gtype, label, ms) in enumerate(raw_groups):
        groups.append(WallGroup(type=gtype, label=label, members=_order(ms, idx)))
    if fallback_pool:
        groups.append(
            WallGroup(
                type="fallback",
                label=_WALL_FALLBACK_LABEL,
                members=_order(list(fallback_pool.values()), len(groups)),
            )
        )

    # ── 我的今日卡片（登录才返回；隐身者仍可看自己的卡，本人数据不出墙）──
    my_card: MyCard | None = None
    if user:
        tier = _tier_for(user)
        card = pick_daily_card(cards, user.id, today)
        my_card = MyCard(
            alias=user.star_alias or generate_alias(user.id, today),
            zodiac=user.zodiac,
            star_number=build_today_guidance(today, user.zodiac)["star_number"],
            card=WallCard(card_id=card.id, name_zh=card.name_zh),
            tier_name=tier_name(tier),
            received_today=received.get(user.id, 0),
            # 本人隐身状态回读（前端进页用 my_card.visible 校准开关初值）
            visible=user.resonance_visible,
        )

    return WallResponse(active_count=len(members), groups=groups, my_card=my_card)


# ═════════════════════════════════════════════════════════════════════════
# T8-3：送出共鸣 / 统计 / 隐身开关 / 共鸣海报
# ═════════════════════════════════════════════════════════════════════════


@router.post("/give", response_model=GiveResponse)
async def give_resonance(
    body: GiveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """送出共鸣（三重防刷：幂等唯一约束 + 每日 10 次上限 + 不产星尘）。

    顺序：自给 400 → 目标不存在/已隐身 404 → 当日计数达上限 400 →
    插入（唯一约束冲突兜底幂等 409）。每日计数 = from_user 当日给出数
    （北京时间日界，与墙/统计同口径）。
    """
    if body.to_user_id == user.id:
        raise HTTPException(status_code=400, detail="不能给自己共鸣 ✦")

    target = await db.get(User, body.to_user_id)
    if target is None or not target.resonance_visible:
        raise HTTPException(status_code=404, detail="这颗星不在夜空中 ✦")

    today = beijing_today()
    today_count = (
        await db.execute(
            select(func.count(StarResonance.id)).where(
                StarResonance.from_user_id == user.id,
                StarResonance.resonate_date == today,
            )
        )
    ).scalar_one()
    if today_count >= _RESONANCE_DAILY_LIMIT:
        raise HTTPException(status_code=400, detail="今天已经送出 10 颗星，明天再来 ✦")

    db.add(StarResonance(
        from_user_id=user.id,
        to_user_id=body.to_user_id,
        resonate_date=today,
    ))
    try:
        await db.flush()
    except IntegrityError:  # 唯一约束兜底幂等：并发/重复 give → 已共鸣
        await db.rollback()
        raise HTTPException(status_code=409, detail="已共鸣过这颗星 ✦")

    return GiveResponse(ok=True, count_today=today_count + 1, limit=_RESONANCE_DAILY_LIMIT)


@router.get("/stats", response_model=StatsResponse)
async def resonance_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """我的共鸣统计（我的页角标数据源）：累计给出/收到 + 今日收到。

    given_total/received_total 为全历史累计（跨日累加）；received_today
    仅北京时间今日（日界复位）。只读聚合，不产生任何副作用。
    """
    today = beijing_today()
    given_total = (
        await db.execute(
            select(func.count(StarResonance.id)).where(StarResonance.from_user_id == user.id)
        )
    ).scalar_one()
    received_total = (
        await db.execute(
            select(func.count(StarResonance.id)).where(StarResonance.to_user_id == user.id)
        )
    ).scalar_one()
    received_today = (
        await db.execute(
            select(func.count(StarResonance.id)).where(
                StarResonance.to_user_id == user.id,
                StarResonance.resonate_date == today,
            )
        )
    ).scalar_one()
    return StatsResponse(
        given_total=given_total,
        received_total=received_total,
        received_today=received_today,
    )


@router.post("/visibility", response_model=VisibilityResponse)
async def set_resonance_visibility(
    body: VisibilityRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """隐身开关：写 users.resonance_visible，关闭即时生效（墙聚合实时过滤）。

    隐身仅影响对外展示（墙/海报目标校验）；本人仍可看墙、收共鸣、出统计。
    """
    user.resonance_visible = body.visible
    await db.flush()
    return VisibilityResponse(ok=True, visible=body.visible)


async def _safe_caption(text: str, openid: str | None) -> str:
    """海报固定文案内容安全（T8-3）：find_forbidden + msg_sec_check 命中 → 兜底句。

    与 T2-6 合盘海报同款接线：
    - 本地禁词表（compliance 共享表）命中 → 替换为静态兜底句 + 记日志；
    - msg_sec_check 命中风险（本地禁词或微信 risky/review）→ 同上兜底；
    - 接口异常 → try/except 不阻塞，返回原文（fail-open，与 community 同口径）。
    """
    hits = find_forbidden(text)
    if hits:
        logger.warning("Resonance caption flagged by local blacklist %s, fallback", hits)
        return _RESONANCE_CAPTION_FALLBACK
    try:
        check = await msg_sec_check(text, openid)
    except Exception as exc:  # 防御：微信接口/网络异常不阻塞海报
        logger.warning("Resonance caption msg check raised (fail-open): %s", exc)
        return text
    if not check["safe"]:
        logger.warning(
            "Resonance caption flagged by msg check, fallback: %s", check.get("err")
        )
        return _RESONANCE_CAPTION_FALLBACK
    return text


def _poster_alias(user: User, today: date) -> str:
    """海报星名：已落库原值，未落库按确定性公式派生（与墙同源，零副作用）。"""
    return user.star_alias or generate_alias(user.id, today)


def _poster_tier(user: User) -> int:
    """星阶索引：star_tier 可空（历史数据），空时按星尘总量推导（与墙同兜底）。"""
    if user.star_tier is not None:
        return user.star_tier
    return tier_for(user.stardust_total or 0)


@router.get("/poster", response_model=PosterResponse)
async def resonance_poster(
    to_user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """共鸣海报数据：双方脱敏字段 + 共鸣维度 + 固定文案（零 UGC）。

    目标不存在或已隐身 → 404（隐身即不出现在任何对外展示，与 give 同口径）。
    dimension：双方同星座 → zodiac；同今日牌 → card；否则 → number
    （同日全站星光数相同，恒真兜底，字段必有值）。
    caption 过 find_forbidden + msg_sec_check，命中 → 安全兜底句，不阻塞出图。
    """
    target = await db.get(User, to_user_id)
    if target is None or not target.resonance_visible:
        raise HTTPException(status_code=404, detail="这颗星不在夜空中 ✦")

    today = beijing_today()
    card_result = await db.execute(select(TarotCard).order_by(TarotCard.id))
    cards = list(card_result.scalars().all())
    if not cards:
        raise HTTPException(status_code=500, detail="卡牌数据为空")

    card_a = pick_daily_card(cards, user.id, today)
    card_b = pick_daily_card(cards, target.id, today)
    if user.zodiac and user.zodiac == target.zodiac:
        dimension = "zodiac"
    elif card_a.id == card_b.id:
        dimension = "card"
    else:
        dimension = "number"

    return PosterResponse(
        alias_a=_poster_alias(user, today),
        alias_b=_poster_alias(target, today),
        zodiac_a=user.zodiac,
        zodiac_b=target.zodiac,
        star_number_a=build_today_guidance(today, user.zodiac)["star_number"],
        star_number_b=build_today_guidance(today, target.zodiac)["star_number"],
        card_a=WallCard(card_id=card_a.id, name_zh=card_a.name_zh),
        card_b=WallCard(card_id=card_b.id, name_zh=card_b.name_zh),
        tier_name_a=tier_name(_poster_tier(user)),
        tier_name_b=tier_name(_poster_tier(target)),
        dimension=dimension,
        caption=await _safe_caption(_RESONANCE_CAPTION, user.openid),
        disclaimer=_RESONANCE_DISCLAIMER,
    )
