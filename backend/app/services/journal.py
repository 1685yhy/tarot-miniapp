"""星光手账（Journal）服务层：星光亮度映射 + 连续记录 + 月历聚合。

T1-1（SDD P1 · 星光手账）：亮度映射为代码常量不落库；star_color 由
``build_today_guidance`` 按日期确定性生成，同样不落库（免存储免同步）。
"""

from datetime import date, timedelta

from app.services.energy_engine import build_today_guidance

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
