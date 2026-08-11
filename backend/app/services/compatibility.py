"""
星辰相遇：12×12 星座兼容表 + 三要素加权算法（星光映照 · P1 T2-1）。

设计（对应设计文档 T2-1 与 task-16-brief）：
  1. 兼容表 COMPAT_TABLE：12×12 对称常量（与 STAR_COLORS 同治理方式：常量配置化、
     可运营调整——改 _COMPAT_TABLE_OVERRIDES 即可，分数带约束由测试守卫）。
     初稿规则（元素关系 → 基线分，同模式 +3 微调）：
       - 同元素（火/土/风/水）：85-95 分
       - 互补元素（火风 / 土水）：75-85 分
       - 其余组合：55-75 分（固定表）
       - 同模式（cardinal/fixed/mutable）微调 +3；再经人工抽查定稿（少数名组合微调）。
  2. 加权：太阳 50% + 月亮 30% + 上升 20%；缺要素 → 剩余权重重归一化
     （仅太阳 → 100%；无上升 → 太阳 62.5% + 月亮 37.5%；无月亮 → 太阳 71.4% + 上升 28.6%）。
  3. 可解释：每个角色 factor 的 reason 形如「同元素·火象相映 +20」——
     score = 70（中性基线）+ delta，每分有出处（兼容表 + 要素权重）。
  4. 确定性：同输入恒同输出（纯函数，无随机/时间依赖）。

合规：输出为「相合度分数 + 相处提示框架」，分数本身不涉预测；
文案禁用 注定/天生一对/命中 类措辞（测试禁词扫描）。

复用：birthchart.ZODIAC_KEYS（12 key 权威枚举）；能量引擎「分数原因可见」哲学
（energy_engine factors 链）。
"""

from __future__ import annotations

from app.services.birthchart import ZODIAC_KEYS

# ─────────────────────────────────────────────────────────────────────────────
# 元素 / 模式（经典四元素与三模式，12 星座全覆盖）
# ─────────────────────────────────────────────────────────────────────────────

# 四元素：火 fire / 土 earth / 风 air / 水 water（每组 3 星座）
ZODIAC_ELEMENTS: dict[str, str] = {
    "aries": "fire", "leo": "fire", "sagittarius": "fire",
    "taurus": "earth", "virgo": "earth", "capricorn": "earth",
    "gemini": "air", "libra": "air", "aquarius": "air",
    "cancer": "water", "scorpio": "water", "pisces": "water",
}

# 三模式：cardinal 开创 / fixed 固定 / mutable 变动（每组 4 星座）
ZODIAC_MODES: dict[str, str] = {
    "aries": "cardinal", "cancer": "cardinal", "libra": "cardinal", "capricorn": "cardinal",
    "taurus": "fixed", "leo": "fixed", "scorpio": "fixed", "aquarius": "fixed",
    "gemini": "mutable", "virgo": "mutable", "sagittarius": "mutable", "pisces": "mutable",
}

_ELEMENT_ZH = {"fire": "火", "earth": "土", "air": "风", "water": "水"}

# 互补元素组（火↔风 相吸、土↔水 相生）
_COMPLEMENTARY_GROUPS: set[frozenset[str]] = {
    frozenset({"fire", "air"}),
    frozenset({"earth", "water"}),
}

# ─────────────────────────────────────────────────────────────────────────────
# 12×12 兼容表（初稿由元素规则生成 + 人工抽查定稿；常量可运营调整）
# ─────────────────────────────────────────────────────────────────────────────

# 元素关系 → 基线分（区间：同元素 85-95 / 互补 75-85 / 其余 55-75）
_BASE_BY_RELATION = {"same": 90, "complement": 80, "other": 65}
_SAME_MODE_ADJUST = 3  # 同模式微调（cardinal 开创×开创 / fixed 固定×固定 / mutable 变动×变动）

# 中性基线：score = 70 + delta，reason 里的 delta 即该要素相对基线的偏移（每分有解释）
NEUTRAL_SCORE = 70

# 人工定稿微调（运营可调）：在带约束内给少数名组合定值；
# 约束：同元素 ≥85、互补 75-85、其余 55-75、全表对称（测试守卫）。
_COMPAT_TABLE_OVERRIDES: dict[tuple[str, str], int] = {
    # 其余组合（55-75）：火土需磨合（开创×开创 同模式 → 双强则刚）
    ("aries", "capricorn"): 62,
    # 其余组合：火土慢热却持久（固定×固定 同模式 → 意外默契）
    ("leo", "taurus"): 72,
    # 其余组合：火土动静互补（变动×变动 同模式 → 一起跑得动）
    ("sagittarius", "virgo"): 74,
    # 其余组合：风土一快一稳，需彼此放慢
    ("gemini", "taurus"): 60,
    # 其余组合：水火温差大，留足边界反而长久
    ("scorpio", "aries"): 58,
    # 其余组合：风水一个飞一个沉，靠日常小事找同频
    ("pisces", "aquarius"): 63,
    # 互补组合（75-85）：火风相吸的极致——双子×射手同变动，聊不完
    ("gemini", "sagittarius"): 85,
    # 互补组合：土水相生的代表——金牛×双鱼同固定，稳而暖
    ("taurus", "pisces"): 84,
}


def _element_relation(a: str, b: str) -> str:
    """两星座元素关系：same / complement / other。"""
    ea, eb = ZODIAC_ELEMENTS[a], ZODIAC_ELEMENTS[b]
    if ea == eb:
        return "same"
    if frozenset({ea, eb}) in _COMPLEMENTARY_GROUPS:
        return "complement"
    return "other"


def _base_compat_score(a: str, b: str) -> int:
    """初稿规则分：元素关系基线 + 同模式微调。"""
    score = _BASE_BY_RELATION[_element_relation(a, b)]
    if ZODIAC_MODES[a] == ZODIAC_MODES[b]:
        score += _SAME_MODE_ADJUST
    return score


def _build_compat_table() -> dict[tuple[str, str], int]:
    """初稿由元素规则生成 → 人工定稿覆盖 → 全表（对称）。"""
    table: dict[tuple[str, str], int] = {
        (a, b): _base_compat_score(a, b) for a in ZODIAC_KEYS for b in ZODIAC_KEYS
    }
    for (a, b), score in _COMPAT_TABLE_OVERRIDES.items():
        table[(a, b)] = score
        table[(b, a)] = score  # 保持对称
    return table


# 12×12 对称常量表（144 组合；约束由 tests/test_compatibility.py 守卫）
COMPAT_TABLE: dict[tuple[str, str], int] = _build_compat_table()


# ─────────────────────────────────────────────────────────────────────────────
# 档位
# ─────────────────────────────────────────────────────────────────────────────

_LEVELS = [
    (85, "星光共鸣"),   # 85+ 心意同频，靠近时像照镜子
    (70, "星光相映"),   # 70-84 彼此点亮，节奏有呼应
    (55, "星光相伴"),   # 55-69 慢慢走近，默契靠相处经营
    (0, "星光初见"),    # <55 各自闪光，相逢即是好开头
]

# 公开档位名常量（T2-1 设计定稿；测试/运营取真实来源，不自行拷贝）
LEVEL_NAMES: tuple[str, ...] = tuple(name for _, name in _LEVELS)


def level_name(score: int) -> str:
    """分数 → 档位名（相合度框架，非预测）。"""
    for threshold, name in _LEVELS:
        if score >= threshold:
            return name
    return _LEVELS[-1][1]


# ─────────────────────────────────────────────────────────────────────────────
# 加权
# ─────────────────────────────────────────────────────────────────────────────

WEIGHTS: dict[str, float] = {"sun": 0.5, "moon": 0.3, "rising": 0.2}

_ROLE_ZH = {"sun": "太阳", "moon": "月亮", "rising": "上升"}
_FACTOR_ORDER = ["sun", "moon", "rising"]


def _compat_reason(a: str, b: str, score: int) -> str:
    """每分的解释：关系类型·元素描述 + 相对中性基线的 delta。"""
    relation = _element_relation(a, b)
    ea, eb = ZODIAC_ELEMENTS[a], ZODIAC_ELEMENTS[b]
    za, zb = _ELEMENT_ZH[ea], _ELEMENT_ZH[eb]
    if relation == "same":
        label = f"同元素·{za}象相映"
    elif relation == "complement":
        label = "互补元素·火风相吸" if frozenset({ea, eb}) == frozenset({"fire", "air"}) else "互补元素·土水相生"
    else:
        label = f"异元素·{za}{zb}节奏互补"
    return f"{label} {score - NEUTRAL_SCORE:+d}"


def compute_compatibility(
    *,
    a_sun: str | None = None,
    b_sun: str | None = None,
    a_moon: str | None = None,
    b_moon: str | None = None,
    a_rising: str | None = None,
    b_rising: str | None = None,
) -> dict:
    """合盘相合度：12×12 兼容表 + 三要素加权（纯函数，确定性）。

    参数为双方各要素的星座 key（birthchart.ZODIAC_KEYS 权威枚举）；
    太阳必填，月亮/上升可为 None（任一侧缺失则该角色不参与）。

    返回::
        {
            "score": int,          # 加权总分（缺要素时按剩余权重重归一化）
            "level_name": str,     # 档位名
            "factors": [{role, score, reason}],  # 每角色一档，reason 解释每分
            "used": [roles],       # 实际参与角色（sun → moon → rising 序）
            "estimated": bool,     # 是否缺要素（估算）
            "estimate_note": str,  # 估算说明（缺哪些/权重如何重归一；完整时为空串）
        }
    """
    pairs: dict[str, tuple[str, str]] = {}
    for role, a_key, b_key in (
        ("sun", a_sun, b_sun),
        ("moon", a_moon, b_moon),
        ("rising", a_rising, b_rising),
    ):
        if a_key is None or b_key is None:
            continue
        for key in (a_key, b_key):
            if key not in ZODIAC_ELEMENTS:
                raise ValueError(f"未知星座 key: {key}")
        pairs[role] = (a_key, b_key)

    if "sun" not in pairs:
        raise ValueError("compute_compatibility 需要太阳星座（a_sun/b_sun 必填）")

    used = [role for role in _FACTOR_ORDER if role in pairs]
    factors = [
        {
            "role": role,
            "score": COMPAT_TABLE[pairs[role]],
            "reason": _compat_reason(pairs[role][0], pairs[role][1], COMPAT_TABLE[pairs[role]]),
        }
        for role in used
    ]

    total_weight = sum(WEIGHTS[role] for role in used)
    score = int(round(sum(f["score"] * WEIGHTS[f["role"]] / total_weight for f in factors)))

    # 估算说明（缺要素 → 重归一化权重明细；每分有出处）
    if total_weight < 1.0:
        missing = [_ROLE_ZH[role] for role in _FACTOR_ORDER if role not in pairs]
        weights_str = " + ".join(
            f"{_ROLE_ZH[f['role']]}{round(WEIGHTS[f['role']] / total_weight * 100, 1):g}%"
            for f in factors
        )
        estimate_note = f"缺少{'、'.join(missing)}，已按 {weights_str} 重归一化，结果仅供参考"
        estimated = True
    else:
        estimate_note = ""
        estimated = False

    return {
        "score": score,
        "level_name": level_name(score),
        "factors": factors,
        "used": used,
        "estimated": estimated,
        "estimate_note": estimate_note,
    }
