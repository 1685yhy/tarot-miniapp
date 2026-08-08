"""
月相服务 —— 确定性天文算法（无第三方库）。

实现：基于「已知新月锚点 + 朔望月周期」的月龄近似公式。
- 朔望月（synodic month）均值 = 29.530588853 天
- 已知新月锚点 = 2000-01-06 18:14 UTC（天文历书数据，JD 2451550.26）
- 每个新月时刻 = 锚点 + k × 29.530588853 天；满月时刻 = 锚点 + (k+0.5) × 周期。

以「时刻落点」定义关键月相日（新月日 / 满月日 / 上弦 / 下弦 —— 即新月/满月
时刻落在某天的 00:00~24:00 UTC 内），其余日期按月龄落入 waxing / waning。
结论与真实天文对齐在 ±1 天以内（均值周期对真实轨道有毫厘漂移，属本方案
预期的精度）；与真实日食可互验：2000-01-06 新月、2026-08-28 满月（月偏食）
均为精确命中，2026-08-12 日全食落在本方案新月日 ±1 天内。

完全确定性：无随机、无外部依赖、可测试。

主要入口：
- ``moon_phase_on(date)``  → 某天的月相 {phase, emoji, label, age_days, ...}
- ``moon_age_on(date)``   → 月龄（0 ~ 29.53）
- ``next_new_moon_after(date)``  → 之后最近的（方案定义的）新月日期
- ``next_full_moon_after(date)`` → 之后最近的（方案定义的）满月日期
"""

import datetime
import math
from datetime import date, timedelta, timezone

# 朔望月均值（天）
SYNODIC_MONTH = 29.530588853

# 已知新月锚点：2000-01-06 18:14 UTC（标准历书参考新月，JD 2451550.26）
_NEW_MOON_ANCHOR = datetime.datetime(2000, 1, 6, 18, 14, 0, tzinfo=timezone.utc)

_UTC = timezone.utc

# 相位定义：{phase_key: (emoji, label)}
# phase_key 六态：new_moon | waxing | first_quarter | full_moon | last_quarter | waning
PHASE_META = {
    "new_moon": ("🌑", "新月"),
    "waxing": ("🌒", "娥眉月"),
    "first_quarter": ("🌓", "上弦月"),
    "full_moon": ("🌕", "满月"),
    "last_quarter": ("🌗", "下弦月"),
    "waning": ("🌘", "残月"),
}

# 周期内的关键相位偏移（相对于新月时刻，单位：周期占比）
_PHASE_FRACTIONS = {
    "new_moon": 0.0,
    "first_quarter": 0.25,
    "full_moon": 0.5,
    "last_quarter": 0.75,
}

# 满月时刻 ≈ 新月时刻 + 半周期（天）
_HALF_CYCLE_DAYS = SYNODIC_MONTH / 2.0


def _phase_instants_near(d: date) -> list[tuple[str, datetime.datetime]]:
    """返回日期 ``d`` 附近（±1 个周期）所有关键相位时刻。

    每个关键相位（新月/上弦/满月/下弦）在一个周期内只有一个时刻；
    扫描 k-1/k/k+1 三个周期索引 + 4 个相位偏移，防御月龄浮点边界。
    """
    noon = datetime.datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=_UTC)
    days_from_anchor = (noon - _NEW_MOON_ANCHOR).total_seconds() / 86400.0
    k = round(days_from_anchor / SYNODIC_MONTH)
    instants: list[tuple[str, datetime.datetime]] = []
    for cycle in (k - 1, k, k + 1):
        for phase, frac in _PHASE_FRACTIONS.items():
            inst = _NEW_MOON_ANCHOR + timedelta(days=(cycle + frac) * SYNODIC_MONTH)
            instants.append((phase, inst))
    return instants


def _day_contains(d: date, inst: datetime.datetime) -> bool:
    """判断相位时刻 ``inst`` 是否落在日期 ``d``（UTC 00:00~24:00）内。"""
    d0 = datetime.datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_UTC)
    return d0 <= inst < d0 + timedelta(days=1)


def moon_age_on(d: date) -> float:
    """返回日期 ``d`` 中午（UTC）的月龄（0 ~ 29.53，0 = 新月）。"""
    noon = datetime.datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=_UTC)
    days = (noon - _NEW_MOON_ANCHOR).total_seconds() / 86400.0
    age = (days % SYNODIC_MONTH + SYNODIC_MONTH) % SYNODIC_MONTH
    return age


def moon_phase_on(d: date) -> dict:
    """返回日期 ``d`` 的月相信息。

    Returns
    -------
    {
      "date": "2026-08-09",
      "phase": "waning",         # new_moon|waxing|first_quarter|full_moon|last_quarter|waning
      "emoji": "🌘",
      "label": "残月",
      "age_days": 25.7,          # 月龄（天）
      "next_new_moon": "2026-08-13",
      "next_full_moon": "2026-08-28",
    }
    """
    # ── 关键相位日：以相位时刻落点为准 ──
    phase: str | None = None
    for candidate, inst in _phase_instants_near(d):
        if _day_contains(d, inst):
            phase = candidate
            break

    # ── 非关键日：按月龄分入 waxing / waning ──
    age = moon_age_on(d)
    if phase is None:
        phase = "waxing" if age < _HALF_CYCLE_DAYS else "waning"

    emoji, label = PHASE_META[phase]
    return {
        "date": d.isoformat(),
        "phase": phase,
        "emoji": emoji,
        "label": label,
        "age_days": round(age, 1),
        "next_new_moon": next_new_moon_after(d).isoformat(),
        "next_full_moon": next_full_moon_after(d).isoformat(),
    }


def _next_phase_date_after(d: date, frac: float) -> date:
    """返回严格晚于 ``d`` 的最近一个相位（frac 相位偏移）日期。"""
    noon = datetime.datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=_UTC)
    days_from_anchor = (noon - _NEW_MOON_ANCHOR).total_seconds() / 86400.0
    k = math.ceil((days_from_anchor - frac * SYNODIC_MONTH) / SYNODIC_MONTH) - 1
    result: date | None = None
    for offset in (1, 2, 3):  # 最近 1~3 个周期内必有，防御边界
        inst = _NEW_MOON_ANCHOR + timedelta(days=(k + offset + frac) * SYNODIC_MONTH)
        if inst.date() > d:
            result = inst.date()
            break
    if result is None:  # 防御兜底（实际不会走到）
        return d + timedelta(days=int(round(SYNODIC_MONTH)))
    return result


def next_new_moon_after(d: date) -> date:
    """返回严格晚于 ``d`` 的最近一个（方案定义的）新月日期。"""
    return _next_phase_date_after(d, 0.0)


def next_full_moon_after(d: date) -> date:
    """返回严格晚于 ``d`` 的最近一个（方案定义的）满月日期。"""
    return _next_phase_date_after(d, 0.5)
