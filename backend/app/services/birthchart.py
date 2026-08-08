"""
本命星盘三要素计算引擎（星光映照 · 开发 05）。

三大要素：
  1. 太阳星座 —— 出生日期 → 12 星座区间表（与前端 utils/energy.js zodiacFromDate 同算法）。
  2. 月亮星座 —— 预计算查找表（12×30 天矩阵，无出生时间时查表，标注「近似」）；
     填了出生时间 → 用连续公式精化（时间→月亮位置近似公式），仍是近似，但随时刻细化。
  3. 上升星座 —— 需要出生时间；「太阳升起时刻≈上升星座」简化：
     太阳在 6:00（太阳时）升起时上升=太阳星座，此后每 2 小时推进 1 宫；
     出生城市经度换算太阳时（无地点默认东八区 120°E）。无时间返回 None（前端提示补全）。

月亮表生成方法（文档）：
  - 锚点：2026-01-03 00:00 新月（日月合相），月亮黄经 ≈ 太阳黄经 ≈ 283°（摩羯 13°）。
  - 月行平均速度 13.176°/天（恒星月 27.32 天，12.19 星座/月 ≈ 2.5 天/星座）。
  - 矩阵为 2026 年逐日 00:00 的月亮落座；与真实星历的误差允许 ±1 星座
    （真实月亮运动非匀速，最大偏差 ~±3.5° < 30°，落在相邻宫内）。
  - 带出生时间时：lon = 283 + (天数偏移 + 小时/24) × 13.176，按 30°/宫取宫位。

红线：文案不预测 / 不恐吓 / 不诊断 / 非决定论（见 generate_* 的 system prompt）。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────

ZODIAC_KEYS = [
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]

ZODIAC_NAMES_ZH = {
    "aries": "白羊座", "taurus": "金牛座", "gemini": "双子座", "cancer": "巨蟹座",
    "leo": "狮子座", "virgo": "处女座", "libra": "天秤座", "scorpio": "天蝎座",
    "sagittarius": "射手座", "capricorn": "摩羯座", "aquarius": "水瓶座",
    "pisces": "双鱼座",
}

ZODIAC_EMOJI = {
    "aries": "♈", "taurus": "♉", "gemini": "♊", "cancer": "♋",
    "leo": "♌", "virgo": "♍", "libra": "♎", "scorpio": "♏",
    "sagittarius": "♐", "capricorn": "♑", "aquarius": "♒", "pisces": "♓",
}

ROLE_LABELS = {
    "sun": "核心动力",
    "moon": "情绪底色",
    "rising": "他人眼中的我",
}

ROLE_ICONS = {"sun": "☀", "moon": "☽", "rising": "✦"}

# ─────────────────────────────────────────────────────────────────────────────
# 1. 太阳星座（与前端 utils/energy.js zodiacFromDate 同一区间表）
# ─────────────────────────────────────────────────────────────────────────────

# (起始月, 起始日, 星座 key) —— 从该月日起进入此星座（含当日）
SUN_SIGN_RULES = [
    (1, 20, "aquarius"), (2, 19, "pisces"), (3, 21, "aries"), (4, 20, "taurus"),
    (5, 21, "gemini"), (6, 22, "cancer"), (7, 23, "leo"), (8, 23, "virgo"),
    (9, 23, "libra"), (10, 24, "scorpio"), (11, 23, "sagittarius"), (12, 22, "capricorn"),
]


def sun_sign(month: int, day: int) -> str:
    """出生月日 → 太阳星座 key（12 月 22 日及之前为射手，之后为摩羯）。"""
    key = "capricorn"
    for m, d, k in SUN_SIGN_RULES:
        if month > m or (month == m and day >= d):
            key = k
    return key


# ─────────────────────────────────────────────────────────────────────────────
# 2. 月亮星座 —— 12×30 天预计算矩阵（2026 历法生成，允许 ±1 星座误差）
# ─────────────────────────────────────────────────────────────────────────────

# 锚点：2026-01-03 00:00（新月，月亮黄经 ≈ 283°）；月行 13.176°/天。
_MOON_ANCHOR_LON = 283.0
_MOON_MEAN_MOTION = 13.176  # 度/天

# 12×30 天矩阵：MOON_SIGN_MATRIX[月-1][日-1]（31 日与 30 日同位；2 月 29/30 与 28 日同位）。
# 由锚点公式生成（见模块文档），硬编码便于审查与确定性。
MOON_SIGN_MATRIX = [
    # 1月
    "sagittarius", "sagittarius", "capricorn", "capricorn", "aquarius", "aquarius", "pisces", "pisces", "aries", "aries", "aries", "taurus", "taurus", "gemini", "gemini", "cancer", "cancer", "leo", "leo", "leo", "virgo", "virgo", "libra", "libra", "scorpio", "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn",
    # 2月
    "aquarius", "aquarius", "pisces", "pisces", "pisces", "aries", "aries", "taurus", "taurus", "gemini", "gemini", "cancer", "cancer", "cancer", "leo", "leo", "virgo", "virgo", "libra", "libra", "libra", "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn", "capricorn", "aquarius", "aquarius", "aquarius",
    # 3月
    "aquarius", "aquarius", "pisces", "pisces", "aries", "aries", "taurus", "taurus", "taurus", "gemini", "gemini", "cancer", "cancer", "leo", "leo", "virgo", "virgo", "virgo", "libra", "libra", "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn", "capricorn", "capricorn", "aquarius", "aquarius", "pisces",
    # 4月
    "aries", "aries", "aries", "taurus", "taurus", "gemini", "gemini", "cancer", "cancer", "leo", "leo", "leo", "virgo", "virgo", "libra", "libra", "scorpio", "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn", "capricorn", "aquarius", "aquarius", "pisces", "pisces", "pisces", "aries", "aries",
    # 5月
    "taurus", "taurus", "gemini", "gemini", "cancer", "cancer", "cancer", "leo", "leo", "virgo", "virgo", "libra", "libra", "libra", "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn", "capricorn", "aquarius", "aquarius", "aquarius", "pisces", "pisces", "aries", "aries", "taurus", "taurus", "taurus",
    # 6月
    "gemini", "cancer", "cancer", "leo", "leo", "virgo", "virgo", "virgo", "libra", "libra", "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn", "capricorn", "capricorn", "aquarius", "aquarius", "pisces", "pisces", "aries", "aries", "aries", "taurus", "taurus", "gemini", "gemini", "cancer", "cancer",
    # 7月
    "leo", "leo", "leo", "virgo", "virgo", "libra", "libra", "scorpio", "scorpio", "sagittarius", "sagittarius", "sagittarius", "capricorn", "capricorn", "aquarius", "aquarius", "pisces", "pisces", "pisces", "aries", "aries", "taurus", "taurus", "gemini", "gemini", "cancer", "cancer", "cancer", "leo", "leo",
    # 8月
    "virgo", "libra", "libra", "libra", "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn", "capricorn", "aquarius", "aquarius", "aquarius", "pisces", "pisces", "aries", "aries", "taurus", "taurus", "gemini", "gemini", "gemini", "cancer", "cancer", "leo", "leo", "virgo", "virgo", "virgo", "libra",
    # 9月
    "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn", "capricorn", "capricorn", "aquarius", "aquarius", "pisces", "pisces", "aries", "aries", "aries", "taurus", "taurus", "gemini", "gemini", "cancer", "cancer", "leo", "leo", "leo", "virgo", "virgo", "libra", "libra", "scorpio", "scorpio", "sagittarius",
    # 10月
    "sagittarius", "sagittarius", "capricorn", "capricorn", "aquarius", "aquarius", "pisces", "pisces", "pisces", "aries", "aries", "taurus", "taurus", "gemini", "gemini", "cancer", "cancer", "cancer", "leo", "leo", "virgo", "virgo", "libra", "libra", "libra", "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn",
    # 11月
    "aquarius", "aquarius", "aquarius", "pisces", "pisces", "aries", "aries", "taurus", "taurus", "gemini", "gemini", "gemini", "cancer", "cancer", "leo", "leo", "virgo", "virgo", "virgo", "libra", "libra", "scorpio", "scorpio", "sagittarius", "sagittarius", "capricorn", "capricorn", "capricorn", "aquarius", "aquarius",
    # 12月
    "pisces", "pisces", "aries", "aries", "taurus", "taurus", "taurus", "gemini", "gemini", "cancer", "cancer", "leo", "leo", "leo", "virgo", "virgo", "libra", "libra", "scorpio", "scorpio", "sagittarius", "sagittarius", "sagittarius", "capricorn", "capricorn", "aquarius", "aquarius", "pisces", "pisces", "pisces",
]

_MONTH_LEN = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]  # 2026 非闰年


def _moon_sign_from_matrix(month: int, day: int) -> str:
    """无出生时间：查 12×30 预计算表（2026 历法近似，允许 ±1 星座误差）。

    矩阵列为日 1..30：31 日与 30 日同位；2 月 29/30 与 28 日同位（2026 非闰年）。
    """
    day = max(1, min(day, 30))
    return MOON_SIGN_MATRIX[(month - 1) * 30 + (day - 1)]


def _moon_sign_refined(month: int, day: int, hour_fraction: float) -> str:
    """带出生时间：锚点连续公式精化（时间→月亮位置近似公式）。"""
    import calendar as _cal

    last = _cal.monthrange(2026, month)[1]
    dd = min(day, last)
    days = (date(2026, month, dd) - date(2026, 1, 3)).days + hour_fraction / 24.0
    lon = (_MOON_ANCHOR_LON + days * _MOON_MEAN_MOTION) % 360.0
    return ZODIAC_KEYS[int(lon // 30.0) % 12]


def moon_sign(month: int, day: int, birth_time: str | None = None) -> tuple[str, bool]:
    """出生月日 → 月亮星座 key + 是否近似（无出生时间 → 查表近似）。

    birth_time 格式 HH:MM 或 HH:MM:SS；解析失败回退查表（近似）。
    """
    if birth_time:
        h = _parse_hours(birth_time)
        if h is not None:
            return _moon_sign_refined(month, day, h), False
    return _moon_sign_from_matrix(month, day), True


# ─────────────────────────────────────────────────────────────────────────────
# 3. 上升星座 —— 出生时刻 + 地点经度近似（太阳升起时刻≈上升星座）
# ─────────────────────────────────────────────────────────────────────────────

# 常用城市经度（东经，度）；未知城市 → 东八区标准经度 120°E
CITY_LONGITUDES = {
    "北京": 116.4, "上海": 121.5, "广州": 113.3, "深圳": 114.1, "成都": 104.1,
    "重庆": 106.6, "杭州": 120.2, "南京": 118.8, "武汉": 114.3, "西安": 108.9,
    "天津": 117.2, "苏州": 120.6, "长沙": 113.0, "郑州": 113.6, "青岛": 120.4,
    "沈阳": 123.4, "大连": 121.6, "哈尔滨": 126.6, "昆明": 102.7, "兰州": 103.8,
    "乌鲁木齐": 87.6, "拉萨": 91.1, "香港": 114.2, "澳门": 113.5, "台北": 121.5,
}
STANDARD_MERIDIAN = 120.0  # 东八区


def _parse_hours(time_str: str) -> float | None:
    """解析 HH:MM / HH:MM:SS → 小时小数；失败返回 None。"""
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", (time_str or "").strip())
    if not m:
        return None
    hour = int(m.group(1))
    if hour > 23:
        return None
    minute = int(m.group(2))
    if minute > 59:
        return None
    second = int(m.group(3) or 0)
    if second > 59:
        return None
    return hour + minute / 60.0 + second / 3600.0


def rising_sign(sun_key: str, birth_time: str | None, birth_city: str | None = None) -> str | None:
    """出生时刻 + 地点经度 → 上升星座 key；无时间返回 None。

    简化算法（标注「近似」）：太阳 6:00（当地太阳时）升起时上升=太阳星座，
    此后天球每 2 小时推进 1 宫 → 上升 = 太阳 + floor((太阳时 - 6) / 2) mod 12。
    """
    hours = _parse_hours(birth_time)
    if hours is None:
        return None
    lon = CITY_LONGITUDES.get((birth_city or "").strip(), STANDARD_MERIDIAN)
    solar_hour = hours - (STANDARD_MERIDIAN - lon) / 15.0  # 表时 → 当地太阳时
    sun_idx = ZODIAC_KEYS.index(sun_key)
    offset = int((solar_hour - 6.0) // 2.0)
    return ZODIAC_KEYS[(sun_idx + offset) % 12]


# ─────────────────────────────────────────────────────────────────────────────
# 模板兜底文案（AI 生成失败时使用；AI 生成一次并缓存到 user.birthchart_json）
# ─────────────────────────────────────────────────────────────────────────────

# text：12 星座 × 3 角色一句话（20~40 字）
_TEXT_TEMPLATES: dict[str, dict[str, str]] = {
    "sun": {
        "aries": "天生点火体质，想到就去做，爱要爱得坦荡",
        "taurus": "稳得像大地，认定的人和事，会守很久",
        "gemini": "风一样灵动，好奇心是你的超能力",
        "cancer": "心里住着一盏灯，越温柔越有力量",
        "leo": "天生聚光灯体质，爱要爱得张扬",
        "virgo": "认真是你的天赋，把小事做到发光的程度",
        "libra": "天生优雅的平衡者，靠近你的人都觉得舒服",
        "scorpio": "深水般的专注，认定的事绝不半途而废",
        "sagittarius": "远方在召唤你，自由是你最重要的行李",
        "capricorn": "沉默的攀登者，一步一步走向山顶",
        "aquarius": "想别人没想过的事，走别人没走过的路",
        "pisces": "心软得像海绵，却装得下整片海洋",
    },
    "moon": {
        "aries": "情绪来得快也去得快，生气三分钟，转头就忘",
        "taurus": "情绪需要稳定的支点，安全感是最好的充电器",
        "gemini": "心情像调频电台，需要新鲜感来充能",
        "cancer": "情绪像海，需要温柔的岸",
        "leo": "被认可时闪闪发光，被冷落时心里下雨",
        "virgo": "心事习惯自己消化，越想周全越容易累",
        "libra": "情绪藏在优雅里，不舒服也很少说出口",
        "scorpio": "情绪深且烈，爱憎都清晰分明",
        "sagittarius": "不开心就去远方，动起来心情就亮了",
        "capricorn": "情绪习惯压箱底，其实你也需要被接住",
        "aquarius": "情绪来得慢热，习惯先观察再靠近",
        "pisces": "感受力强得像天线，别人的悲喜都收得到",
    },
    "rising": {
        "aries": "初见就带着冲劲，让人觉得你随时准备出发",
        "taurus": "第一印象是温柔的坚定，慢热却持久",
        "gemini": "初见机灵又健谈，让人想多聊两句",
        "cancer": "初见亲切得像老朋友，自带安全感",
        "leo": "初见自带光芒，让人很难不注意你",
        "virgo": "初见细致又靠谱，让人觉得可以托付",
        "libra": "初见让人如沐春风",
        "scorpio": "初见有些神秘，熟了才知道有多热",
        "sagittarius": "初见阳光开朗，笑意很有感染力",
        "capricorn": "初见稳重寡言，久了才知你的认真",
        "aquarius": "初见有点酷，熟了才发现脑洞很大",
        "pisces": "初见温柔好说话，像一阵软软的风",
    },
}

# detail 三段：天赋 / 阴影 / 今年主题（按角色给句式模板，插值星座名）
_DETAIL_TEMPLATES: dict[str, dict[str, str]] = {
    "sun": {
        "talent": "你的天赋是「成为光源」——靠近{name}的人会被你的能量点燃，你的存在本身就是一种鼓舞。",
        "shadow": "阴影面是：怕暗。当掌声安静下来，你会怀疑自己的价值。记住，光不靠观众存在。",
        "theme": "今年太阳主题：重新认领「被看见」的权利。你的光芒不是冒犯，不必谦让。",
    },
    "moon": {
        "talent": "你的天赋是「接住情绪」——{name}的直觉细腻，朋友心事第一个想到你。",
        "shadow": "阴影面是：太擅长照顾别人，忘了自己也需要被照顾。先给自己留一盏灯。",
        "theme": "今年月亮主题：把「照顾」分一点给自己。你值得被同样温柔地对待。",
    },
    "rising": {
        "talent": "你的天赋是「第一印象」——{name}出场自带气场，让人愿意靠近和信任。",
        "shadow": "阴影面是：面具戴久了，会忘了自己的本来面目。真实，比完美更动人。",
        "theme": "今年上升主题：让外在的你和内在的你，慢慢变成同一个人。",
    },
}

_MISSING_MESSAGES = {
    "birth_date": "填出生日期，点亮太阳与月亮 ✦",
    "birth_time": "补全出生时间解锁上升 ✦",
}


def fallback_element(role: str, zodiac_key: str) -> dict:
    """AI 生成失败时的模板兜底（text + talent/shadow/theme）。"""
    name = ZODIAC_NAMES_ZH[zodiac_key]
    detail_tmpl = _DETAIL_TEMPLATES[role]
    return {
        "text": _TEXT_TEMPLATES[role][zodiac_key],
        "detail": {
            "talent": detail_tmpl["talent"].format(name=name),
            "shadow": detail_tmpl["shadow"].format(name=name),
            "theme": detail_tmpl["theme"].format(name=name),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 星盘计算（纯函数）
# ─────────────────────────────────────────────────────────────────────────────


def compute_birthchart(
    birth_date: str | None,
    birth_time: str | None = None,
    birth_city: str | None = None,
    ai_text: dict | None = None,
) -> dict:
    """计算三要素，返回接口结构（ai_text 为 AI 生成的 {role: {text, detail}}，可空）。

    - 无 birth_date → 三要素均 null + missing=["birth_date"]
    - 无 birth_time → moon 近似(查表) + rising null + missing=["birth_time"]
    """
    missing: list[str] = []
    if not birth_date:
        return {
            "birth": {"date": None, "time": birth_time, "city": birth_city, "complete": False},
            "sun": None, "moon": None, "rising": None,
            "missing": ["birth_date"],
            "message": _MISSING_MESSAGES["birth_date"],
        }

    parts = birth_date.split("-")
    if len(parts) != 3:
        return {
            "birth": {"date": birth_date, "time": birth_time, "city": birth_city, "complete": False},
            "sun": None, "moon": None, "rising": None,
            "missing": ["birth_date"],
            "message": _MISSING_MESSAGES["birth_date"],
        }
    month, day = int(parts[1]), int(parts[2])

    sun_key = sun_sign(month, day)
    moon_key, moon_approx = moon_sign(month, day, birth_time)
    rising_key = rising_sign(sun_key, birth_time, birth_city)
    if rising_key is None:
        missing.append("birth_time")

    def _el(role: str, key: str, approx: bool) -> dict:
        src = (ai_text or {}).get(role) or fallback_element(role, key)
        return {
            "zodiac": key,
            "name": ZODIAC_NAMES_ZH[key],
            "label": ROLE_LABELS[role],
            "text": src.get("text") or fallback_element(role, key)["text"],
            "approx": approx,
            "detail": src.get("detail") or fallback_element(role, key)["detail"],
        }

    return {
        "birth": {
            "date": birth_date,
            "time": birth_time,
            "city": birth_city,
            "complete": not missing,
        },
        "sun": _el("sun", sun_key, False),
        "moon": _el("moon", moon_key, moon_approx),
        "rising": _el("rising", rising_key, True) if rising_key else None,
        "missing": missing,
        "message": _MISSING_MESSAGES["birth_time"] if missing else "",
    }


def birth_fingerprint(birth_date: str | None, birth_time: str | None, birth_city: str | None) -> str:
    """出生信息指纹：缓存失效判定用（任一字段变化 → 重新生成文案）。"""
    return f"{birth_date or ''}|{birth_time or ''}|{birth_city or ''}"


# ─────────────────────────────────────────────────────────────────────────────
# AI 生成（生成一次 → 缓存到 user.birthchart_json / user.birthchart_report）
# ─────────────────────────────────────────────────────────────────────────────

_OUTPUT_RED_LINES = (
    "【输出红线】必须无条件遵守：\n"
    "1. 不预测具体事件、时间或结果：不说「一定会」「注定」「某月某日」等确定性断言。\n"
    "2. 禁止恐吓或威胁式表达：不说「再不…就来不及了」之类制造恐慌的话。\n"
    "3. 禁止命运定性：不说「你就是这种命」「命中注定」。\n"
    "4. 禁止健康与心理诊断：不评判用户的身体或精神状况。\n"
    "5. 禁止财务、投资、法律建议。\n"
    "6. 不引用、不暗示用户日记、聊天记录或任何用户未主动告知的信息。\n"
    "7. 语言温暖、具体、鼓励，强调用户有选择的自由。\n"
)


def _get_ai_client():
    """与 report.py 同模式：本地 AsyncOpenAI 客户端（无 key 返回 None）。"""
    from openai import AsyncOpenAI

    from app.config import settings

    if not settings.DEEPSEEK_API_KEY:
        return None
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


def _strip_json_fence(content: str) -> str:
    """去掉 AI 输出可能带的 ```json ``` 围栏。"""
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        stripped = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()
    return stripped


async def generate_elements_text(
    sun_key: str, moon_key: str, rising_key: str | None,
) -> dict | None:
    """AI 一次生成三要素文案 {role: {text, talent, shadow, theme}}；失败返回 None。"""
    from app.config import settings

    client = _get_ai_client()
    if not client:
        return None

    rising_line = ZODIAC_NAMES_ZH[rising_key] if rising_key else "无（用户未填出生时间）"
    system_prompt = (
        "你是一位温柔而有洞察力的占星师，为用户的「本命星盘三要素」撰写文案。\n"
        "语言风格：温暖、具体、像懂他的老朋友，不故弄玄虚。所有输出使用中文。\n"
        + _OUTPUT_RED_LINES
    )
    user_prompt = (
        "用户的星盘三要素如下，请为每一要素生成一句主线文案（20~40字）与三段详解：\n"
        f"- 太阳：{ZODIAC_NAMES_ZH[sun_key]}\n"
        f"- 月亮：{ZODIAC_NAMES_ZH[moon_key]}\n"
        f"- 上升：{rising_line}\n\n"
        "严格按以下 JSON 输出，不要包含任何多余内容：\n"
        "{\n"
        '  "sun": {"text": "一句话主线", "talent": "天赋段40-70字", "shadow": "阴影段40-70字", "theme": "今年主题段40-70字"},\n'
        '  "moon": {"text": "...", "talent": "...", "shadow": "...", "theme": "..."},\n'
        '  "rising": {"text": "...", "talent": "...", "shadow": "...", "theme": "..."} 或 null\n'
        "}\n"
        "每段不要使用「命中注定」「必须」「一定会」等措辞。"
    )

    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=60.0,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            return None
        data = json.loads(_strip_json_fence(content))
        return {
            role: {
                "text": str(data.get(role, {}).get("text", "")),
                "detail": {
                    "talent": str(data.get(role, {}).get("talent", "")),
                    "shadow": str(data.get(role, {}).get("shadow", "")),
                    "theme": str(data.get(role, {}).get("theme", "")),
                },
            }
            for role in ("sun", "moon", "rising")
            if isinstance(data.get(role), dict)
        }
    except Exception as exc:
        logger.warning("generate_elements_text failed: %s", exc)
        return None


# ── 深度报告（付费 · POST /user/birthchart/report）──

REPORT_SECTIONS = ["character", "relation", "annual_theme", "card_advice"]
REPORT_SECTION_NAMES = {
    "character": "性格底色",
    "relation": "关系模式",
    "annual_theme": "年度主题",
    "card_advice": "牌面建议",
}


def fallback_report(chart: dict) -> dict:
    """AI 失败时的模板兜底报告（由三要素文案拼装，温和非决定论）。"""
    sun = chart.get("sun") or {}
    moon = chart.get("moon") or {}
    rising = chart.get("rising") or {}
    sun_name = sun.get("name", "太阳")
    moon_name = moon.get("name", "月亮")
    sun_text = sun.get("text", "")
    moon_text = moon.get("text", "")
    rising_text = rising.get("text", "")

    character = (
        f"太阳落在{sun_name}——{sun_text}；月亮落在{moon_name}——{moon_text}。"
        f"这两股力量一明一暗，构成你性格的主色板：白天有太阳的做派，夜晚有月亮的柔软。"
        f"接受两种面貌共存，是你和自己和解的开始。"
    )
    relation = (
        f"在关系里，你带着{moon_name}的底色——{moon_text}。"
        f"你习惯先付出、先体谅，但请记得：好的关系不需要你一直「懂事」。"
        f"把需求说出口，不是索取，是让彼此更靠近的方式。"
    )
    annual_theme = (
        f"今年对{ sun_name}的你来说，主题是「把光对准自己」——"
        f"允许自己被看见、被喜欢，也允许自己有时暗淡。"
        f"给自己留一点独处的时间，那里有你的答案。"
    )
    card_advice = (
        "给今天的你一张温柔的牌面建议：与其等待「更好的时机」，不如从一件小事开始行动。"
        "写下今天最想推进的一步，完成它；牌面只是镜子，掌舵的人始终是你。"
    )
    return {
        "character": character,
        "relation": relation,
        "annual_theme": annual_theme,
        "card_advice": card_advice,
        "fallback": True,
    }


async def generate_deep_report(chart: dict) -> dict | None:
    """AI 生成深度报告四段；失败返回 None（调用方用 fallback_report）。"""
    from app.config import settings

    client = _get_ai_client()
    if not client:
        return None

    sun = chart.get("sun") or {}
    moon = chart.get("moon") or {}
    rising = chart.get("rising") or {}

    system_prompt = (
        "你是一位温柔、睿智的占星师，为用户撰写一份深度的本命星盘报告。\n"
        "要求：洞察深刻、文字有温度、具体可感，像一位懂他的老朋友在深夜谈心。\n"
        "报告是「觉察的镜子」而不是「判决书」——一切落脚在用户的自主选择与成长可能上。\n"
        "所有输出使用中文。\n"
        + _OUTPUT_RED_LINES
    )
    user_prompt = (
        "用户的星盘三要素：\n"
        f"- 太阳 {sun.get('name', '')}（{sun.get('label', '核心动力')}）：{sun.get('text', '')}\n"
        f"- 月亮 {moon.get('name', '')}（{moon.get('label', '情绪底色')}）：{moon.get('text', '')}\n"
        f"- 上升 {rising.get('name', '未填出生时间')}（{rising.get('label', '他人眼中的我')}）：{rising.get('text', '')}\n\n"
        "严格按以下 JSON 输出，不要包含任何多余内容：\n"
        "{\n"
        '  "character": "性格底色：综合日月升的完整剖析，100-180字",\n'
        '  "relation": "关系模式：在亲密与友谊中的行为模式与温柔提醒，100-180字",\n'
        '  "annual_theme": "年度主题：今年的成长课题与可行方向，100-180字（不指定具体月份与事件）",\n'
        '  "card_advice": "牌面建议：给一张塔罗牌作为隐喻+一条今天就能做的小行动，80-150字"\n'
        "}\n"
        "禁止预测具体事件、时间点或结果；禁止恐吓；禁止健康诊断；禁止引用用户日记。"
    )

    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=120.0,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            return None
        data = json.loads(_strip_json_fence(content))
        result = {sec: str(data.get(sec, "")).strip() for sec in REPORT_SECTIONS}
        if all(result.values()):
            return {**result, "fallback": False}
        return None
    except Exception as exc:
        logger.warning("generate_deep_report failed: %s", exc)
        return None
