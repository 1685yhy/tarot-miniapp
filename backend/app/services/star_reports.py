"""星象月报服务（SDD P2 · T7-1 周报 + T7-2 月报）：star_reports 聚合 + AI + 缓存/降级。

设计决策（P2 设计 2.3，AI 成本控制 P0）：
- 统计段纯 SQL 确定性聚合（周：星运曲线/星尘统计/牌运回顾/星光色带；
  月：天象复盘/手账引用/牌运 TOP3/星尘估算），AI 只写文案段
  （周寄语 ≤60 字 / 月总评 ≤100 字）；
- 懒生成（打开才生成）+ 按人按周期缓存（star_reports，命中零 AI）；
- AI 失败/无 key/输出含共享禁词（find_forbidden · AI_OUTPUT_BLACKLIST）
  → 本地温柔降级模板（统计段永不受影响）；
- 周期口径：周 = ISO 周键（复用 ``journal.iso_week_key``），缺省 = 上一完整周
  （每周一 00:00 后即可看上周）；月 = 'YYYY-MM' 键，缺省 = 上一完整月
  （每月 1 日 00:00 后即可看上月，设计「每月 1 日后可看上月」）；
- 月报手账段直接引用 ``star_monthly_reviews`` 缓存（零新增 AI 调用）；
  下月展望只预告真实天象日期 + 温柔行动建议（活动预告非运势预测，过禁词扫描）。

数据源：Reading/DrawnCard/TarotCard（牌运）、HoroscopeHistory（7 天能量总分，
无记录日 total=None）、CheckIn + astral_activity_logs（周/月星尘行为计数）、
``build_today_guidance``（7 色带，确定性）、ASTRAL_EVENTS_2026 +
``astral_events_on``（月度天象，零新数据）、``StarMonthlyReview``（手账汇总）、
``tier_for`` / ``tier_name``（当前星阶）。

``get_readings_for_range`` / ``get_diary_entries_for_range`` 是从
api/report.py ``_get_readings_for_days`` / ``_get_diary_entries_for_days``
抽取的通用区间版本（report.py 委托调用，行为等价）。
"""

import json
import logging
import re
from collections import Counter
from datetime import date, datetime, time, timedelta

from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.astral_activity_log import AstralActivityLog
from app.models.card import TarotCard
from app.models.checkin import CheckIn
from app.models.diary import DiaryEntry
from app.models.horoscope import HoroscopeHistory
from app.models.reading import DrawnCard, Reading
from app.models.star_monthly_review import StarMonthlyReview
from app.models.star_report import StarReport
from app.models.user import User
from app.services.ai_engine import _OUTPUT_RED_LINE
from app.services.compliance import AI_OUTPUT_BLACKLIST, find_forbidden
from app.services.energy_engine import ASTRAL_EVENTS_2026, build_today_guidance
from app.services.journal import iso_week_key
from app.services.star_words import beijing_today
from app.services.stardust import tier_for, tier_name

logger = logging.getLogger(__name__)

_WEEK_PATTERN = re.compile(r"^(\d{4})-W(\d{1,2})$")
_MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
_MAX_NOTE_LEN = 60  # AI 周寄语 ≤60 字
_MAX_MONTH_NOTE_LEN = 100  # AI 月总评 ≤100 字

# ── 降级寄语（AI 失败/无 key 时按能量均值三档；均不下定性结论，过禁词扫描）──
_FALLBACK_WEEK_NOTE_HIGH = "这一周星光明亮，抽牌与日记陪你走得很稳。"
_FALLBACK_WEEK_NOTE_MEDIUM = "这一周星光平稳，起起落落都是星光留下的印记。"
_FALLBACK_WEEK_NOTE_LOW = "这一周星光有些微暗，记得多给自己一点温柔。"
# 空态周温柔引导（不发 AI、不落缓存）
_EMPTY_WEEK_NOTE = "这一周夜空还很安静，等你来点亮第一颗星。"
# 月报降级总评（AI 失败/无 key；不下定性结论，过禁词扫描）
_FALLBACK_MONTH_NOTE = "这一个月，星光记得你的每一次靠近，慢一点也没关系。"
# 空态月温柔引导（不发 AI、不落缓存）
_EMPTY_MONTH_NOTE = "这个月夜空还很安静，等你来点亮第一颗星。"


# ═══════════════════════════════════════════════════════════════════════
# 周期键 / 区间（纯函数 + 通用区间查询）
# ═══════════════════════════════════════════════════════════════════════


def period_week_key(d: date) -> str:
    """ISO 周键（如 2026-W33；复用 journal.iso_week_key，避免重复实现）。

    年初/年末跨年周取 ISO 年（如 2026-W01 的周一落在 2025-12-29）。
    """
    return iso_week_key(d)


def week_bounds(period: str) -> tuple[date, date]:
    """周区间 [周一, 周日]（含首尾）。

    形如 '2026-W33'；跨年周由 ``date.fromisocalendar`` 处理
    （2026-W01 → 2025-12-29 ~ 2026-01-04）。非法/不存在的周期抛 ValueError。
    """
    m = _WEEK_PATTERN.fullmatch(period)
    if not m:
        raise ValueError(f"非法周周期: {period!r}")
    year, week = int(m.group(1)), int(m.group(2))
    try:
        monday = date.fromisocalendar(year, week, 1)
    except ValueError:
        raise ValueError(f"不存在的周: {period!r}") from None
    return monday, monday + timedelta(days=6)


def last_completed_week(today: date) -> str:
    """上一完整周键（本周尚未结束，任一天调用均返回上周）。

    设计「每周一 00:00 后可看上周」：周一当天 → 上周；周日 → 上周。
    """
    return period_week_key(today - timedelta(days=7))


def period_month_key(d: date) -> str:
    """月键（'YYYY-MM'，如 2026-08）。"""
    return f"{d.year}-{d.month:02d}"


def month_bounds(period: str) -> tuple[date, date]:
    """月区间 [月初, 月末]（含首尾）。

    形如 '2026-08'；'YYYY-01' ~ 'YYYY-12'，跨年由年字段直接处理。
    非法/不存在的周期抛 ValueError。
    """
    m = _MONTH_PATTERN.fullmatch(period)
    if not m:
        raise ValueError(f"非法月周期: {period!r}")
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"不存在的月: {period!r}")
    first = date(year, month, 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


def last_completed_month(today: date) -> str:
    """上一完整月键（本月尚未结束，任一天调用均返回上月）。

    设计「每月 1 日后可看上月」：1 日当天 → 上月；月末 → 上月；跨年自然处理。
    """
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def _next_month_key(period: str) -> str:
    """下月键（展望用；period 已由 month_bounds 校验）。"""
    start, _end = month_bounds(period)
    if start.month == 12:
        return f"{start.year + 1}-01"
    return f"{start.year}-{start.month + 1:02d}"


async def get_readings_for_range(
    db: AsyncSession, user_id: str, start: date, end: date
) -> list[Reading]:
    """区间占卜（含首尾日，UTC 零点口径），带 drawn_cards.card 预载。

    从 api/report.py ``_get_readings_for_days`` 抽取的通用区间版本；
    report.py 委托调用，行为等价（近 N 自然日 = [today-(N-1), today]）。
    """
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)
    result = await db.execute(
        select(Reading)
        .where(
            Reading.user_id == user_id,
            Reading.created_at >= start_dt,
            Reading.created_at < end_dt,
        )
        .options(selectinload(Reading.drawn_cards).selectinload(DrawnCard.card))
        .order_by(Reading.created_at.asc())
    )
    return list(result.scalars().all())


async def get_diary_entries_for_range(
    db: AsyncSession, user_id: str, start: date, end: date
) -> list[DiaryEntry]:
    """区间日记（entry_date 含首尾日）。report.py 委托调用。"""
    result = await db.execute(
        select(DiaryEntry)
        .where(
            DiaryEntry.user_id == user_id,
            DiaryEntry.entry_date >= start,
            DiaryEntry.entry_date <= end,
        )
        .order_by(DiaryEntry.entry_date.asc())
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════
# 周聚合（纯 SQL 确定性，零 AI）
# ═══════════════════════════════════════════════════════════════════════


def _parse_keywords(raw: str | None) -> list[str]:
    """解析卡牌关键词（JSON 数组或中文顿号分隔的旧数据），取前 3。"""
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(k) for k in parsed][:3]
    except (json.JSONDecodeError, TypeError):
        pass
    parts = re.split(r"[、,，]", raw)
    return [p.strip() for p in parts if p.strip()][:3]


async def aggregate_week(
    db: AsyncSession, user: User, start: date, end: date
) -> dict:
    """周聚合（纯 SQL 确定性聚合，零 AI）。

    返回::
        {
            "curve": [{"date": "2026-08-10", "total": 260}, ...],  # 7 天；无记录日 None
            "stardust": {"checkin_days": 2, "activity_events": 1, "total": 3},
            "cards": {
                "readings_count": 4,
                "most_card": {"name": "卡牌1", "count": 3, "keywords": [...]} | None,
                "card_list": [{"name": "卡牌1", "count": 3}, ...],
            },
            "color_band": [{"date": ..., "star_color": "#..."}],  # 7 天
        }

    - curve：HoroscopeHistory 四维能量之和（无记录日 total=None，不崩溃）
    - stardust：本周星尘行为计数（签到天数 + 节点活动事件数；估算口径，
      与设计 2.5.4「当月行为可得星尘」一致，不承诺精确账目）
    - color_band：build_today_guidance 确定性生成（同日同人恒定）
    """
    days = [start + timedelta(days=i) for i in range(7)]
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)

    # ── 星运曲线：7 天能量总分 ──
    horo_result = await db.execute(
        select(HoroscopeHistory.date, HoroscopeHistory.energy).where(
            HoroscopeHistory.user_id == user.id,
            HoroscopeHistory.date >= start,
            HoroscopeHistory.date <= end,
        )
    )
    energy_by_day = {
        row.date: sum(row.energy.values()) if isinstance(row.energy, dict) else None
        for row in horo_result.all()
    }
    curve = [
        {"date": day.isoformat(), "total": energy_by_day.get(day)}
        for day in days
    ]

    # ── 星尘统计：签到 + 节点活动 ──
    checkin_days = (
        await db.execute(
            select(func.count(CheckIn.id)).where(
                CheckIn.user_id == user.id,
                CheckIn.checkin_date >= start,
                CheckIn.checkin_date <= end,
            )
        )
    ).scalar_one()
    activity_events = (
        await db.execute(
            select(func.count(AstralActivityLog.id)).where(
                AstralActivityLog.user_id == user.id,
                AstralActivityLog.event_date >= start,
                AstralActivityLog.event_date <= end,
            )
        )
    ).scalar_one()
    stardust = {
        "checkin_days": checkin_days,
        "activity_events": activity_events,
        "total": checkin_days + activity_events,
    }

    # ── 牌运回顾：占卜次数 + 抽牌榜（单 join 查询）──
    readings_count = (
        await db.execute(
            select(func.count(Reading.id)).where(
                Reading.user_id == user.id,
                Reading.created_at >= start_dt,
                Reading.created_at < end_dt,
            )
        )
    ).scalar_one()
    card_rows = (
        await db.execute(
            select(TarotCard.name_zh, TarotCard.keywords_upright)
            .join(DrawnCard, DrawnCard.card_id == TarotCard.id)
            .join(Reading, Reading.id == DrawnCard.reading_id)
            .where(
                Reading.user_id == user.id,
                Reading.created_at >= start_dt,
                Reading.created_at < end_dt,
            )
            # 显式定序：无 ORDER BY 时行序由数据库实现决定，
            # 平局时 most_common 取首见牌会不确定——按卡名排序后同人同周期结果确定
            .order_by(TarotCard.name_zh)
        )
    ).all()
    counter = Counter(name for name, _ in card_rows)
    keywords_by_name: dict[str, list[str]] = {}
    for name, raw in card_rows:
        keywords_by_name.setdefault(name, _parse_keywords(raw))

    most_card = None
    if counter:
        # 平局规则：同次数取卡名排序最前（name_zh 升序首见者）
        top_name = counter.most_common(1)[0][0]
        most_card = {
            "name": top_name,
            "count": counter[top_name],
            "keywords": keywords_by_name.get(top_name, []),
        }
    card_list = [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    cards = {
        "readings_count": readings_count,
        "most_card": most_card,
        "card_list": card_list,
    }

    # ── 星光色带：build_today_guidance 确定性生成 ──
    color_band = [
        {
            "date": day.isoformat(),
            "star_color": build_today_guidance(day, user.zodiac or None)["star_color"],
        }
        for day in days
    ]

    return {"curve": curve, "stardust": stardust, "cards": cards, "color_band": color_band}


# ═══════════════════════════════════════════════════════════════════════
# 月聚合（纯 SQL 确定性，零 AI；手账段直接引用 star_monthly_reviews 缓存）
# ═══════════════════════════════════════════════════════════════════════


async def aggregate_month(
    db: AsyncSession, user: User, start: date, end: date
) -> dict:
    """月聚合（纯 SQL 确定性聚合，零 AI）。

    返回::
        {
            "astral_events": [{"type", "label", "date"}, ...],  # 当月天象（日历事实）
            "journal": {"active_days", "bright_ratio", "trend"} | None,  # 引用缓存
            "cards": {"readings_count": N, "top3": [{"name", "count"}, ...]},
            "stardust": {"estimated": N, "tier_name": "..."},
        }

    - astral_events：ASTRAL_EVENTS_2026 当月事件（含区间事件首日），按日期升序
    - journal：直接引用 ``StarMonthlyReview`` 缓存 data JSON 的
      stats.days_recorded / stats.bright_ratio / trend_summary —— 零新增 AI 调用；
      无缓存/损坏 → None
    - cards：月度占卜次数 + 抽牌 TOP3（次数降序、平局卡名升序，确定性）
    - stardust：当月行为可得星尘估算（签到天数 + 节点活动事件数，不承诺精确账目）
      + 当前星阶名（star_tier 缺失时按 stardust_total 经 tier_for 兜底推导）
    """
    month_key = period_month_key(start)

    # ── 月度天象复盘：当月事件（零新数据，直接查表）──
    month_events = sorted(
        (
            ev
            for ev in ASTRAL_EVENTS_2026
            if start <= ev["start"] <= end
        ),
        key=lambda ev: (ev["start"], ev["type"]),
    )
    astral_events = [
        {"type": ev["type"], "label": ev["label"], "date": ev["start"].isoformat()}
        for ev in month_events
    ]

    # ── 星光手账汇总：直接引用 star_monthly_reviews 缓存（零新增 AI）──
    journal = None
    review_row = (
        await db.execute(
            select(StarMonthlyReview).where(
                StarMonthlyReview.user_id == user.id,
                StarMonthlyReview.month == month_key,
            )
        )
    ).scalar_one_or_none()
    if review_row is not None:
        try:
            review_data = json.loads(review_row.data)
        except (ValueError, TypeError):
            review_data = None
        if isinstance(review_data, dict) and isinstance(review_data.get("stats"), dict):
            journal = {
                "active_days": review_data["stats"].get("days_recorded", 0),
                "bright_ratio": review_data["stats"].get("bright_ratio", 0.0),
                "trend": (review_data.get("trend_summary") or "").strip(),
            }

    # ── 牌运回顾：月度占卜次数 + TOP3 ──
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)
    readings_count = (
        await db.execute(
            select(func.count(Reading.id)).where(
                Reading.user_id == user.id,
                Reading.created_at >= start_dt,
                Reading.created_at < end_dt,
            )
        )
    ).scalar_one()
    card_rows = (
        await db.execute(
            select(TarotCard.name_zh)
            .join(DrawnCard, DrawnCard.card_id == TarotCard.id)
            .join(Reading, Reading.id == DrawnCard.reading_id)
            .where(
                Reading.user_id == user.id,
                Reading.created_at >= start_dt,
                Reading.created_at < end_dt,
            )
            # 显式定序：无 ORDER BY 时行序由数据库实现决定，平局时首见牌不确定
            .order_by(TarotCard.name_zh)
        )
    ).all()
    counter = Counter(name for (name,) in card_rows)
    top3 = [
        {"name": name, "count": count}
        for name, count in sorted(
            counter.items(), key=lambda kv: (-kv[1], kv[0])
        )[:3]
    ]

    # ── 星尘与星阶：当月行为可得星尘（估算口径）+ 当前星阶 ──
    checkin_days = (
        await db.execute(
            select(func.count(CheckIn.id)).where(
                CheckIn.user_id == user.id,
                CheckIn.checkin_date >= start,
                CheckIn.checkin_date <= end,
            )
        )
    ).scalar_one()
    activity_events = (
        await db.execute(
            select(func.count(AstralActivityLog.id)).where(
                AstralActivityLog.user_id == user.id,
                AstralActivityLog.event_date >= start,
                AstralActivityLog.event_date <= end,
            )
        )
    ).scalar_one()
    tier = user.star_tier if user.star_tier is not None else tier_for(user.stardust_total or 0)
    stardust = {
        "estimated": checkin_days + activity_events,
        "tier_name": tier_name(tier),
    }

    return {
        "astral_events": astral_events,
        "journal": journal,
        "cards": {"readings_count": readings_count, "top3": top3},
        "stardust": stardust,
    }


def build_outlook(next_month: str, events_2026: list[dict]) -> dict:
    """下月展望（活动预告非运势预测，文案过禁词扫描）。

    返回::
        {
            "first_new_moon": {"type", "label", "date"} | None,
            "first_full_moon": {...} | None,
            "first_retrograde": {...} | None,   # 水逆优先，金星逆行为兜底
            "tips": [...],                       # 温柔行动建议（仅当对应事件存在）
        }

    只取 ``events_2026`` 中 start 落在下月的真实事件；每个位取当月首个同类事件。
    """
    start, _end = month_bounds(next_month)
    if start.month == 12:
        next_start = date(start.year + 1, 1, 1)
    else:
        next_start = date(start.year, start.month + 1, 1)
    month_events = sorted(
        (
            ev
            for ev in events_2026
            if start <= ev["start"] < next_start
        ),
        key=lambda ev: (ev["start"], ev["type"]),
    )

    def _first(etype: str) -> dict | None:
        for ev in month_events:
            if ev["type"] == etype:
                return {
                    "type": etype,
                    "label": ev["label"],
                    "date": ev["start"].isoformat(),
                }
        return None

    first_new_moon = _first("new_moon")
    first_full_moon = _first("full_moon")
    first_retrograde = _first("mercury_retrograde") or _first("venus_retrograde")

    tips = []
    if first_new_moon:
        tips.append("新月之夜，给自己留一页空白，写下新的期许。")
    if first_full_moon:
        tips.append("满月时分，把完成的事轻轻放下，让月光照见收成。")
    if first_retrograde:
        tips.append("慢行的日子要来了，重要决定不妨缓一缓。")
    return {
        "first_new_moon": first_new_moon,
        "first_full_moon": first_full_moon,
        "first_retrograde": first_retrograde,
        "tips": tips,
    }


# ═══════════════════════════════════════════════════════════════════════
# AI 寄语 + 降级模板
# ═══════════════════════════════════════════════════════════════════════


def _get_ai_client() -> AsyncOpenAI | None:
    """DeepSeek 客户端（与 report.py / journal.py 同款封装）。"""
    if not settings.DEEPSEEK_API_KEY:
        return None
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


async def generate_week_note_ai(
    db: AsyncSession, user: User, stats: dict
) -> str | None:
    """周寄语（≤60 字）：DeepSeek 生成，system 含 ``_OUTPUT_RED_LINE``。

    失败 / 无 key / 非 JSON / 输出含共享禁词（find_forbidden ·
    AI_OUTPUT_BLACKLIST）→ 返回 None（由调用方走降级模板）。``db`` 参数为
    签名预留（后续按需注入日记/心情上下文，当前未使用）。
    """
    client = _get_ai_client()
    if client is None:
        return None

    curve_text = "、".join(
        f"{p['date']}:{p['total']}" for p in stats["curve"] if p["total"] is not None
    ) or "本周暂无能量记录"
    most = stats["cards"]["most_card"]
    card_text = (
        f"最常抽到的牌: {most['name']}（{most['count']}次）" if most else "本周未抽牌"
    )
    stardust = stats["stardust"]

    system_prompt = (
        "你是一位温柔而有诗意的塔罗周记陪伴者，像老朋友一样了解用户。"
        "所有输出必须使用中文。"
    ) + _OUTPUT_RED_LINE

    user_prompt = (
        "请基于用户过去一周（周一至周日）的星象数据，写一句本周寄语。\n\n"
        f"【本周数据】\n"
        f"每日能量总分: {curve_text}\n"
        f"{card_text}\n"
        f"签到 {stardust['checkin_days']} 天 · 节点活动 {stardust['activity_events']} 次\n\n"
        "要求：一行、温暖有画面感、像朋友的一句话，不超过60字；"
        "只描述状态与感受，不下结论、不预测、不恐吓。"
        "请严格按照以下JSON格式回复，不要包含任何多余内容：\n"
        '{"note": "..."}'
    )
    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=256,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=60.0,
        )
        content = response.choices[0].message.content
        if not content:
            return None
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = "\n".join(
                line for line in stripped.split("\n")
                if not line.strip().startswith("```")
            ).strip()
        try:
            note = json.loads(stripped).get("note")
        except (json.JSONDecodeError, TypeError, AttributeError):
            logger.warning("周寄语 AI 返回非 JSON，走降级: %s", stripped[:200])
            return None
        if not isinstance(note, str) or not note.strip():
            return None
        note = note.strip()
        if find_forbidden(note, AI_OUTPUT_BLACKLIST):
            logger.warning("周寄语 AI 输出含禁词，走降级: %s", note[:60])
            return None
        return note[:_MAX_NOTE_LEN]
    except Exception as exc:
        logger.warning("周寄语 AI 生成失败，走降级: %s", exc)
        return None


async def generate_month_note_ai(
    db: AsyncSession, user: User, stats: dict
) -> str | None:
    """月度总评（≤100 字）：DeepSeek 生成，system 含 ``_OUTPUT_RED_LINE``。

    失败 / 无 key / 非 JSON / 输出含共享禁词（find_forbidden ·
    AI_OUTPUT_BLACKLIST）→ 返回 None（由调用方走降级模板）。``db`` 参数为
    签名预留（与周寄语一致）。
    """
    client = _get_ai_client()
    if client is None:
        return None

    astral_text = "、".join(
        f"{ev['date']} {ev['label']}" for ev in stats["astral_events"]
    ) or "本月暂无天象事件"
    journal = stats["journal"]
    journal_text = (
        f"手账点亮 {journal['active_days']} 天 · 亮暗比例 "
        f"{journal['bright_ratio']:.0%} · 情绪趋势: {journal['trend']}"
        if journal
        else "本月暂无手账记录"
    )
    top3 = stats["cards"]["top3"]
    cards_text = "、".join(f"{c['name']}({c['count']}次)" for c in top3) or "本月未抽牌"
    stardust = stats["stardust"]

    system_prompt = (
        "你是一位温柔而有诗意的塔罗月报陪伴者，像老朋友一样为你回望这一段星光。"
        "所有输出必须使用中文。"
    ) + _OUTPUT_RED_LINE

    user_prompt = (
        "请基于用户上一个月的星象数据，写一段月度总评。\n\n"
        f"【本月数据】\n"
        f"天象事件: {astral_text}\n"
        f"{journal_text}\n"
        f"牌运: 占卜 {stats['cards']['readings_count']} 次 · 常抽: {cards_text}\n"
        f"星尘: 本月点亮 {stardust['estimated']} 颗星尘\n\n"
        "要求：一段、温暖、有画面感，不超过100字；"
        "只描述状态与感受，不下结论、不预测、不恐吓。"
        "请严格按照以下JSON格式回复，不要包含任何多余内容：\n"
        '{"note": "..."}'
    )
    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=256,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=60.0,
        )
        content = response.choices[0].message.content
        if not content:
            return None
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = "\n".join(
                line for line in stripped.split("\n")
                if not line.strip().startswith("```")
            ).strip()
        try:
            note = json.loads(stripped).get("note")
        except (json.JSONDecodeError, TypeError, AttributeError):
            logger.warning("月总评 AI 返回非 JSON，走降级: %s", stripped[:200])
            return None
        if not isinstance(note, str) or not note.strip():
            return None
        note = note.strip()
        if find_forbidden(note, AI_OUTPUT_BLACKLIST):
            logger.warning("月总评 AI 输出含禁词，走降级: %s", note[:60])
            return None
        return note[:_MAX_MONTH_NOTE_LEN]
    except Exception as exc:
        logger.warning("月总评 AI 生成失败，走降级: %s", exc)
        return None


def build_month_report(stats: dict, ai_note: str | None) -> dict:
    """完整月报 JSON（统计段 + 展望 + 总评段）。

    - ai_note 非空 → 直接使用（source 由调用方标记 ai）
    - ai_note 为空 → 降级温柔总评；完全空态月 → 温柔引导文案
      （统计 0 + 「夜空等着被你点亮」，不发 AI、不落缓存由调用方决定）
    """
    note = ai_note
    if not note:
        if (
            stats["cards"]["readings_count"] == 0
            and stats["stardust"]["estimated"] == 0
            and stats["journal"] is None
        ):
            note = _EMPTY_MONTH_NOTE
        else:
            note = _FALLBACK_MONTH_NOTE
    return {**stats, "note": note}


def _energy_star_mean(stats: dict) -> float | None:
    """能量均值（0-5 星口径）：日均能量总分归一化。

    能量四维取值 35-98（energy_engine normalize 口径），总分 = 四维之和；
    总分 / 80 即平均维度得分 / 20 → 0-5 星（降级三档阈值 ≥4/≥3/<3 基于此）。
    无任何能量记录返回 None。
    """
    totals = [p["total"] for p in stats["curve"] if p["total"] is not None]
    if not totals:
        return None
    return sum(totals) / len(totals) / 80.0


def build_week_report(stats: dict, ai_note: str | None) -> dict:
    """完整报告 JSON（统计段 + 寄语段）。

    - ai_note 非空 → 直接使用（source 由调用方标记 ai）
    - ai_note 为空 → 降级三档文案（按能量均值 ≥4/≥3/<3，均不下定性结论）；
      完全空态周 → 温柔引导文案
    """
    note = ai_note
    if not note:
        star_mean = _energy_star_mean(stats)
        if star_mean is None:
            if not stats["cards"]["readings_count"] and stats["stardust"]["total"] == 0:
                note = _EMPTY_WEEK_NOTE
            else:
                note = _FALLBACK_WEEK_NOTE_MEDIUM
        elif star_mean >= 4:
            note = _FALLBACK_WEEK_NOTE_HIGH
        elif star_mean >= 3:
            note = _FALLBACK_WEEK_NOTE_MEDIUM
        else:
            note = _FALLBACK_WEEK_NOTE_LOW
    return {**stats, "note": note}


# ═══════════════════════════════════════════════════════════════════════
# 缓存读写（star_reports，按人按周期一份；仿 star_monthly_reviews 模式）
# ═══════════════════════════════════════════════════════════════════════


async def _load_cached_report(
    db: AsyncSession, user_id: str, report_type: str, period: str
) -> tuple[dict, str] | None:
    """读报告缓存（data JSON + source）；无缓存或损坏返回 None。"""
    result = await db.execute(
        select(StarReport).where(
            StarReport.user_id == user_id,
            StarReport.report_type == report_type,
            StarReport.period_key == period,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    try:
        data = json.loads(row.data)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data, row.source


async def _save_cached_report(
    db: AsyncSession, user_id: str, report_type: str, period: str,
    data: dict, source: str,
) -> None:
    """写入/覆盖报告缓存（upsert，幂等）。"""
    result = await db.execute(
        select(StarReport).where(
            StarReport.user_id == user_id,
            StarReport.report_type == report_type,
            StarReport.period_key == period,
        )
    )
    row = result.scalar_one_or_none()
    payload = json.dumps(data, ensure_ascii=False)
    if row:
        row.data = payload
        row.source = source
    else:
        db.add(StarReport(
            user_id=user_id,
            report_type=report_type,
            period_key=period,
            data=payload,
            source=source,
        ))


async def get_or_create_week_report(
    db: AsyncSession, user: User, period: str, force: bool = False
) -> dict:
    """周报（懒生成 + 缓存）：返回 {report, cached, source}。

    - 缓存命中（非 force）→ 直接返回，零 AI 消耗
    - 未命中：聚合 → AI 寄语 → 落 star_reports（source=ai|fallback）
    - 空态周（无任何数据）→ 统计 0 + 温柔引导，不发 AI、不落缓存（source=None）
    - force=True → 覆盖缓存重新生成
    """
    if not force:
        cached = await _load_cached_report(db, user.id, "week", period)
        if cached is not None:
            return {"report": cached[0], "cached": True, "source": cached[1]}

    start, end = week_bounds(period)
    stats = await aggregate_week(db, user, start, end)

    if (
        not stats["cards"]["readings_count"]
        and stats["stardust"]["total"] == 0
        and all(p["total"] is None for p in stats["curve"])
    ):
        # 空态周：温柔引导，不发 AI、不落缓存
        return {
            "report": build_week_report(stats, None),
            "cached": False,
            "source": None,
        }

    ai_note = await generate_week_note_ai(db, user, stats)
    source = "ai" if ai_note else "fallback"
    report = build_week_report(stats, ai_note)
    await _save_cached_report(db, user.id, "week", period, report, source)
    return {"report": report, "cached": False, "source": source}


async def get_or_create_month_report(
    db: AsyncSession, user: User, period: str, force: bool = False
) -> dict:
    """月报（懒生成 + 缓存）：返回 {report, cached, source}。

    - 缓存命中（非 force）→ 直接返回，零 AI 消耗
    - 未命中：聚合 → 展望 → AI 月总评 → 落 star_reports（source=ai|fallback）
    - 空态月（无任何用户数据）→ 统计 0 + 温柔引导，不发 AI、不落缓存
      （天象/展望是日历事实，照常入报告）
    - force=True → 覆盖缓存重新生成
    """
    if not force:
        cached = await _load_cached_report(db, user.id, "month", period)
        if cached is not None:
            return {"report": cached[0], "cached": True, "source": cached[1]}

    start, end = month_bounds(period)
    stats = await aggregate_month(db, user, start, end)
    stats["outlook"] = build_outlook(_next_month_key(period), ASTRAL_EVENTS_2026)

    if (
        stats["cards"]["readings_count"] == 0
        and stats["stardust"]["estimated"] == 0
        and stats["journal"] is None
    ):
        # 空态月：温柔引导，不发 AI、不落缓存
        return {
            "report": build_month_report(stats, None),
            "cached": False,
            "source": None,
        }

    ai_note = await generate_month_note_ai(db, user, stats)
    source = "ai" if ai_note else "fallback"
    report = build_month_report(stats, ai_note)
    await _save_cached_report(db, user.id, "month", period, report, source)
    return {"report": report, "cached": False, "source": source}
