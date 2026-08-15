"""
Tarot reading API endpoints.

- POST   /readings/spread/{spread_type}   – create a new reading
- GET    /readings/{reading_id}           – retrieve a single reading
- GET    /readings/history                – list the current user's readings
- DELETE /readings/history                – delete the current user's reading history
"""

import json
import re
import uuid as uuid_lib
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.diary import MOOD_LABEL_MAP
from app.config import settings
from app.db.database import get_db
from app.models.card import TarotCard
from app.models.card_teaching import CardTeaching
from app.models.diary import DiaryEntry
from app.models.reading import ChatMessage, DrawnCard, Reading
from app.models.user import User
from app.schemas.reading import (
    ActionItem,
    ChatMessageResponse,
    CreateReadingRequest,
    DeepSection,
    DrawnCardResponse,
    ReadingHistoryItem,
    ReadingHistoryResponse,
    ReadingResponse,
)
from app.services.ai_engine import (
    generate_reading,
    generate_reflection_question,
    parse_deep_sections,
    _build_user_context,
)
from app.services.ai_personas import get_persona
from app.services.tarot import draw_cards
from app.utils.auth import get_current_user
from app.utils.quota import reset_ai_quota_if_new_day

router = APIRouter(prefix="/readings", tags=["占卜解读"])


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _today() -> datetime:
    """Return the start-of-day (midnight) for the current UTC date (naive, matching DB storage)."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day)


async def _reset_daily_count_if_new_day(user: User) -> None:
    """
    If the user hasn't done a reading ''today'', reset their daily counters.

    The field ``last_reading_date`` stores the timestamp of the *last*
    reading; we compare its date part against today.
    """
    if user.last_reading_date is None:
        return
    # Compare only the date portion
    last = user.last_reading_date.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if last < _today():
        user.free_readings_today = 0
        user.free_chats_today = 0


async def _load_card_info(db: AsyncSession, card_id: int) -> TarotCard | None:
    result = await db.execute(select(TarotCard).where(TarotCard.id == card_id))
    return result.scalar_one_or_none()


async def _load_card_name(db: AsyncSession, card_id: int) -> str | None:
    card = await _load_card_info(db, card_id)
    return card.name_zh if card else None


# ── Action item parsing ──────────────────────────────────────────────


_LOVE_KEYWORDS = [
    "爱", "恋爱", "伴侣", "约会", "感情", "浪漫", "爱情",
    "关系", "结婚", "表白", "心动", "亲密", "对象",
    "牵手", "拥抱", "相处", "信任", "婚姻",
    "恋人", "告白", "交往", "约会",
]

_CAREER_KEYWORDS = [
    "工作", "事业", "职业", "晋升", "同事", "团队", "项目",
    "创业", "投资", "简历", "面试", "学习", "成长", "技能",
    "职场", "办公", "会议", "客户", "业务", "计划", "目标",
    "专业", "进修", "课程", "读书", "绩效", "求职", "跳槽",
    "副业", "创业",
]

_SPREAD_TYPE_NAMES = {
    "three_card": "三牌占卜",
    "triangle": "恋人三角",
    "decision": "二择一",
    "celtic_cross": "凯尔特十字",
    "career": "事业牌阵",
    "finance": "财运牌阵",
    "life_cross": "人生十字",
    "horseshoe": "马蹄牌阵",
    "relationship": "关系牌阵",
    "year_ahead": "年度运势",
}

# P1-6: spreads that were premium-only in the UI — now enforced server-side.
PREMIUM_SPREADS = {"celtic_cross", "horseshoe", "relationship", "year_ahead"}


# Diary focus-point keyword categories — used to distil *what* the user
# is preoccupied with from diary reflections WITHOUT quoting any content.
_DIARY_FOCUS_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("工作", ("工作", "事业", "职业", "同事", "项目", "老板", "面试", "升职", "跳槽", "加班", "绩效", "客户", "领导", "上班", "会议", "方案", "任务")),
    ("感情", ("恋爱", "伴侣", "约会", "感情", "关系", "结婚", "表白", "分手", "对象", "喜欢", "爱情", "牵手", "暧昧")),
    ("金钱", ("钱", "财务", "理财", "收入", "存款", "账单", "投资", "省钱", "消费", "房租", "工资", "负债", "预算")),
    ("学习成长", ("学习", "考试", "读书", "课程", "成长", "进步", "考研", "毕业", "论文", "技能", "复盘")),
    ("健康", ("健康", "生病", "失眠", "身体", "体检", "疲惫", "累")),
    ("人际", ("朋友", "家人", "父母", "家庭", "闺蜜", "兄弟", "室友", "社交")),
    ("人生方向", ("迷茫", "方向", "未来", "人生", "意义", "自我", "选择", "决定", "犹豫", "坚持", "勇气")),
)


def _distil_diary_focus(entries: list) -> list[str]:
    """Extract the user's recent focus topics from diary reflections.

    Keyword-matches each reflection and returns the top 3 topic labels
    (e.g. 工作 / 感情 / 学习成长). Never returns original text — the
    AI may sense the user's concerns but must not quote the diary.
    """
    hits: Counter[str] = Counter()
    for e in entries:
        content = (e.reflection or "").strip()
        if not content:
            continue
        for label, keywords in _DIARY_FOCUS_KEYWORDS:
            if any(kw in content for kw in keywords):
                hits[label] += 1
    return [label for label, _ in hits.most_common(3)]


async def _build_diary_context_block(
    db: AsyncSession, user_id: str,
) -> str:
    """Query the user's diary entries from the last 7 days (including today)
    and distil them into a *state-awareness* block for the AI.

    The block contains only aggregated state — mood tendency + focus
    topics — NEVER diary content. The AI uses it to adjust tone and angle
    of the reading, but must not mention/quote the diary in its reply
    (enforced by the 【输出红线】 instruction in the prompt).

    Privacy boundary: only the last-7-day window is read, max 5 entries,
    and raw content never enters logs — only distilled labels are injected
    into the AI prompt.

    Returns an empty string when there is nothing to inject.
    """
    today = date.today()
    week_ago = today - timedelta(days=7)
    result = await db.execute(
        select(DiaryEntry)
        .where(
            DiaryEntry.user_id == user_id,
            DiaryEntry.entry_date >= week_ago,
        )
        .order_by(DiaryEntry.entry_date.desc(), DiaryEntry.created_at.desc())
        .limit(5)
    )
    entries: list[DiaryEntry] = list(result.scalars().all())
    if not entries:
        return ""

    # ── Mood tendency: most frequent mood keys → CN labels (top 3) ──
    mood_counter: Counter[str] = Counter(
        (e.mood or "thoughtful") for e in entries
    )
    mood_labels = [
        MOOD_LABEL_MAP.get(key, key) for key, _ in mood_counter.most_common(3)
    ]

    # ── Focus topics: theme keywords distilled from reflections ──
    focus_labels = _distil_diary_focus(entries)

    lines = ["\n【用户近况（最近7天状态感知，仅用于调整语气，严禁在回复中提及）】"]
    if mood_labels:
        lines.append(f"· 用户近期情绪倾向：{'/'.join(mood_labels)}")
    if focus_labels:
        lines.append(f"· 用户近期关注点：{'/'.join(focus_labels)}")
    if len(lines) == 1:
        return ""  # nothing distilled — omit the block entirely
    lines.append("")
    return "\n".join(lines)


async def _build_user_context_block(
    db: AsyncSession, user_id: str,
) -> str:
    """Query the user's reading history + recent diary and build a context
    block for the AI.

    Returns an empty string if the user has neither history nor recent diary.
    """
    from collections import Counter

    # ── Reading-history context ──
    # Fetch all readings for this user (capped at 200 for performance)
    result = await db.execute(
        select(Reading)
        .where(Reading.user_id == user_id)
        .order_by(Reading.created_at.desc())
        .limit(200)
    )
    readings: list[Reading] = list(result.scalars().all())

    readings_context = ""
    if readings:
        total_count = len(readings)

        # Most common spread type
        spread_counter: Counter[str] = Counter(r.spread_type for r in readings)
        common_spread = spread_counter.most_common(1)[0][0] if spread_counter else None

        # Most common theme (excluding None/general)
        theme_counter: Counter[str] = Counter(
            r.theme for r in readings if r.theme and r.theme != "general"
        )
        common_theme = theme_counter.most_common(1)[0][0] if theme_counter else None

        # Streak: consecutive days from the most recent reading date backwards
        unique_dates = sorted(
            set(r.created_at.date() for r in readings if r.created_at), reverse=True
        )
        streak = 0
        if unique_dates:
            from datetime import timedelta, timezone
            last_date = unique_dates[0]
            today = datetime.now(timezone.utc).date()
            # If the most recent reading is not today or yesterday, streak = 0
            if (today - last_date).days <= 1:
                check = last_date
                for d in unique_dates:
                    if d == check:
                        streak += 1
                        check -= timedelta(days=1)
                    else:
                        break

        # Last 3 reading summaries (question text, or fallback to spread type)
        last_3_root = readings[:3]
        last_3_summaries: list[str] = []
        for r in last_3_root:
            summary = r.question or _SPREAD_TYPE_NAMES.get(r.spread_type, r.spread_type)
            last_3_summaries.append(summary[:60])

        readings_context = _build_user_context(
            total_count=total_count,
            common_spread=common_spread,
            common_theme=common_theme,
            streak=streak,
            last_3_summaries=last_3_summaries,
        )

    # ── Recent diary state-awareness context (last 7 days, incl. today) ──
    diary_context = await _build_diary_context_block(db, user_id)

    parts = [p for p in (readings_context, diary_context) if p and p.strip()]
    if not parts:
        return ""
    return "\n".join(parts)


def _categorize_action(content: str) -> str:
    """Determine action category (love / career / general) by keyword matching."""
    for kw in _LOVE_KEYWORDS:
        if kw in content:
            return "love"
    for kw in _CAREER_KEYWORDS:
        if kw in content:
            return "career"
    return "general"


def parse_action_items(text: str | None) -> list[dict]:
    """Extract [ACTION]...[/ACTION] tags from AI response into structured items.

    Returns a list of dicts with keys: id, content, category.
    Returns an empty list if no action items are found.
    """
    if not text:
        return []

    pattern = r'\[ACTION\](.*?)\[/ACTION\]'
    matches = re.findall(pattern, text, re.DOTALL)

    items: list[dict] = []
    for match in matches:
        content = match.strip()
        if not content:
            continue
        items.append({
            "id": str(uuid_lib.uuid4()),
            "content": content,
            "category": _categorize_action(content),
        })
    return items


def _build_fortune_mood(
    major_count: int, minor_count: int, suit_dist: dict[str, int]
) -> str:
    """牌运一句话总结 — 纯规则式（3-4 条规则，不调 AI）。

    - 无解读记录 → 星光初启
    - 大阿卡那出现次数多于小阿卡那 → 转折之年
    - 花色分布决定行动/情绪/思虑/稳健
    """
    if major_count + minor_count == 0:
        return "星光初启，牌运之旅待你开启"
    if major_count > minor_count:
        return "转折之年 · 大牌主导，人生迎来关键变化"
    top_suit, top_count = max(suit_dist.items(), key=lambda kv: kv[1])
    if top_count == 0:
        return "牌运平稳，随心而行"
    if top_suit == "wands":
        return "行动力强 · 宜主动出击"
    if top_suit == "cups":
        return "情绪丰沛 · 倾听内心声音"
    if top_suit == "swords":
        return "思虑渐明 · 拨云见日"
    return "稳步向前 · 厚积薄发"


async def _load_drawn_cards_response(
    db: AsyncSession, drawn_cards: list[DrawnCard]
) -> list[dict]:
    """Build the ``DrawnCardResponse``-compatible dict list for a reading."""
    resp = []
    card_ids = [dc.card_id for dc in drawn_cards]

    # Batch-load card rows in one query (avoid N+1 per card)
    cards_by_id: dict[int, TarotCard] = {}
    if card_ids:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id.in_(card_ids))
        )
        cards_by_id = {card.id: card for card in card_result.scalars().all()}

    # Batch-load teaching info
    teaching_info: dict[int, dict] = {}
    if card_ids:
        t_result = await db.execute(
            select(CardTeaching).where(CardTeaching.card_id.in_(card_ids))
        )
        for teaching_row in t_result.scalars().all():
            teaching_info[teaching_row.card_id] = {
                "symbols": json.loads(teaching_row.symbols),
                "life_connection": teaching_row.life_connection,
            }

    for dc in drawn_cards:
        card = cards_by_id.get(dc.card_id)
        entry = {
            "id": dc.id,
            "card_id": dc.card_id,
            "card_name": card.name_zh if card else f"卡牌#{dc.card_id}",
            "name_en": card.name_en if card else "",
            "arcana": card.arcana if card else "",
            "suit": card.suit if card else None,
            "card_number": card.card_number if card else 0,
            "position": dc.position,
            "position_name": dc.position_name,
            "is_reversed": dc.is_reversed,
        }
        # Attach teaching if available
        if dc.card_id in teaching_info:
            entry["teaching"] = teaching_info[dc.card_id]
        resp.append(entry)
    return resp


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------


@router.post("/spread/{spread_type}", response_model=ReadingResponse)
async def create_reading(
    spread_type: str,
    req: CreateReadingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Draw cards, create a reading record, and generate an AI interpretation.

    Free-tier users are limited to ``FREE_DAILY_READINGS`` per day.
    Members have unlimited usage.
    """
    # ── Reset daily counters if last reading was on a previous day ──
    await _reset_daily_count_if_new_day(user)

    # ── Free-tier limit check ──
    if user.is_member and user.member_expires_at:
        expires = user.member_expires_at
        # SQLite returns naive datetimes; normalize to aware UTC before comparing
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            user.is_member = False
    uses_paid_credit = False
    if not user.is_member and user.free_readings_today >= settings.FREE_DAILY_READINGS:
        # Check if user has paid reading credits
        if user.paid_readings_balance and user.paid_readings_balance > 0:
            uses_paid_credit = True
        else:
            raise HTTPException(
                status_code=402,
                detail="今日免费次数已用完，请开通会员",
            )

    # ── Premium spread gate (P1-6): previously UI-only, now enforced here ──
    if spread_type in PREMIUM_SPREADS and not user.is_member:
        raise HTTPException(
            status_code=402,
            detail="该牌阵为会员专属，请先开通会员",
        )

    # ── Draw cards ──
    cards_data = draw_cards(spread_type)

    # ── Resolve persona ──
    persona_key = req.persona or None
    if persona_key:
        # Validate against registry
        _ = get_persona(persona_key)

    # ── Resolve depth level ──
    # basic:   TL;DR only (~200 chars) — free
    # standard: Full interpretation (current) — free
    # deep:    Full + extra depth analysis — member only, or non-members
    #          who pay with paid_readings_balance / free_deep_readings
    #          (P0-2: paid deep readings must actually deliver deep).
    reading_depth = req.depth or "standard"
    deep_uses_free = False
    deep_uses_paid = False
    if reading_depth == "deep" and not user.is_member:
        if (user.free_deep_readings or 0) > 0:
            deep_uses_free = True
        elif (user.paid_readings_balance or 0) > (1 if uses_paid_credit else 0):
            # Requires one spare unit on top of the credit this reading
            # already consumes for the daily quota (never overdraft).
            deep_uses_paid = True
        else:
            reading_depth = "standard"

    # ── Create reading record ──
    reading = Reading(
        user_id=user.id,
        spread_type=spread_type,
        question=req.question,
        theme=req.theme,
        persona=persona_key,
        depth=reading_depth,
        is_paid=user.is_member or uses_paid_credit or deep_uses_free or deep_uses_paid,
    )
    db.add(reading)
    await db.flush()

    # ── Save DrawnCard rows & collect enriched info for AI ──
    # Batch-load all drawn cards in a single query (avoid N+1 per card).
    card_ids = [c["card_id"] for c in cards_data]
    cards_by_id: dict[int, TarotCard] = {}
    if card_ids:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id.in_(card_ids))
        )
        cards_by_id = {card.id: card for card in card_result.scalars().all()}

    cards_info: list[dict] = []
    for c in cards_data:
        card = cards_by_id.get(c["card_id"])
        if card is None:
            continue  # should never happen with valid IDs

        drawn = DrawnCard(
            reading_id=reading.id,
            card_id=c["card_id"],
            position=c["position"],
            position_name=c["position_name"],
            is_reversed=c["is_reversed"],
        )
        db.add(drawn)

        cards_info.append(
            {
                **c,
                "name_zh": card.name_zh,
                "name_en": card.name_en,
                "arcana": card.arcana,
                "suit": card.suit,
                "card_number": card.card_number,
                "image_description": card.image_description,
                "meaning_upright": card.meaning_upright,
                "meaning_reversed": card.meaning_reversed,
                "love_upright": card.love_upright,
                "love_reversed": card.love_reversed,
                "career_upright": card.career_upright,
                "career_reversed": card.career_reversed,
                "finance_upright": card.finance_upright,
                "finance_reversed": card.finance_reversed,
            }
        )

    # ── Fetch teaching data for the drawn cards ──
    teaching_info: dict[int, dict] = {}
    if card_ids:
        t_result = await db.execute(
            select(CardTeaching).where(CardTeaching.card_id.in_(card_ids))
        )
        for teaching_row in t_result.scalars().all():
            teaching_info[teaching_row.card_id] = {
                "symbols": json.loads(teaching_row.symbols),
                "story": teaching_row.story,
                "keywords_learning": json.loads(teaching_row.keywords_learning),
                "life_connection": teaching_row.life_connection,
                "element_association": teaching_row.element_association,
            }

    # ── Build user context block (async DB query) ──
    user_context = await _build_user_context_block(db, user.id)

    # ── Generate AI interpretation ──
    interpretation = await generate_reading(
        spread_type, req.question, req.theme, cards_info,
        teaching_info=teaching_info,
        persona=persona_key,
        user_context=user_context,
        zodiac_sign=req.zodiac,
        depth=reading_depth,
    )
    action_items: list[dict] = []
    deep_sections: list[dict] = []
    if interpretation is not None:
        reading.interpretation = interpretation
        action_items = parse_action_items(interpretation)
        # 深度解读：AI 输出按固定六段结构解析为结构化分区（付费价值核心）
        if reading_depth == "deep":
            deep_sections = parse_deep_sections(interpretation)

    # ── Deduct balances only after successful AI generation ──
    if uses_paid_credit:
        user.paid_readings_balance -= 1
    # P0-2: consume the deep-reading balance (free_deep_readings first,
    # then paid_readings_balance) — this is where share-rewarded
    # free_deep_readings finally get spent.
    if deep_uses_free:
        user.free_deep_readings -= 1
    if deep_uses_paid:
        user.paid_readings_balance -= 1

    # ── Apply depth tier truncation ──
    if reading_depth == "basic" and interpretation:
        truncation_note = "\n\n[注：此为免费简要解读。完整解读请升级为标准或深度模式。]"
        interpretation = interpretation[:200] + truncation_note
        reading.interpretation = interpretation

    # ── Generate reflection question ──
    reflection_question = None
    if cards_info and interpretation:
        first_card_name = cards_info[0].get("name_zh", "")
        reflection_question = await generate_reflection_question(
            req.question, first_card_name, interpretation,
        )
    reading.reflection_question = reflection_question

    # ── Update user state ──
    if not user.is_member:
        user.free_readings_today += 1
    user.last_reading_date = datetime.now(timezone.utc)

    # ── Flush so the drawn_cards relationship is populated ──
    await db.flush()
    await db.refresh(reading, ["drawn_cards"])

    # ── Build response (reuse cards already loaded above — no extra queries) ──
    drawn_resp = []
    for dc in reading.drawn_cards:
        card = cards_by_id.get(dc.card_id)
        entry = {
            "id": dc.id,
            "card_id": dc.card_id,
            "card_name": card.name_zh if card else f"卡牌#{dc.card_id}",
            "name_en": card.name_en if card else "",
            "arcana": card.arcana if card else "",
            "suit": card.suit if card else None,
            "card_number": card.card_number if card else 0,
            "position": dc.position,
            "position_name": dc.position_name,
            "is_reversed": dc.is_reversed,
        }
        # Attach teaching if available
        if dc.card_id in teaching_info:
            entry["teaching"] = {
                "symbols": teaching_info[dc.card_id]["symbols"],
                "life_connection": teaching_info[dc.card_id]["life_connection"],
            }
        drawn_resp.append(entry)

    return ReadingResponse(
        id=reading.id,
        spread_type=reading.spread_type,
        question=reading.question,
        theme=reading.theme,
        persona=reading.persona,
        interpretation=reading.interpretation,
        is_paid=reading.is_paid,
        created_at=reading.created_at,
        drawn_cards=[DrawnCardResponse(**d) for d in drawn_resp],
        action_items=[ActionItem(**a) for a in action_items],
        reflection_question=reflection_question,
        depth=reading_depth,
        deep_sections=[DeepSection(**s) for s in deep_sections],
    )


@router.get("/history", response_model=ReadingHistoryResponse)
async def list_readings(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's reading history, newest first."""
    # Total count
    count_result = await db.execute(
        select(func.count(Reading.id)).where(Reading.user_id == user.id)
    )
    total = count_result.scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Reading)
        .where(Reading.user_id == user.id)
        .options(selectinload(Reading.drawn_cards))
        .order_by(Reading.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    readings: list[Reading] = result.scalars().all()

    items: list[ReadingHistoryItem] = []
    for r in readings:
        first_card_name = None
        first_card_reversed = None
        if r.drawn_cards:
            fcard = r.drawn_cards[0]
            first_card_name = await _load_card_name(db, fcard.card_id)
            first_card_reversed = fcard.is_reversed

        items.append(
            ReadingHistoryItem(
                id=r.id,
                spread_type=r.spread_type,
                question=r.question,
                theme=r.theme,
                persona=r.persona,
                interpretation=r.interpretation,
                is_paid=r.is_paid,
                created_at=r.created_at,
                first_card_name=first_card_name,
                first_card_is_reversed=first_card_reversed,
                depth=r.depth or "standard",
                reflection_question=r.reflection_question,
            )
        )

    return ReadingHistoryResponse(total=total, items=items)


# -------------------------------------------------------------------
# 牌运曲线 — 个人数据资产（近 N 天解读聚合）
# -------------------------------------------------------------------


@router.get("/fortune-trend")
async def fortune_trend(
    days: int = Query(30, ge=1, le=90, description="统计天数"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """牌运曲线：聚合当前用户近 N 天解读记录。

    Response
    --------
    {
      "days": 30,
      "total_readings": 12,
      "cards": [{"name", "name_en", "count"}],       // 高频牌 top5（按抽出次数）
      "arcana_dist": {"major": 4, "minor": 8},        // 大/小阿卡那分布
      "suit_dist": {"wands", "cups", "swords", "pentacles"},
      "mood": "稳步向前 · 厚积薄发",                  // 规则式一句话总结
      "trend": [{"date": "2026-08-01", "count": 1}]   // 每日解读次数（满 N 天补零）
    }
    """
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=days - 1)
    cutoff_dt = datetime(cutoff.year, cutoff.month, cutoff.day)

    # ── 窗口内解读记录（含抽牌明细）──
    result = await db.execute(
        select(Reading)
        .where(Reading.user_id == user.id, Reading.created_at >= cutoff_dt)
        .options(selectinload(Reading.drawn_cards))
        .order_by(Reading.created_at.asc())
    )
    readings: list[Reading] = list(result.scalars().all())
    total_readings = len(readings)

    # ── 聚合抽出的牌 ──
    card_counter: Counter[int] = Counter()
    arcana_dist = {"major": 0, "minor": 0}
    suit_dist = {"wands": 0, "cups": 0, "swords": 0, "pentacles": 0}
    for r in readings:
        for dc in r.drawn_cards:
            card_counter[dc.card_id] += 1

    top_cards: list[dict] = []
    if card_counter:
        top_ids = [cid for cid, _ in card_counter.most_common(5)]
        card_result = await db.execute(select(TarotCard).where(TarotCard.id.in_(top_ids)))
        cards_by_id = {c.id: c for c in card_result.scalars().all()}
        for cid, count in card_counter.most_common(5):
            card = cards_by_id.get(cid)
            if not card:
                continue
            top_cards.append({"name": card.name_zh, "name_en": card.name_en, "count": count})
            arcana_dist[card.arcana] = arcana_dist.get(card.arcana, 0) + count
            if card.suit in suit_dist:
                suit_dist[card.suit] += count

    # ── 每日解读次数（满 N 天，无记录的天补 0）──
    daily_counts: dict[str, int] = {}
    for r in readings:
        if r.created_at:
            key = r.created_at.date().isoformat()
            daily_counts[key] = daily_counts.get(key, 0) + 1
    trend = [
        {"date": (today - timedelta(days=i)).isoformat(), "count": daily_counts.get((today - timedelta(days=i)).isoformat(), 0)}
        for i in range(days - 1, -1, -1)
    ]

    return {
        "days": days,
        "total_readings": total_readings,
        "cards": top_cards,
        "arcana_dist": arcana_dist,
        "suit_dist": suit_dist,
        "mood": _build_fortune_mood(arcana_dist["major"], arcana_dist["minor"], suit_dist),
        "trend": trend,
    }


@router.get("/{reading_id}", response_model=ReadingResponse)
async def get_reading(
    reading_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single reading by its ID (must belong to the current user)."""
    result = await db.execute(
        select(Reading)
        .where(Reading.id == reading_id)
        .options(selectinload(Reading.drawn_cards), selectinload(Reading.chat_messages))
    )
    reading = result.scalar_one_or_none()

    if reading is None:
        raise HTTPException(status_code=404, detail="解读不存在")
    if reading.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看他人的解读")

    drawn_resp = await _load_drawn_cards_response(db, reading.drawn_cards)
    action_items = parse_action_items(reading.interpretation)
    reading_depth = reading.depth or "standard"
    # 深度解读：从存储的解读文本解析结构化分区（与创建时同源同构）
    deep_sections = parse_deep_sections(reading.interpretation) if reading_depth == "deep" else []

    return ReadingResponse(
        id=reading.id,
        spread_type=reading.spread_type,
        question=reading.question,
        theme=reading.theme,
        persona=reading.persona,
        interpretation=reading.interpretation,
        is_paid=reading.is_paid,
        created_at=reading.created_at,
        drawn_cards=[DrawnCardResponse(**d) for d in drawn_resp],
        action_items=[ActionItem(**a) for a in action_items],
        chat_messages=[ChatMessageResponse.model_validate(m) for m in reading.chat_messages],
        reflection_question=reading.reflection_question,
        depth=reading_depth,
        deep_sections=[DeepSection(**s) for s in deep_sections],
    )


@router.post("/{reading_id}/reinterpret", response_model=ReadingResponse)
async def reinterpret_reading(
    reading_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-generate the AI interpretation for a reading.

    Non-members are limited to ``FREE_REINTERPRETS_DAILY`` reinterprets per day
    (members are unlimited).
    """
    # ── Free-tier daily quota (non-members only) ──
    if not user.is_member:
        reset_ai_quota_if_new_day(user)
        if user.reinterpret_count_today >= settings.FREE_REINTERPRETS_DAILY:
            raise HTTPException(status_code=402, detail="今日重解次数已用完，请开通会员")

    result = await db.execute(
        select(Reading)
        .where(Reading.id == reading_id)
        .options(selectinload(Reading.drawn_cards))
    )
    reading = result.scalar_one_or_none()
    if reading is None:
        raise HTTPException(status_code=404, detail="解读不存在")
    if reading.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的解读")

    # Build cards_info from drawn_cards (batch-loaded — avoid N+1 per card)
    drawn_card_ids = [dc.card_id for dc in reading.drawn_cards]
    cards_by_id: dict[int, TarotCard] = {}
    if drawn_card_ids:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id.in_(drawn_card_ids))
        )
        cards_by_id = {card.id: card for card in card_result.scalars().all()}

    cards_info: list[dict] = []
    for dc in reading.drawn_cards:
        card = cards_by_id.get(dc.card_id)
        if card is None:
            continue
        cards_info.append(
            {
                "card_id": dc.card_id,
                "position": dc.position,
                "position_name": dc.position_name,
                "is_reversed": dc.is_reversed,
                "name_zh": card.name_zh,
                "name_en": card.name_en,
                "image_description": card.image_description,
                "meaning_upright": card.meaning_upright,
                "meaning_reversed": card.meaning_reversed,
                "love_upright": card.love_upright,
                "love_reversed": card.love_reversed,
                "career_upright": card.career_upright,
                "career_reversed": card.career_reversed,
                "finance_upright": card.finance_upright,
                "finance_reversed": card.finance_reversed,
            }
        )

    # ── Fetch teaching data for re-interpretation ──
    card_ids = [c.get("card_id") for c in cards_info if c.get("card_id")]
    teaching_info: dict[int, dict] = {}
    if card_ids:
        t_result = await db.execute(
            select(CardTeaching).where(CardTeaching.card_id.in_(card_ids))
        )
        for teaching_row in t_result.scalars().all():
            teaching_info[teaching_row.card_id] = {
                "symbols": json.loads(teaching_row.symbols),
                "story": teaching_row.story,
                "keywords_learning": json.loads(teaching_row.keywords_learning),
                "life_connection": teaching_row.life_connection,
                "element_association": teaching_row.element_association,
            }

    # ── Build user context block (async DB query) ──
    user_context = await _build_user_context_block(db, user.id)

    # ── Depth tier (moved up: generate_reading + section parsing need it) ──
    reading_depth = reading.depth or "standard"

    interpretation = await generate_reading(
        reading.spread_type, reading.question, reading.theme, cards_info,
        teaching_info=teaching_info,
        persona=reading.persona,
        user_context=user_context,
        depth=reading_depth,
    )
    action_items: list[dict] = []
    deep_sections: list[dict] = []
    if interpretation is not None:
        reading.interpretation = interpretation
        action_items = parse_action_items(interpretation)
        if reading_depth == "deep":
            deep_sections = parse_deep_sections(interpretation)

    # ── Apply depth tier truncation ──
    if reading_depth == "basic" and interpretation:
        truncation_note = "\n\n[注：此为免费简要解读。完整解读请升级为标准或深度模式。]"
        interpretation = interpretation[:200] + truncation_note
        reading.interpretation = interpretation

    # ── Generate reflection question (preserve existing if one already exists) ──
    if not reading.reflection_question and cards_info and interpretation:
        first_card_name = cards_info[0].get("name_zh", "")
        reading.reflection_question = await generate_reflection_question(
            reading.question, first_card_name, interpretation,
        )

    # ── Count the successful reinterpret toward the daily quota (non-members) ──
    if not user.is_member:
        user.reinterpret_count_today += 1

    await db.flush()
    await db.refresh(reading, ["drawn_cards"])

    drawn_resp = await _load_drawn_cards_response(db, reading.drawn_cards)

    return ReadingResponse(
        id=reading.id,
        spread_type=reading.spread_type,
        question=reading.question,
        theme=reading.theme,
        persona=reading.persona,
        interpretation=reading.interpretation,
        is_paid=reading.is_paid,
        created_at=reading.created_at,
        drawn_cards=[DrawnCardResponse(**d) for d in drawn_resp],
        action_items=[ActionItem(**a) for a in action_items],
        reflection_question=reading.reflection_question,
        depth=reading_depth,
        deep_sections=[DeepSection(**s) for s in deep_sections],
    )


@router.delete("/history")
async def delete_readings_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all reading history for the current user."""
    # Delete all DrawnCard rows belonging to the user's readings
    subquery = select(Reading.id).where(Reading.user_id == user.id)
    await db.execute(
        delete(DrawnCard).where(DrawnCard.reading_id.in_(subquery))
    )
    # Delete all ChatMessage rows belonging to the user's readings
    await db.execute(
        delete(ChatMessage).where(ChatMessage.reading_id.in_(subquery))
    )
    # Delete the readings themselves
    await db.execute(
        delete(Reading).where(Reading.user_id == user.id)
    )
    return {"detail": "历史记录已清除"}
