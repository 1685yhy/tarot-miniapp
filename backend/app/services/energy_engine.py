"""
星座能量引擎 — 确定性规则引擎（同日同人恒定、可解释）。

七步流水线：
  1. 生物节律正弦（体力 23 天 / 情绪 28 天 / 思维 33 天，从出生日期起算；
     无出生日期时用 user.created_at 近似）
  2. 星座常量偏移（12 星座 × 4 维固定表，人工定稿）
  3. 天文事件表（2026 全年 ~50 条常量：新月/满月/水逆/金星逆行/日月食/节气）
  4. 塔罗牌偏移（78 张 × 4 维：大牌按牌义定稿、小牌按花色规则）
  5. 日记情绪修正（近 7 天 reflection 关键词）
  6. 归一化：clamp [35, 98] + 四舍五入到个位（非整十）
  7. 平滑：与昨日值差 ≤ 15（超限收敛到 ±15 内）

每维输出 factors 解释链（用户问"为什么"时有答案）。

文案红线：不预测 / 不恐吓 / 不命运定性 / 健康只说照顾自己。
"""

import math
from datetime import date, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# 常量定义
# ─────────────────────────────────────────────────────────────────────────────

DIM_LOVE = "love"        # 爱情
DIM_CAREER = "career"    # 事业
DIM_SOCIAL = "social"    # 人际
DIM_HEALTH = "health"    # 健康
DIMS = (DIM_LOVE, DIM_CAREER, DIM_SOCIAL, DIM_HEALTH)

DIM_NAMES_ZH = {
    DIM_LOVE: "爱情",
    DIM_CAREER: "事业",
    DIM_SOCIAL: "人际",
    DIM_HEALTH: "健康",
}

MIN_ENERGY = 35
MAX_ENERGY = 98
MAX_DAY_DELTA = 15  # 第 7 步：平滑约束，与昨日差值上限

# 生物节律周期（天）
BIORHYTHM_PERIODS = {
    DIM_LOVE: 28,    # 情绪
    DIM_CAREER: 33,  # 思维
    DIM_HEALTH: 23,  # 体力
}
# 人际维度无独立生物曲线，基线 50

# ─────────────────────────────────────────────────────────────────────────────
# 第 2 步：十二星座常量偏移（12 星座 × 4 维，人工定稿）
# ─────────────────────────────────────────────────────────────────────────────

ZODIAC_OFFSETS: dict[str, dict[str, int]] = {
    "aries":       {DIM_LOVE: 0, DIM_CAREER: 4, DIM_SOCIAL: 2, DIM_HEALTH: 0},
    "taurus":      {DIM_LOVE: 0, DIM_CAREER: 2, DIM_SOCIAL: 0, DIM_HEALTH: 3},
    "gemini":      {DIM_LOVE: 0, DIM_CAREER: 0, DIM_SOCIAL: 4, DIM_HEALTH: 0},
    "cancer":      {DIM_LOVE: 3, DIM_CAREER: 0, DIM_SOCIAL: 0, DIM_HEALTH: -2},
    "leo":         {DIM_LOVE: 2, DIM_CAREER: 3, DIM_SOCIAL: 0, DIM_HEALTH: 0},
    "virgo":       {DIM_LOVE: 0, DIM_CAREER: 2, DIM_SOCIAL: 0, DIM_HEALTH: 3},
    "libra":       {DIM_LOVE: 3, DIM_CAREER: 0, DIM_SOCIAL: 4, DIM_HEALTH: 0},
    "scorpio":     {DIM_LOVE: 3, DIM_CAREER: 2, DIM_SOCIAL: 0, DIM_HEALTH: 0},
    "sagittarius": {DIM_LOVE: 0, DIM_CAREER: 3, DIM_SOCIAL: 2, DIM_HEALTH: 0},
    "capricorn":   {DIM_LOVE: 0, DIM_CAREER: 4, DIM_SOCIAL: 0, DIM_HEALTH: 0},
    # 水瓶：人际 +3（"思维"并入事业维 +1，四维模型无独立思维维）
    "aquarius":    {DIM_LOVE: 0, DIM_CAREER: 1, DIM_SOCIAL: 3, DIM_HEALTH: 0},
    "pisces":      {DIM_LOVE: 4, DIM_CAREER: 0, DIM_SOCIAL: 0, DIM_HEALTH: -2},
}

ZODIAC_NAMES_ZH = {
    "aries": "白羊座", "taurus": "金牛座", "gemini": "双子座", "cancer": "巨蟹座",
    "leo": "狮子座", "virgo": "处女座", "libra": "天秤座", "scorpio": "天蝎座",
    "sagittarius": "射手座", "capricorn": "摩羯座", "aquarius": "水瓶座",
    "pisces": "双鱼座",
}

# ─────────────────────────────────────────────────────────────────────────────
# 第 3 步：2026 天文事件表（~50 条常量，含日期/类型/影响/文案）
# ─────────────────────────────────────────────────────────────────────────────

# 事件类型 → 影响（4 维偏移）与一句话文案
ASTRAL_TYPE_IMPACTS: dict[str, dict[str, int]] = {
    "new_moon":           {DIM_CAREER: 8},                       # 新月 → 事业 +8"新开始"
    "full_moon":          {DIM_LOVE: 6, DIM_HEALTH: -3},         # 满月 → 爱情 +6、健康 -3
    "mercury_retrograde": {DIM_SOCIAL: -8, DIM_CAREER: -5},      # 水逆 → 人际 -8、事业 -5
    "venus_retrograde":   {DIM_LOVE: -8},                        # 金星逆行 → 爱情 -8
    "solar_eclipse":      {DIM_CAREER: 5, DIM_SOCIAL: -5},       # 日食 → 事业 +5、人际 -5
    "lunar_eclipse":      {DIM_CAREER: 5, DIM_SOCIAL: -5},       # 月食 → 事业 +5、人际 -5
    "solar_term":         {DIM_HEALTH: 3},                       # 节气 → 健康 +3
}

ASTRAL_TYPE_FACTOR_NAME = {
    "new_moon": "新月",
    "full_moon": "满月",
    "mercury_retrograde": "水逆",
    "venus_retrograde": "金星逆行",
    "solar_eclipse": "日食",
    "lunar_eclipse": "月食",
    "solar_term": "节气",
}

ASTRAL_TYPE_NOTES = {
    "new_moon": "新月开启新的能量周期，适合许愿与启程。",
    "full_moon": "满月照见情绪深处，适合表达与放下。",
    "mercury_retrograde": "水逆期间沟通易有波折，重要决定请三思再行。",
    "venus_retrograde": "金星逆行，旧人旧事容易浮现，让一切慢慢来。",
    "solar_eclipse": "日食带来新的开始，适合种下新的愿望。",
    "lunar_eclipse": "月食让情绪与关系浮出水面，是整理内心的好时机。",
    "solar_term": "节气更替，身体顺应自然，宜早睡与休息。",
}

# 同日多事件时的展示优先级（越大越优先）
ASTRAL_TYPE_PRIORITY = {
    "solar_eclipse": 7, "lunar_eclipse": 6, "new_moon": 5, "full_moon": 4,
    "mercury_retrograde": 3, "venus_retrograde": 2, "solar_term": 1,
}

_ZODIAC_SIGNS = ["白羊", "金牛", "双子", "巨蟹", "狮子", "处女", "天秤", "天蝎", "射手", "摩羯", "水瓶", "双鱼"]

# 已知 2026 新/满月 的月亮落座（用于天象小字；其余日期用确定性近似公式）
_MOON_SIGNS = {
    "2026-01-03": "摩羯", "2026-01-11": "巨蟹", "2026-02-17": "狮子",
    "2026-03-14": "处女", "2026-03-29": "白羊", "2026-04-28": "天蝎",
    "2026-05-12": "金牛", "2026-05-26": "射手", "2026-06-12": "双子",
    "2026-06-22": "摩羯", "2026-07-11": "巨蟹", "2026-07-24": "水瓶",
    "2026-08-12": "狮子", "2026-09-11": "处女", "2026-09-27": "白羊",
    "2026-10-07": "白羊", "2026-11-05": "天蝎", "2026-11-21": "金牛",
    "2026-12-02": "射手",
}

# 2026 二十四节气（公历日期）
_SOLAR_TERMS_2026 = [
    ("2026-01-05", "小寒"), ("2026-01-20", "大寒"), ("2026-02-04", "立春"),
    ("2026-02-19", "雨水"), ("2026-03-06", "惊蛰"), ("2026-03-21", "春分"),
    ("2026-04-05", "清明"), ("2026-04-20", "谷雨"), ("2026-05-06", "立夏"),
    ("2026-05-21", "小满"), ("2026-06-06", "芒种"), ("2026-06-21", "夏至"),
    ("2026-07-07", "小暑"), ("2026-07-23", "大暑"), ("2026-08-08", "立秋"),
    ("2026-08-23", "处暑"), ("2026-09-08", "白露"), ("2026-09-23", "秋分"),
    ("2026-10-08", "寒露"), ("2026-10-23", "霜降"), ("2026-11-07", "立冬"),
    ("2026-11-22", "小雪"), ("2026-12-07", "大雪"), ("2026-12-22", "冬至"),
]

# 已知天文事件（2026 全年；新月/满月/日月食/水逆/金星逆行 定稿日期）
_KNOWN_EVENTS = [
    # (日期, 类型, 标签后缀, 月亮落座可选)
    ("2026-01-03", "new_moon", "摩羯新月", "摩羯"),
    ("2026-01-11", "full_moon", "满月", "巨蟹"),
    ("2026-01-14", "mercury_retrograde", "水瓶水逆", None),
    ("2026-02-17", "full_moon", "满月", "狮子"),
    ("2026-03-14", "full_moon", "处女满月", "处女"),
    ("2026-03-14", "lunar_eclipse", "处女满月月食", None),
    ("2026-03-29", "new_moon", "白羊新月", "白羊"),
    ("2026-03-29", "solar_eclipse", "白羊新月日食", None),
    ("2026-03-30", "mercury_retrograde", "白羊水逆", None),
    ("2026-04-28", "full_moon", "天蝎满月", "天蝎"),
    ("2026-05-12", "new_moon", "金牛新月", "金牛"),
    ("2026-05-26", "full_moon", "满月", "射手"),
    ("2026-06-12", "new_moon", "双子新月", "双子"),
    ("2026-06-22", "full_moon", "满月", "摩羯"),
    ("2026-07-11", "new_moon", "巨蟹新月", "巨蟹"),
    ("2026-07-24", "full_moon", "满月", "水瓶"),
    ("2026-08-12", "new_moon", "狮子座新月", "狮子"),
    ("2026-08-12", "solar_eclipse", "狮子座日全食", None),
    ("2026-09-11", "new_moon", "处女新月", "处女"),
    ("2026-09-18", "mercury_retrograde", "天秤水逆", None),
    ("2026-09-27", "full_moon", "满月", "白羊"),
    ("2026-10-07", "full_moon", "白羊满月", "白羊"),
    ("2026-11-05", "new_moon", "天蝎新月", "天蝎"),
    ("2026-11-21", "full_moon", "满月", "金牛"),
    ("2026-12-02", "new_moon", "射手新月", "射手"),
    # 补充逆行区间
    ("2026-03-02", "venus_retrograde", "金星逆行", None),
    ("2026-06-29", "mercury_retrograde", "巨蟹水逆", None),
]

# 水逆/金星逆行的结束日期（区间事件）
_RETROGRADE_ENDS = {
    "2026-01-14": "2026-02-04",
    "2026-03-02": "2026-04-14",
    "2026-03-30": "2026-04-22",
    "2026-06-29": "2026-07-22",
    "2026-09-18": "2026-10-10",
}


def _parse(d: str) -> date:
    return date.fromisoformat(d)


def _build_astral_events() -> list[dict]:
    """构建 2026 全年天文事件表（含节气，约 50 条）。"""
    events: list[dict] = []
    for day, etype, label, moon_sign in _KNOWN_EVENTS:
        end = _RETROGRADE_ENDS.get(day)
        events.append({
            "start": _parse(day),
            "end": _parse(end) if end else None,
            "type": etype,
            "label": label,
            "moon_sign": moon_sign,
        })
    for day, term in _SOLAR_TERMS_2026:
        events.append({
            "start": _parse(day),
            "end": None,
            "type": "solar_term",
            "label": f"节气 · {term}",
            "moon_sign": None,
        })
    return events


ASTRAL_EVENTS_2026 = _build_astral_events()


# ─────────────────────────────────────────────────────────────────────────────
# 第 4 步：塔罗牌偏移表（78 张 × 4 维）
# ─────────────────────────────────────────────────────────────────────────────

# 22 张大阿卡纳按 card_number(0-21) 定稿（基于牌义）
MAJOR_TAROT_OFFSETS: dict[int, dict[str, int]] = {
    0:  {DIM_LOVE: 1, DIM_CAREER: 2},          # 愚者 — 新起点
    1:  {DIM_CAREER: 2, DIM_SOCIAL: 1},        # 魔术师 — 主动创造
    2:  {DIM_LOVE: 1, DIM_CAREER: 1},          # 女祭司 — 直觉
    3:  {DIM_LOVE: 3, DIM_HEALTH: 1},          # 皇后 — 温柔丰盛
    4:  {DIM_CAREER: 3, DIM_SOCIAL: 1},        # 皇帝 — 稳固推进
    5:  {DIM_SOCIAL: 3, DIM_CAREER: 1},        # 教皇 — 贵人提点
    6:  {DIM_LOVE: 3, DIM_SOCIAL: 1},          # 恋人 — 联结
    7:  {DIM_CAREER: 3},                       # 战车 — 意志力
    8:  {DIM_SOCIAL: 2, DIM_HEALTH: 1},        # 力量 — 温柔坚定
    9:  {DIM_CAREER: 1, DIM_SOCIAL: -1},       # 隐士 — 独处蓄力
    10: {DIM_CAREER: 2, DIM_LOVE: 1},          # 命运之轮 — 转机
    11: {DIM_CAREER: 2, DIM_SOCIAL: 1},        # 正义 — 平衡决断
    12: {DIM_CAREER: 1},                       # 倒吊人 — 换视角
    13: {DIM_CAREER: 2, DIM_HEALTH: -1},       # 死神 — 焕新（非恐吓，仅"转变"）
    14: {DIM_HEALTH: 3, DIM_SOCIAL: 1},        # 节制 — 身心调和
    15: {DIM_CAREER: 1, DIM_HEALTH: -1},       # 恶魔 — 克制提醒
    16: {DIM_CAREER: 2, DIM_SOCIAL: -2},       # 高塔 — 变化
    17: {DIM_LOVE: 2, DIM_HEALTH: 1},          # 星星 — 希望
    18: {DIM_LOVE: 3, DIM_HEALTH: -2},         # 月亮 — 朦胧感受（定稿：爱情+3 健康-2）
    19: {DIM_LOVE: 3, DIM_CAREER: 3},          # 太阳 — 明亮丰盈（定稿：爱情+3 事业+3）
    20: {DIM_CAREER: 2, DIM_SOCIAL: 1},        # 审判 — 复盘新生
    21: {DIM_CAREER: 2, DIM_LOVE: 1},          # 世界 — 圆满
}

# 小阿卡纳按花色规则：权杖→事业+2；圣杯→爱情+2；宝剑→人际-1 思维+2(并入事业)；
# 星币→健康+2（星币九→健康+2）
MINOR_SUIT_OFFSETS: dict[str, dict[str, int]] = {
    "wands":     {DIM_CAREER: 2},
    "cups":      {DIM_LOVE: 2},
    "swords":    {DIM_SOCIAL: -1, DIM_CAREER: 1},
    "pentacles": {DIM_HEALTH: 2},
}


# ─────────────────────────────────────────────────────────────────────────────
# 第 5 步：日记情绪关键词（近 7 天 reflection）
# ─────────────────────────────────────────────────────────────────────────────

DIARY_NEGATIVE_WORDS = ("累", "难过", "焦虑", "疲惫", "失眠", "崩溃", "压力")
DIARY_HAPPY_WORDS = ("开心", "高兴", "快乐", "幸福", "满足")
DIARY_SMOOTH_WORDS = ("顺利", "成功", "突破", "进步")
DIARY_WORK_WORDS = ("工作", "加班", "项目", "开会", "汇报")


# ─────────────────────────────────────────────────────────────────────────────
# 第 3 步辅助：月相 / 月亮落座（确定性近似，仅用于无事件日的天象小字）
# ─────────────────────────────────────────────────────────────────────────────

# 2026-01-03 为已知新月（引擎纪元）
_EPOCH_NEW_MOON = _parse("2026-01-03")
_SYNODIC_MONTH = 29.530588

MOON_PHASES = [
    ("new_moon", "新月"), ("waxing_crescent", "娥眉月"), ("first_quarter", "上弦月"),
    ("waxing_gibbous", "盈凸月"), ("full_moon", "满月"), ("waning_gibbous", "亏凸月"),
    ("last_quarter", "下弦月"), ("waning_crescent", "残月"),
]


def moon_phase_on(target: date) -> str:
    """确定性月相（无事件日的天象展示用）。"""
    progress = ((target - _EPOCH_NEW_MOON).days % _SYNODIC_MONTH) / _SYNODIC_MONTH
    idx = int(progress * 8) % 8
    return MOON_PHASES[idx][0]


def moon_sign_on(target: date) -> str:
    """确定性月亮落座近似（月行 12 宫约 27.3 天，每宫约 2.3 天）。"""
    day_idx = (target - _parse("2026-01-01")).days
    return _ZODIAC_SIGNS[int((day_idx * 12.37) % 12)]


def astral_events_on(target: date) -> list[dict]:
    """返回命中目标日期的天文事件列表（含区间事件）。"""
    hits = []
    for ev in ASTRAL_EVENTS_2026:
        if ev["start"] <= target <= (ev["end"] or ev["start"]):
            hits.append(ev)
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# 今日星光卡（Task 3 · 星象宜忌引擎）：星光色 / 星光数 / 星象宜忌
# ─────────────────────────────────────────────────────────────────────────────

# 星光色盘（12 色，暖金/细金系 + 星彩色；由日期确定性派生）
STAR_COLORS = [
    "#A98B5F",  # 星光金
    "#E8C97E",  # 暖金
    "#D9B48F",  # 沙金
    "#C7B89F",  # 米金
    "#B8A6D9",  # 星雾紫
    "#8FAED6",  # 星云蓝
    "#A8C0D9",  # 银河蓝
    "#9FC7A8",  # 月影绿
    "#7FA8B8",  # 海雾青
    "#E7A8B8",  # 霞光粉
    "#C9A9A6",  # 玫瑰金
    "#D6C2A0",  # 月华金
]

# 天文事件 → 宜忌（绑定真实天象，有出处；全部积极开放向，禁 必/绝对/改运/化解/转运/注定）
GUIDANCE_BY_EVENT: dict[str, tuple[str, str]] = {
    "new_moon":           ("宜·许下心愿", "忌·急于求成"),
    "full_moon":          ("宜·复盘整理", "忌·冲动决定"),
    "mercury_retrograde": ("宜·慢下来", "忌·重大签约"),
    "venus_retrograde":   ("宜·重温美好", "忌·翻旧账"),
    "solar_eclipse":      ("宜·开启新篇", "忌·原地打转"),
    "lunar_eclipse":      ("宜·整理内心", "忌·把话憋着"),
    "solar_term":         ("宜·顺应节奏", "忌·熬夜透支"),
}

# 无事件日中性宜忌（随日期轮换，同样积极开放向）
NEUTRAL_GUIDANCE: list[tuple[str, str]] = [
    ("宜·表达心意", "忌·独自纠结"),
    ("宜·往前一小步", "忌·计划排太满"),
    ("宜·给自己留白", "忌·和他人比较"),
    ("宜·温柔待己", "忌·苛责自己"),
    ("宜·早睡早醒", "忌·过度消耗"),
]

# 宜忌文案库全集（事件 + 中性），供测试校验条数 ≥ 12 与禁用词
STAR_GUIDANCE_LIBRARY: list[tuple[str, str]] = list(GUIDANCE_BY_EVENT.values()) + NEUTRAL_GUIDANCE


def build_today_guidance(target: date, zodiac: str | None = None) -> dict:
    """
    今日星光卡数据（确定性：同日同人恒定）。

    返回::
        {
            "star_color": "#A98B5F",   # 12 色暖金系色盘，日期（+星座）派生
            "star_number": 7,           # 日期数字和 mod 9 + 1（1-9，仅由日期决定）
            "advice_do": "宜·许下心愿", # 有事件按事件类型绑定，无事件用中性池轮换
            "advice_dont": "忌·急于求成",
        }
    """
    date_seed = sum(int(ch) for ch in target.isoformat() if ch.isdigit())
    mix_seed = date_seed + (sum(ord(ch) for ch in zodiac) if zodiac else 0)

    events = astral_events_on(target)
    if events:
        # 同日多事件 → 按展示优先级取最高者决定宜忌（与能量引擎 astral 展示一致）
        primary = sorted(events, key=lambda e: ASTRAL_TYPE_PRIORITY.get(e["type"], 0), reverse=True)[0]
        advice_do, advice_dont = GUIDANCE_BY_EVENT.get(primary["type"], NEUTRAL_GUIDANCE[0])
    else:
        advice_do, advice_dont = NEUTRAL_GUIDANCE[date_seed % len(NEUTRAL_GUIDANCE)]

    return {
        "star_color": STAR_COLORS[mix_seed % len(STAR_COLORS)],
        "star_number": date_seed % 9 + 1,
        "advice_do": advice_do,
        "advice_dont": advice_dont,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 第 1 步：生物节律正弦
# ─────────────────────────────────────────────────────────────────────────────

def biorhythm_on(days_since_birth: int) -> dict[str, float]:
    """体力/情绪/思维三条正弦曲线，返回 4 维基值（人际无独立曲线，取 50）。"""
    values: dict[str, float] = {DIM_SOCIAL: 50.0}
    for dim, period in BIORHYTHM_PERIODS.items():
        values[dim] = 50.0 + 25.0 * math.sin(2.0 * math.pi * days_since_birth / period)
    return values


# ─────────────────────────────────────────────────────────────────────────────
# 第 6 / 7 步：归一化与平滑
# ─────────────────────────────────────────────────────────────────────────────

def normalize(raw: dict[str, float]) -> dict[str, int]:
    """clamp [35, 98] + 四舍五入到个位（非整十）。"""
    return {
        dim: min(MAX_ENERGY, max(MIN_ENERGY, round(value)))
        for dim, value in raw.items()
    }


def smooth(values: dict[str, int], yesterday: dict[str, int] | None) -> dict[str, int]:
    """与昨日值差 ≤ 15，超限收敛到 ±15 内；无昨日记录则原样返回。"""
    if not yesterday:
        return values
    out = {}
    for dim in DIMS:
        v = values[dim]
        y = yesterday.get(dim, v)
        if v - y > MAX_DAY_DELTA:
            v = y + MAX_DAY_DELTA
        elif y - v > MAX_DAY_DELTA:
            v = y - MAX_DAY_DELTA
        out[dim] = v
    return out


# ─────────────────────────────────────────────────────────────────────────────
# summary / tip 规则模板（不预测 / 不恐吓）
# ─────────────────────────────────────────────────────────────────────────────

_DIM_LEVEL_SUMMARY = {
    DIM_LOVE: {
        (80, 99): "爱情能量正盛，心里有光",
        (65, 79): "爱情能量平稳向好",
        (50, 64): "爱情能量中等，适合慢慢来",
        (35, 49): "爱情能量偏低，先照顾好自己的心情",
    },
    DIM_CAREER: {
        (80, 99): "事业能量强劲，适合推进",
        (65, 79): "事业能量平稳向上",
        (50, 64): "事业能量中等，按自己的节奏走",
        (35, 49): "事业能量偏低，允许自己缓一缓",
    },
    DIM_SOCIAL: {
        (80, 99): "人际能量充沛，适合联结与表达",
        (65, 79): "人际能量顺遂",
        (50, 64): "人际能量平稳，先观察再靠近",
        (35, 49): "人际能量偏低，独处也是蓄力",
    },
    DIM_HEALTH: {
        (80, 99): "身体状态轻盈",
        (65, 79): "身体状态不错",
        (50, 64): "精力平稳，记得劳逸结合",
        (35, 49): "今天身体容易累，请把休息当功课",
    },
}

_DIM_TIPS = {
    DIM_LOVE: "把最想对一个人说的话写进日记，不用发出去——写完，就是回应。",
    DIM_CAREER: "列出今天最重要的三件事，只完成第一件，然后认真夸自己一句。",
    DIM_SOCIAL: "给一位久未联系、却偶尔会想起的人，发一句「最近好吗」。",
    DIM_HEALTH: "现在放下手机，做三次很慢很长的呼吸，让肩膀先松下来。",
}


def _level_text(dim: str, value: int) -> str:
    for (lo, hi), text in _DIM_LEVEL_SUMMARY[dim].items():
        if lo <= value <= hi:
            return text
    return _DIM_LEVEL_SUMMARY[dim][(35, 49)]


def build_summary_tip(
    energy: dict[str, int],
    astral_label: str | None,
    tarot_name: str | None,
) -> tuple[str, str]:
    """规则生成一句话总评 + 30 秒微行动（先不调 AI，控制成本）。"""
    ordered = sorted(DIMS, key=lambda d: energy[d], reverse=True)
    strongest, weakest = ordered[0], ordered[-1]

    parts = [f"今日{DIM_NAMES_ZH[strongest]}能量最盛——{_level_text(strongest, energy[strongest])}。"]
    if astral_label:
        parts.append(f"天象正值{astral_label}。")
    if tarot_name:
        parts.append(f"今日塔罗「{tarot_name}」也在轻轻为你留灯。")
    parts.append(f"{DIM_NAMES_ZH[weakest]}维度稍微需要留意：{_level_text(weakest, energy[weakest])}，温柔对待自己就好。")
    return "".join(parts), _DIM_TIPS[weakest]


# ─────────────────────────────────────────────────────────────────────────────
# 核心：能量计算
# ─────────────────────────────────────────────────────────────────────────────

def compute_energy(
    *,
    target_date: date,
    birth_date: date,
    zodiac: str | None = None,
    tarot_card: object | None = None,      # TarotCard ORM：需 card_number/arcana/suit/name_zh/name_en
    diary_texts: list[str] | None = None,  # 近 7 天 reflection 文本列表
    yesterday: dict[str, int] | None = None,
) -> dict:
    """
    确定性计算指定日期的 4 维能量 + 解释链。

    返回::
        {
            "energy": {love: 81, career: 73, social: 64, health: 57},
            "factors": {love: [{"name": "满月", "delta": 6}, ...], ...},
            "astral": {"type": "full_moon", "label": "满月 · 月亮在白羊", "note": "..."},
            "summary": "一句话总评",
            "tip": "30 秒微行动",
        }
    """
    diary_texts = diary_texts or []

    # ── 第 1 步：生物节律 ──
    days_since_birth = (target_date - birth_date).days
    raw = biorhythm_on(days_since_birth)
    factors: dict[str, list[dict]] = {dim: [] for dim in DIMS}

    # ── 第 2 步：星座常量偏移 ──
    if zodiac and zodiac in ZODIAC_OFFSETS:
        zodiac_name = ZODIAC_NAMES_ZH.get(zodiac, zodiac)
        for dim, delta in ZODIAC_OFFSETS[zodiac].items():
            if delta:
                raw[dim] += delta
                factors[dim].append({"name": zodiac_name, "delta": delta})

    # ── 第 3 步：天文事件 ──
    events = astral_events_on(target_date)
    if events:
        for ev in sorted(events, key=lambda e: ASTRAL_TYPE_PRIORITY.get(e["type"], 0), reverse=True):
            etype = ev["type"]
            factor_name = ASTRAL_TYPE_FACTOR_NAME.get(etype, ev["label"])
            for dim, delta in ASTRAL_TYPE_IMPACTS.get(etype, {}).items():
                if delta:
                    raw[dim] += delta
                    factors[dim].append({"name": factor_name, "delta": delta})

    # 天象小字：有事件用事件（含月亮落座），无事件用确定性月相近似
    if events:
        primary = sorted(events, key=lambda e: ASTRAL_TYPE_PRIORITY.get(e["type"], 0), reverse=True)[0]
        astral_label_parts = [primary["label"]]
        moon_sign = primary.get("moon_sign") or moon_sign_on(target_date)
        astral_label_parts.append(f"月亮在{moon_sign}")
        astral = {
            "type": primary["type"],
            "label": " · ".join(astral_label_parts),
            "note": ASTRAL_TYPE_NOTES.get(primary["type"], ""),
        }
    else:
        phase_key = moon_phase_on(target_date)
        phase_name = dict(MOON_PHASES)[phase_key]
        astral = {
            "type": phase_key,
            "label": f"{phase_name} · 月亮在{moon_sign_on(target_date)}",
            "note": "今日天象平稳，把注意力放在自己真正想做的事上。",
        }

    # ── 第 4 步：塔罗牌偏移 ──
    if tarot_card is not None:
        offsets: dict[str, int] = {}
        if getattr(tarot_card, "arcana", None) == "major":
            offsets = MAJOR_TAROT_OFFSETS.get(getattr(tarot_card, "card_number", -1), {})
        else:
            suit = getattr(tarot_card, "suit", None)
            offsets = MINOR_SUIT_OFFSETS.get(suit, {}) if suit else {}
        for dim, delta in offsets.items():
            if delta:
                raw[dim] += delta
                factors[dim].append({"name": getattr(tarot_card, "name_zh", "塔罗"), "delta": delta})

    # ── 第 5 步：日记情绪修正（近 7 天）──
    joined = " ".join(text or "" for text in diary_texts)
    if joined:
        if any(w in joined for w in DIARY_NEGATIVE_WORDS):
            raw[DIM_HEALTH] -= 5
            raw[DIM_LOVE] -= 3
            factors[DIM_HEALTH].append({"name": "日记:低落", "delta": -5})
            factors[DIM_LOVE].append({"name": "日记:低落", "delta": -3})
        if any(w in joined for w in DIARY_HAPPY_WORDS):
            raw[DIM_LOVE] += 4
            factors[DIM_LOVE].append({"name": "日记:开心", "delta": 4})
        if any(w in joined for w in DIARY_SMOOTH_WORDS):
            raw[DIM_CAREER] += 4
            factors[DIM_CAREER].append({"name": "日记:顺利", "delta": 4})
        if any(w in joined for w in DIARY_WORK_WORDS):
            raw[DIM_CAREER] += 3
            factors[DIM_CAREER].append({"name": "日记:工作", "delta": 3})

    # ── 第 6 步：归一化（clamp + 取整）──
    energy = normalize(raw)

    # ── 第 7 步：平滑（与昨日差 ≤ 15）──
    energy = smooth(energy, yesterday)
    energy = normalize(energy)  # 平滑后再钳一次，保证落回 [35, 98]

    # ── summary / tip（规则模板）──
    astral_label = astral["label"].split(" · ")[0] if astral else None
    tarot_name = getattr(tarot_card, "name_zh", None) if tarot_card else None
    summary, tip = build_summary_tip(energy, astral_label, tarot_name)

    return {
        "energy": energy,
        "factors": factors,
        "astral": astral,
        "summary": summary,
        "tip": tip,
    }
