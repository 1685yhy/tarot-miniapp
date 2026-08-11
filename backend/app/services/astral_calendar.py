"""
星空时刻表（SDD P1 · T3-1）— 星象日历 / 日详情 / 节点内容纯函数服务。

数据源零新增：直接复用 energy_engine 的 ASTRAL_EVENTS_2026（~50 条常量 +
逆行区间）、astral_events_on、ASTRAL_TYPE_NOTES / GUIDANCE_BY_EVENT /
ASTRAL_TYPE_PRIORITY / NEUTRAL_GUIDANCE，以及 moon.py 的 moon_phase_on
（月相小字）与 next_new_moon_after（2027+ 无表数据时的许愿窗口回退）。

全部纯函数、日期参数化，便于确定性测试：
- month_view(year, month, today)       月视图：每日月相小字 + 事件 + 逆行区间标记
- day_detail(target)                   日详情：事件 note + 宜忌 + 节点活动形态
- node_content(node_type, today, wish_counts)  节点打卡内容（许愿/复盘/水逆指南/资讯）

文案红线：积极开放向，禁「化解/转运」类用语（黑名单词扫描在测试中覆盖）。
"""

from datetime import date, timedelta

from app.services.energy_engine import (
    ASTRAL_EVENTS_2026,
    ASTRAL_TYPE_NOTES,
    ASTRAL_TYPE_PRIORITY,
    GUIDANCE_BY_EVENT,
    NEUTRAL_GUIDANCE,
    astral_events_on,
)
from app.services.moon import moon_phase_on, next_new_moon_after

# 事件类型 → 节点活动形态（activity；由同日最高优先级事件决定）
NODE_TYPE_BY_EVENT = {
    "new_moon": "wish",
    "full_moon": "review",
    "mercury_retrograde": "mercury_guide",
}
DEFAULT_NODE_TYPE = "info"

# 区间事件类型（日历上需要「展开到每一天」的逆行区间）
RETROGRADE_TYPES = frozenset({"mercury_retrograde", "venus_retrograde"})

# 许愿窗口：新月日 00:00 起至其后 2 天
WISH_WINDOW_DAYS = 2

# range 空态规格（简报未定义空态 → 规格化：无逆行期时显式空对象，range 键恒在）
EMPTY_RETROGRADE_RANGE = {"start": "", "end": "", "days_left": 0}

# 水逆「自我关怀指南」固定清单（≥7 条，积极开放向，无黑名单词）
MERCURY_CARE_ITEMS = [
    "把重要决定写下来，放一天再读一遍",
    "每一条消息都回慢一点，先想清楚再说",
    "重要文件顺手备份到两个地方",
    "约一位老朋友聊聊近况，只聊开心的事",
    "把大计划拆成今天能完成的最小一步",
    "早一点睡，把夜晚完整留给自己",
    "出门前多看一眼随身物品，从容出发",
    "给自己写三行温柔的鼓励，放在手机壳里",
]

# 水逆期每日一句（确定性轮换池：date_seed % 池长，同日同人恒定）
MERCURY_DAILY_SENTENCES = [
    "慢一点，也是在前进。",
    "今天的节奏由你自己决定。",
    "把大事分成小事，把小事变成行动。",
    "先说出口的话，往往不是最想说的那句。",
    "留白的时间里，常常藏着答案。",
    "风慢下来时，云才有了形状。",
    "多喝一杯温水，多看一眼窗外。",
    "有些消息可以明天再回，有些话可以明天再说。",
    "把计划表收起来，今晚只做让自己安心的事。",
    "水逆不是倒退，是提醒我们重新整理。",
    "温柔对待自己，就像对待一位老朋友。",
    "今天的月亮也在慢慢走，不急。",
]

# info 节点文案（其余事件类型的说明，复用 ASTRAL_TYPE_NOTES）
INFO_NODE_NOTES = [
    ASTRAL_TYPE_NOTES[t]
    for t in ("venus_retrograde", "solar_eclipse", "lunar_eclipse", "solar_term")
]


def _date_seed(d: date) -> int:
    """日期数字和（与 energy_engine 宜忌轮换一致）。"""
    return sum(int(ch) for ch in d.isoformat() if ch.isdigit())


def _sort_events(events: list[dict]) -> list[dict]:
    """按 ASTRAL_TYPE_PRIORITY 降序（同日多事件展示优先级）。"""
    return sorted(
        events,
        key=lambda ev: ASTRAL_TYPE_PRIORITY.get(ev["type"], 0),
        reverse=True,
    )


def _node_type_for(event_type: str) -> str:
    return NODE_TYPE_BY_EVENT.get(event_type, DEFAULT_NODE_TYPE)


# ─────────────────────────────────────────────────────────────────────────────
# 月视图
# ─────────────────────────────────────────────────────────────────────────────


def _next_event_from(today: date) -> dict | None:
    """从 today 起首个事件（start >= today，含当天；当天多事件取优先级最高者）。"""
    candidates = [ev for ev in ASTRAL_EVENTS_2026 if ev["start"] >= today]
    if not candidates:
        return None
    best = min(
        candidates,
        key=lambda ev: (ev["start"], -ASTRAL_TYPE_PRIORITY.get(ev["type"], 0)),
    )
    return {
        "type": best["type"],
        "label": best["label"],
        "date": best["start"].isoformat(),
        "days_until": (best["start"] - today).days,
    }


def month_view(year: int, month: int, today: date | None = None) -> dict:
    """
    月视图（纯函数）：{days, next_event}。

    days 每项：{date, phase: {phase, emoji, label}, events: [{type, label, moon_sign}],
    is_retrograde_range}；区间事件（水逆等）展开到每一天；无事件日也有月相小字。
    next_event = 从 today 起首个事件 start >= today（或今天当天的首个），days_until 纯函数计算。
    """
    today = today or date.today()
    days: list[dict] = []
    d = date(year, month, 1)
    while d.month == month:
        events = astral_events_on(d)
        phase = moon_phase_on(d)
        days.append(
            {
                "date": d.isoformat(),
                "phase": {
                    "phase": phase["phase"],
                    "emoji": phase["emoji"],
                    "label": phase["label"],
                },
                "events": [
                    {
                        "type": ev["type"],
                        "label": ev["label"],
                        "moon_sign": ev.get("moon_sign"),
                    }
                    for ev in _sort_events(events)
                ],
                "is_retrograde_range": any(
                    ev["type"] in RETROGRADE_TYPES for ev in events
                ),
            }
        )
        d += timedelta(days=1)
    return {
        "year": year,
        "month": month,
        "days": days,
        "next_event": _next_event_from(today),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 日详情
# ─────────────────────────────────────────────────────────────────────────────


def day_detail(target: date) -> dict:
    """
    日详情（纯函数）：{date, events: [{type, label, note}], guidance: {do, dont}, activity}。

    note 复用 ASTRAL_TYPE_NOTES；guidance 复用 GUIDANCE_BY_EVENT（无事件日走
    中性宜忌池轮换）；activity 由同日最高优先级事件决定：new_moon→wish、
    full_moon→review、mercury_retrograde→mercury_guide、其余→info。
    """
    events = _sort_events(astral_events_on(target))
    primary = events[0] if events else None
    guidance = GUIDANCE_BY_EVENT.get(primary["type"]) if primary else None
    if guidance is None:
        guidance = NEUTRAL_GUIDANCE[_date_seed(target) % len(NEUTRAL_GUIDANCE)]
    return {
        "date": target.isoformat(),
        "events": [
            {
                "type": ev["type"],
                "label": ev["label"],
                "note": ASTRAL_TYPE_NOTES.get(ev["type"], ""),
            }
            for ev in events
        ],
        "guidance": {"do": guidance[0], "dont": guidance[1]},
        "activity": _node_type_for(primary["type"]) if primary else DEFAULT_NODE_TYPE,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 节点内容（许愿 / 复盘 / 水逆指南 / 资讯）
# ─────────────────────────────────────────────────────────────────────────────


def _wish_window(today: date) -> dict:
    """最近新月窗口：新月日 00:00 至其后 2 天；days_left 从今天倒计。

    优先用 ASTRAL_EVENTS_2026 的定稿新月日；无表数据（2027+）回退月相引擎。
    """
    new_moons = sorted(
        (ev for ev in ASTRAL_EVENTS_2026 if ev["type"] == "new_moon"),
        key=lambda ev: ev["start"],
    )
    start = next(
        (
            ev["start"]
            for ev in new_moons
            if ev["start"] >= today - timedelta(days=WISH_WINDOW_DAYS)
        ),
        None,
    )
    if start is None:
        start = next_new_moon_after(today)
    end = start + timedelta(days=WISH_WINDOW_DAYS)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days_left": (end - today).days,
    }


def _retrograde_range(today: date) -> dict | None:
    """当前（或下一个）水逆区间：{start, end, days_left}；无则 None。

    2026-10-10（末次水逆结束）之后 / 2027 起无表内水逆 → None；node_content
    侧规格化为 EMPTY_RETROGRADE_RANGE，保证响应 range 键恒在。
    """
    retros = sorted(
        (ev for ev in ASTRAL_EVENTS_2026 if ev["type"] == "mercury_retrograde"),
        key=lambda ev: ev["start"],
    )
    target = next(
        (
            ev
            for ev in retros
            if ev["start"] <= today <= (ev["end"] or ev["start"])
        ),
        None,
    )
    if target is None:
        target = next((ev for ev in retros if ev["start"] >= today), None)
    if target is None:
        return None
    end = target["end"] or target["start"]
    return {
        "start": target["start"].isoformat(),
        "end": end.isoformat(),
        "days_left": (end - today).days,
    }


_ZERO_WISH_COUNTS = {"active": 0, "grown": 0, "answered": 0}


def node_content(node_type: str, today: date, wish_counts: dict | None = None) -> dict:
    """
    节点内容（纯函数）：wish / review / mercury_guide / info 四形态。

    - wish → 许愿之夜：窗口（最近新月日 00:00 至其后 2 天）+ 引导语 + 目标页
    - review → 复盘之夜：wish_counts（active/grown/answered，由 API 接 db 传入）
    - mercury_guide → 慢行期：当前/下一水逆区间（无则规格化空对象）+ 自我关怀清单
      + 确定性每日一句
    - info → 资讯：其余事件类型的说明文案列表
    """
    counts = wish_counts or _ZERO_WISH_COUNTS
    if node_type == "wish":
        return {
            "type": "wish",
            "title": "许愿之夜",
            "window": _wish_window(today),
            "content": "写给月亮的三行愿望",
            "target_page": "pages/wish/wish",
            "wish_counts": counts,
        }
    if node_type == "review":
        return {
            "type": "review",
            "title": "复盘之夜",
            "wish_counts": counts,
            "target_page": "pages/review/review",
        }
    if node_type == "mercury_guide":
        return {
            "type": "mercury_guide",
            "title": "慢行期",
            "range": _retrograde_range(today) or EMPTY_RETROGRADE_RANGE,
            "items": list(MERCURY_CARE_ITEMS),
            "daily_sentence": MERCURY_DAILY_SENTENCES[
                _date_seed(today) % len(MERCURY_DAILY_SENTENCES)
            ],
        }
    return {"type": "info", "notes": list(INFO_NODE_NOTES)}
