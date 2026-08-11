"""星光手账（Journal）服务层：星光亮度映射 + 连续记录 + 月历聚合 + 月度复盘。

T1-1（SDD P1 · 星光手账）：亮度映射为代码常量不落库；star_color 由
``build_today_guidance`` 按日期确定性生成，同样不落库（免存储免同步）。

T1-2：``build_monthly_review`` 聚合当月日记/卡牌/新满月天象 → DeepSeek 生成
月度星光复盘（trend_summary/insight/next_guide），AI 失败降级本地温柔模板；
AI 输出经黑名单词清洗（注定/越来越糟/越来越差/天生/命）后由 API 层落缓存。
"""

import json
import logging
from collections import Counter
from datetime import date, timedelta

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.card import TarotCard
from app.models.diary import DiaryEntry
from app.models.user import User
from app.services.ai_engine import _OUTPUT_RED_LINE
from app.services.energy_engine import ASTRAL_EVENTS_2026, build_today_guidance
from app.services.stardust import tier_for

logger = logging.getLogger(__name__)

# 6 档情绪 → 5 档星光亮度（代码常量，不落库）
MOOD_BRIGHTNESS: dict[str, int] = {
    "excited": 5,
    "happy": 4,
    "calm": 3,
    "thoughtful": 2,
    "anxious": 1,
    "sad": 1,
}

# 5 档亮度中文命名（月历/复盘文案用；暗星不评判）
BRIGHTNESS_NAMES: dict[int, str] = {
    5: "满溢星光",
    4: "明亮星光",
    3: "常亮星光",
    2: "微暗星光",
    1: "隐没星光",
}

# 缺失/未知情绪兜底档（与 diary.py 现有 `mood or "thoughtful"` 习惯一致）
_DEFAULT_MOOD = "thoughtful"


def brightness_for(mood: str | None) -> int:
    """情绪档 → 星光亮度（1-5）；缺失/未知情绪按『思考』(2) 兜底。"""
    if not mood:
        return MOOD_BRIGHTNESS[_DEFAULT_MOOD]
    return MOOD_BRIGHTNESS.get(mood, MOOD_BRIGHTNESS[_DEFAULT_MOOD])


def current_streak(dates: set[date], today: date) -> int:
    """从 ``today`` 起向前数连续有记录的天然日数（纯函数）。

    - 无记录 → 0
    - 中间缺一天即断（只数到今天为止的连续段）
    - 跨月连续照常累计（纯日期运算，无月界概念）
    """
    streak = 0
    cursor = today
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def journal_days_for(entries, zodiac: str | None) -> list[dict]:
    """月历 days 聚合：亮度映射 + 星光色确定性生成（不落库）。

    ``entries`` 为某用户某月的 ``DiaryEntry`` 列表（建议按 entry_date 升序）。
    返回::

        [{"date": "2026-08-01", "mood": "happy", "brightness": 4,
          "star_color": "#A98B5F", "has_reflection": True, "card_id": 3}, ...]
    """
    days: list[dict] = []
    for e in entries:
        days.append({
            "date": e.entry_date.isoformat(),
            "mood": e.mood,
            "brightness": brightness_for(e.mood),
            "star_color": build_today_guidance(e.entry_date, zodiac)["star_color"],
            "has_reflection": bool(e.reflection and e.reflection.strip()),
            "card_id": e.card_id,
        })
    return days


def month_stats(days: list[dict], today: date, prior_dates: set[date] | None = None) -> dict:
    """月度统计：days_recorded / bright_count(亮度≥4) / dim_count(亮度≤2) / current_streak。

    ``prior_dates``：月初之前的连续记录日期集（API 集成层为跨月 streak 补数据）。
    只并入 current_streak 的计算集合；days_recorded / bright_count / dim_count
    仍只统计当月（与 days 数组口径一致）。
    """
    recorded_dates = {date.fromisoformat(d["date"]) for d in days}
    if prior_dates:
        recorded_dates |= prior_dates
    return {
        "days_recorded": len(days),
        "bright_count": sum(1 for d in days if d["brightness"] >= 4),
        "dim_count": sum(1 for d in days if d["brightness"] <= 2),
        "current_streak": current_streak(recorded_dates, today),
    }


# ═══════════════════════════════════════════════════════════════════════
# T1-3 · 连续 7 天记录 → +1 星尘（ISO 周幂等）
# ═══════════════════════════════════════════════════════════════════════


def iso_week_key(day: date) -> str:
    """ISO 周幂等键（如 2026-W33；VARCHAR(8)）。

    用 ``isocalendar()`` 的 ISO 年（年初几天可能归属上一年第 53 周/下一年
    第 1 周，年号必须取 ISO 年而非公历年）。``journal_streak_reward_week``
    记录发放周键，同周不重复发放。
    """
    iso_year, iso_week, _ = day.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


async def current_streak_for(
    db: AsyncSession, user_id: str, today: date
) -> int:
    """用户以 ``today`` 为锚的连续记录天然日数（跨月连续照常累计）。

    查询投影 entry_date 全集（轻量；dairy 表按用户量级很小），交给纯函数
    ``current_streak`` 计算，与月历统计口径一致。
    """
    result = await db.execute(
        select(DiaryEntry.entry_date).where(DiaryEntry.user_id == user_id)
    )
    return current_streak(set(result.scalars()), today)


def maybe_grant_streak_reward(user: User, streak: int, today: date) -> bool:
    """连续 ≥7 天且本周未发放 → +1 星尘、星阶同步推导、写周键；返回是否发放。

    幂等：``user.journal_streak_reward_week`` 与本周 ISO 周键相同即跳过，
    同周不重复发放。星尘/星阶写入与 tasks.py 签到模式一致：
    ``stardust_total += 1; star_tier = tier_for(stardust_total)``。
    """
    if streak < 7 or user.journal_streak_reward_week == iso_week_key(today):
        return False
    user.stardust_total = (user.stardust_total or 0) + 1
    user.star_tier = tier_for(user.stardust_total)
    user.journal_streak_reward_week = iso_week_key(today)
    return True


# ═══════════════════════════════════════════════════════════════════════
# T1-2 · 月度星光复盘（AI 生成 + 本地降级模板 + 黑名单词清洗）
# ═══════════════════════════════════════════════════════════════════════

# 情绪中文名（与 diary.py MOOD_LABEL_MAP 同口径；services 层不反向依赖 api 层）
_MOOD_LABELS = {
    "happy": "开心",
    "calm": "平静",
    "excited": "兴奋",
    "anxious": "焦虑",
    "sad": "低落",
    "thoughtful": "思考",
}

# 月度复盘 AI 红线（走 ai_engine._OUTPUT_RED_LINE，含「不引用日记原文」）
# 输出黑名单词：合规红线（不下命运定性/不评判趋势），AI 输出与降级文案双保险
_BLACKLIST_WORDS = ("注定", "越来越糟", "越来越差", "天生", "命")
_SANITIZE_REPLACEMENTS = {
    "命中注定": "自有答案",
    "命运": "际遇",
    "命里": "日子里",
    "生命": "生活",
    "注定": "自有答案",
    "越来越糟": "时有起伏",
    "越来越差": "时有起伏",
    "越来越好": "渐入佳境",
    "天生": "原本",
}

# 降级模板（本地温柔文案：只描述夜空状态，不下定性结论；空月引导文案）
_EMPTY_MONTH_COPY = "这个月还没有星光记录——夜空从不催促，星会等你，今晚就记一颗吧。"
_FALLBACK_INSIGHT = "每颗星都是你自己点亮的——看见它，就是看见自己。"
_FALLBACK_NEXT_GUIDE = "下个月，试着给每个夜晚留一颗星的位子——哪怕只写一行心情。"

# 当月新/满月天象类型（含食相——日食必逢新月、月食必逢满月）
_ASTRAL_MOON_TYPES = ("new_moon", "full_moon", "lunar_eclipse", "solar_eclipse")


def _sanitize(text: str) -> str:
    """黑名单词清洗：先短语替换，再移除任何残留的「命」字（红线兜底）。"""
    for word, repl in _SANITIZE_REPLACEMENTS.items():
        text = text.replace(word, repl)
    return text.replace("命", "")


def _fallback_trend(bright_ratio: float) -> str:
    """按亮暗比例分档的降级趋势文案（不下「越来越好/越来越糟」类定性结论）。

    空月由调用方（build_monthly_review）提前返回 _EMPTY_MONTH_COPY，不会
    走到这里；记录过但近乎全暗（ratio≈0）也归入微光文案（"隐没的星也是
    夜空的居民"，不评判）。
    """
    if bright_ratio >= 0.6:
        return "这个月你的夜空格外明亮——多数夜晚星光满溢，收下这份光亮，它属于你。"
    if bright_ratio >= 0.35:
        return "这个月你的夜空明暗交错——亮着的星与歇着的星，都是夜空的一部分。"
    return "这个月你的夜空以微光为主——隐没的星也在夜空里，它只是需要一点时间，再亮起来。"


def _parse_ai_json(content: str) -> dict | None:
    """剥离 markdown 围栏后解析 JSON；失败返回 None（复用 /diary/review 模式）。"""
    stripped = (content or "").strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        stripped = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _get_ai_client() -> AsyncOpenAI | None:
    """DeepSeek 客户端（与 diary.py / wishes.py 同款）。"""
    if not settings.DEEPSEEK_API_KEY:
        return None
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


def _month_start(month: str) -> date:
    y, m = month.split("-")
    return date(int(y), int(m), 1)


def _next_month_start(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _month_astral_labels(month_start: date) -> list[str]:
    """当月新/满月天象标签（如「8-12 狮子座新月」，按日期升序）。"""
    month_end = _next_month_start(month_start)
    events = sorted(
        (
            ev
            for ev in ASTRAL_EVENTS_2026
            if ev["type"] in _ASTRAL_MOON_TYPES
            and month_start <= ev["start"] < month_end
        ),
        key=lambda ev: ev["start"],
    )
    return [f"{ev['start'].month}-{ev['start'].day} {ev['label']}" for ev in events]


async def _collect_month(
    db: AsyncSession, user_id: str, zodiac: str | None, month: str
) -> tuple[list[DiaryEntry], list[dict], dict[int, TarotCard]]:
    """当月日记 + 月历 days + 卡牌映射（服务层内部共用）。"""
    start = _month_start(month)
    end = _next_month_start(start)
    result = await db.execute(
        select(DiaryEntry)
        .where(
            DiaryEntry.user_id == user_id,
            DiaryEntry.entry_date >= start,
            DiaryEntry.entry_date < end,
        )
        .order_by(DiaryEntry.entry_date.asc())
    )
    entries = result.scalars().all()
    days = journal_days_for(entries, zodiac)

    cards_map: dict[int, TarotCard] = {}
    card_ids = [e.card_id for e in entries if e.card_id is not None]
    if card_ids:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id.in_(card_ids))
        )
        for card in card_result.scalars().all():
            cards_map[card.id] = card
    return entries, days, cards_map


def _aggregate(
    entries: list[DiaryEntry],
    days: list[dict],
    cards_map: dict[int, TarotCard],
    month: str,
) -> dict:
    """当月聚合纯函数：stats / mood_series / star_color_counts / top_cards。

    share-preview 与 build_monthly_review 共用；star_color 由
    ``build_today_guidance`` 按日确定性生成（不落库）。
    """
    recorded = len(days)
    bright = sum(1 for d in days if d["brightness"] >= 4)
    dim = sum(1 for d in days if d["brightness"] <= 2)
    bright_ratio = round(bright / recorded, 4) if recorded else 0.0

    color_counts = Counter(d["star_color"] for d in days)
    card_counts: Counter[str] = Counter()
    for e in entries:
        if e.card_id and e.card_id in cards_map:
            card_counts[cards_map[e.card_id].name_zh] += 1

    return {
        "month": month,
        "stats": {
            "days_recorded": recorded,
            "bright_count": bright,
            "dim_count": dim,
            "bright_ratio": bright_ratio,
        },
        "mood_series": [
            {"date": d["date"], "mood": d["mood"], "brightness": d["brightness"]}
            for d in days
        ],
        "star_color_counts": [
            {"color": c, "count": n}
            for c, n in sorted(
                color_counts.items(), key=lambda kv: (-kv[1], kv[0])
            )
        ],
        "top_cards": [
            {"name": n, "count": c}
            for n, c in sorted(card_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


async def aggregate_month(
    db: AsyncSession, user_id: str, zodiac: str | None, month: str
) -> dict:
    """当月聚合（无 AI）：stats / mood_series / star_color_counts / top_cards。

    share-preview 复用；不触发 AI、不消耗配额。
    """
    entries, days, cards_map = await _collect_month(db, user_id, zodiac, month)
    return _aggregate(entries, days, cards_map, month)


async def build_monthly_review(
    db: AsyncSession, user_id: str, zodiac: str | None, month: str
) -> dict:
    """月度星光复盘：聚合当月数据 → AI 生成（trend_summary/insight/next_guide）。

    - 空月：返回友好文案，不发 AI（由调用方决定不落缓存）
    - AI 成功：输出经黑名单词清洗，source="ai"
    - AI 失败/无 key/非法 JSON：本地温柔模板，source="fallback"
    """
    entries, days, cards_map = await _collect_month(db, user_id, zodiac, month)

    if not entries:
        return {
            "month": month,
            "stats": {
                "days_recorded": 0,
                "bright_count": 0,
                "dim_count": 0,
                "bright_ratio": 0.0,
            },
            "mood_series": [],
            "star_color_counts": [],
            "top_cards": [],
            "trend_summary": _EMPTY_MONTH_COPY,
            "insight": None,
            "next_guide": None,
            "source": None,
        }

    agg = _aggregate(entries, days, cards_map, month)
    stats = agg["stats"]
    astral_labels = _month_astral_labels(_month_start(month))
    ai = await _ai_generate(
        entries, cards_map, stats, agg["top_cards"], astral_labels, month
    )

    if ai is None:
        return {
            **agg,
            "trend_summary": _fallback_trend(stats["bright_ratio"]),
            "insight": _FALLBACK_INSIGHT,
            "next_guide": _FALLBACK_NEXT_GUIDE,
            "source": "fallback",
        }
    return {
        **agg,
        "trend_summary": ai["trend_summary"] or _fallback_trend(stats["bright_ratio"]),
        "insight": ai["insight"] or _FALLBACK_INSIGHT,
        "next_guide": ai["next_guide"] or _FALLBACK_NEXT_GUIDE,
        "source": "ai",
    }


async def _ai_generate(
    entries: list[DiaryEntry],
    cards_map: dict[int, TarotCard],
    stats: dict,
    top_cards: list[dict],
    astral_labels: list[str],
    month: str,
) -> dict | None:
    """调用 DeepSeek 生成复盘三段文案；任何失败返回 None（走降级）。"""

    parts = []
    for e in entries:
        mood_label = _MOOD_LABELS.get(e.mood or "thoughtful", "思考")
        card_name = (
            cards_map[e.card_id].name_zh
            if e.card_id and e.card_id in cards_map
            else "无"
        )
        snippet = e.reflection or ""
        if len(snippet) > 80:
            snippet = snippet[:80] + "..."
        parts.append(
            f"- {e.entry_date} | 心情: {mood_label} | 卡牌: {card_name} | 感悟: {snippet or '无记录'}"
        )
    entries_text = "\n".join(parts)
    top_cards_text = "、".join(f"{t['name']}（{t['count']}次）" for t in top_cards) or "无"
    astral_text = "；".join(astral_labels) if astral_labels else "本月无新/满月天象"

    user_prompt = (
        "你是一位温柔且富有洞察力的星光手账分析师。请基于用户本月的星光日记记录，"
        "生成一份月度星光复盘。\n\n"
        f"【月度数据】\n"
        f"月份: {month}\n"
        f"记录天数: {stats['days_recorded']} 天\n"
        f"点亮天数（亮度≥4，满溢/明亮）: {stats['bright_count']} 天\n"
        f"微暗天数（亮度≤2，微暗/隐没）: {stats['dim_count']} 天\n"
        f"亮暗比例: {stats['bright_ratio']:.0%} 的夜晚星光满溢或明亮\n\n"
        f"每日记录:\n{entries_text}\n\n"
        f"本月出现最多的卡牌: {top_cards_text}\n\n"
        f"本月新/满月天象: {astral_text}\n\n"
        "请严格按照以下 JSON 格式回复，不要包含任何多余内容：\n"
        "{\n"
        '  "trend_summary": "用一句话总结本月情绪与星光状态，只描述夜空状态本身，'
        '绝不下"越来越好/越来越糟"这类定性结论（例如：这个月的夜空由静默渐次点亮，'
        '明亮的夜晚多于微暗的夜晚）",\n'
        '  "insight": "基于用户的星光记录与卡牌，生成一句有启发性的洞察（50字以内，'
        '温暖而深刻，像了解用户的老朋友）",\n'
        '  "next_guide": "为下个月给出具体的行动指引和心灵建议（80字以内，可操作的建议）"\n'
        "}"
    )

    try:
        client = _get_ai_client()  # 在 try 内：客户端构造失败同样走降级
        if client is None:
            return None
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=settings.AI_MAX_TOKENS,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一位温柔睿智的星光手账分析师，精通情绪分析和卡牌解读。"
                        "回复必须只输出纯 JSON 对象，不含任何 markdown 代码块标记或其他文字。"
                    ) + _OUTPUT_RED_LINE,
                },
                {"role": "user", "content": user_prompt},
            ],
            timeout=60.0,
        )
        content = response.choices[0].message.content
        data = _parse_ai_json(content)
        if data is None:
            logger.warning("月度复盘 AI 返回非 JSON，降级本地文案: %s", (content or "")[:200])
            return None
        return {
            "trend_summary": _sanitize((data.get("trend_summary") or "").strip()),
            "insight": _sanitize((data.get("insight") or "").strip()),
            "next_guide": _sanitize((data.get("next_guide") or "").strip()),
        }
    except Exception as exc:
        logger.warning("月度复盘 AI 生成失败，降级本地文案: %s", exc)
        return None
