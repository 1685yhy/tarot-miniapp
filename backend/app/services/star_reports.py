"""星象月报服务（SDD P2 · T7-1）：star_reports 周报聚合 + AI 寄语 + 缓存/降级。

设计决策（P2 设计 2.3，AI 成本控制 P0）：
- 统计段纯 SQL 确定性聚合（星运曲线 / 星尘统计 / 牌运回顾 / 星光色带），
  AI 只写文案段（周寄语 ≤60 字）；
- 懒生成（打开才生成）+ 按人按周期缓存（star_reports，命中零 AI）；
- AI 失败/无 key/输出含共享禁词（find_forbidden · AI_OUTPUT_BLACKLIST）
  → 本地温柔降级模板（统计段永不受影响）；
- 周期口径：ISO 周键（复用 ``journal.iso_week_key``，不重复实现）；
  缺省周期 = 上一完整周（``last_completed_week``：周一 00:00 后即可看上周，
  设计「每周一后可看上周」）。

数据源：Reading/DrawnCard/TarotCard（牌运）、HoroscopeHistory（7 天能量总分，
无记录日 total=None）、CheckIn + astral_activity_logs（本周星尘行为计数）、
``build_today_guidance``（7 色带，确定性）。

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
from app.models.star_report import StarReport
from app.models.user import User
from app.services.ai_engine import _OUTPUT_RED_LINE
from app.services.compliance import AI_OUTPUT_BLACKLIST, find_forbidden
from app.services.energy_engine import build_today_guidance
from app.services.journal import iso_week_key
from app.services.star_words import beijing_today

logger = logging.getLogger(__name__)

_WEEK_PATTERN = re.compile(r"^(\d{4})-W(\d{1,2})$")
_MAX_NOTE_LEN = 60  # AI 周寄语 ≤60 字

# ── 降级寄语（AI 失败/无 key 时按能量均值三档；均不下定性结论，过禁词扫描）──
_FALLBACK_WEEK_NOTE_HIGH = "这一周星光明亮，抽牌与日记陪你走得很稳。"
_FALLBACK_WEEK_NOTE_MEDIUM = "这一周星光平稳，起起落落都是星光留下的印记。"
_FALLBACK_WEEK_NOTE_LOW = "这一周星光有些微暗，记得多给自己一点温柔。"
# 空态周温柔引导（不发 AI、不落缓存）
_EMPTY_WEEK_NOTE = "这一周夜空还很安静，等你来点亮第一颗星。"


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
        )
    ).all()
    counter = Counter(name for name, _ in card_rows)
    keywords_by_name: dict[str, list[str]] = {}
    for name, raw in card_rows:
        keywords_by_name.setdefault(name, _parse_keywords(raw))

    most_card = None
    if counter:
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


async def _load_cached_week(
    db: AsyncSession, user_id: str, period: str
) -> tuple[dict, str] | None:
    """读周报缓存（data JSON + source）；无缓存或损坏返回 None。"""
    result = await db.execute(
        select(StarReport).where(
            StarReport.user_id == user_id,
            StarReport.report_type == "week",
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


async def _save_cached_week(
    db: AsyncSession, user_id: str, period: str, data: dict, source: str
) -> None:
    """写入/覆盖周报缓存（upsert，幂等）。"""
    result = await db.execute(
        select(StarReport).where(
            StarReport.user_id == user_id,
            StarReport.report_type == "week",
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
            report_type="week",
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
        cached = await _load_cached_week(db, user.id, period)
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
    await _save_cached_week(db, user.id, period, report, source)
    return {"report": report, "cached": False, "source": source}
