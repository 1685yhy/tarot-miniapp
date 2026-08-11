"""
星辰相遇：12×12 星座兼容表 + 三要素加权算法（星光映照 · P1 T2-1）。

覆盖（对应 task-16-brief Step 1 验收）：
- 确定性：同输入两次 → 同 score / 同 level
- 权重：仅太阳 → used=["sun"]、权重 100%（score == 该要素分）
- 重归一化：无上升 → 太阳 62.5% + 月亮 37.5%；缺月亮 → 太阳/上升重归一
- 档位边界：85/84、70/69、55/54
- factor：每项 reason 非空、含元素描述、delta 与 score 算术一致（每分有解释）
- 表结构：对称、144 组合全在 55-95、同元素 ≥85、互补 75-85、四元素/三模式分组正确
- 合规：档位名/注释文案无 注定/天生一对 类禁词

算法为纯函数：确定性 + 可解释（每分有出处：兼容表 + 要素权重）。
"""

import re

import pytest

from app.services.birthchart import ZODIAC_KEYS
from app.services.compatibility import (
    COMPAT_TABLE,
    WEIGHTS,
    ZODIAC_ELEMENTS,
    ZODIAC_MODES,
    compute_compatibility,
    level_name,
)

# 互补元素组（火风 / 土水）
COMPLEMENTARY_GROUPS = [
    {"fire", "air"},
    {"earth", "water"},
]

BANNED_WORDS = ("注定", "天生一对", "命中注定", "一定要", "百分百", "绝对")

_ELEMENT_ZH = ("火", "土", "风", "水")


def _pair_score(a: str, b: str) -> int:
    return COMPAT_TABLE[(a, b)]


# ─────────────────────────────────────────────────────────────────────────────
# 表结构：12×12 对称常量
# ─────────────────────────────────────────────────────────────────────────────


def test_compat_table_covers_all_144_pairs():
    """COMPAT_TABLE 覆盖全部 12×12 组合，key 与 birthchart.ZODIAC_KEYS 一致。"""
    for a in ZODIAC_KEYS:
        for b in ZODIAC_KEYS:
            assert (a, b) in COMPAT_TABLE, f"缺组合 ({a}, {b})"
    assert len(COMPAT_TABLE) == 144


def test_compat_table_symmetric():
    """表对称：compat(a, b) == compat(b, a)。"""
    for a in ZODIAC_KEYS:
        for b in ZODIAC_KEYS:
            assert _pair_score(a, b) == _pair_score(b, a), f"不对称: ({a}, {b})"


def test_compat_table_all_scores_in_55_95():
    """全部 144 组合分数在 55-95 合法区间。"""
    for a in ZODIAC_KEYS:
        for b in ZODIAC_KEYS:
            s = _pair_score(a, b)
            assert 55 <= s <= 95, f"({a}, {b}) 分数 {s} 越界"


def test_compat_table_same_element_at_least_85():
    """同元素组合 ≥85。"""
    for a in ZODIAC_KEYS:
        for b in ZODIAC_KEYS:
            if ZODIAC_ELEMENTS[a] == ZODIAC_ELEMENTS[b]:
                assert _pair_score(a, b) >= 85, f"同元素 ({a}, {b}) 分数过低"


def test_compat_table_complementary_in_75_85():
    """互补元素组合（火风/土水）75-85。"""
    for a in ZODIAC_KEYS:
        for b in ZODIAC_KEYS:
            if {ZODIAC_ELEMENTS[a], ZODIAC_ELEMENTS[b]} in COMPLEMENTARY_GROUPS:
                s = _pair_score(a, b)
                assert 75 <= s <= 85, f"互补 ({a}, {b}) 分数 {s} 越界"


def test_zodiac_elements_groups_balanced():
    """四元素各 3 星座，12 key 全覆盖。"""
    groups: dict[str, list[str]] = {g: [] for g in ("fire", "earth", "air", "water")}
    for key in ZODIAC_KEYS:
        groups[ZODIAC_ELEMENTS[key]].append(key)
    for g, keys in groups.items():
        assert len(keys) == 3, f"元素 {g} 应有 3 星座: {keys}"
    # 抽查经典归属（权威枚举）
    assert ZODIAC_ELEMENTS["aries"] == "fire"
    assert ZODIAC_ELEMENTS["taurus"] == "earth"
    assert ZODIAC_ELEMENTS["gemini"] == "air"
    assert ZODIAC_ELEMENTS["cancer"] == "water"


def test_zodiac_modes_balanced():
    """三模式（cardinal/fixed/mutable）各 4 星座。"""
    modes: dict[str, list[str]] = {m: [] for m in ("cardinal", "fixed", "mutable")}
    for key in ZODIAC_KEYS:
        modes[ZODIAC_MODES[key]].append(key)
    for m, keys in modes.items():
        assert len(keys) == 4, f"模式 {m} 应有 4 星座: {keys}"
    assert ZODIAC_MODES["aries"] == "cardinal"
    assert ZODIAC_MODES["taurus"] == "fixed"
    assert ZODIAC_MODES["gemini"] == "mutable"


def test_weights_declared():
    """WEIGHTS 常量：太阳 50% + 月亮 30% + 上升 20%。"""
    assert WEIGHTS == {"sun": 0.5, "moon": 0.3, "rising": 0.2}


# ─────────────────────────────────────────────────────────────────────────────
# 确定性
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_deterministic_same_input_same_result():
    """确定性：同输入两次 → 完整结果完全一致。"""
    r1 = compute_compatibility(a_sun="leo", b_sun="sagittarius", a_moon="cancer", b_moon="pisces")
    r2 = compute_compatibility(a_sun="leo", b_sun="sagittarius", a_moon="cancer", b_moon="pisces")
    assert r1 == r2
    assert r1["score"] == r2["score"]


# ─────────────────────────────────────────────────────────────────────────────
# 权重与重归一化
# ─────────────────────────────────────────────────────────────────────────────


def test_sun_only_uses_full_weight():
    """仅太阳 → used=["sun"]、score == 太阳要素分（权重 100%）、标注估算。"""
    a_sun, b_sun = "leo", "aries"
    r = compute_compatibility(a_sun=a_sun, b_sun=b_sun)
    assert r["used"] == ["sun"]
    assert r["estimated"] is True
    assert r["estimate_note"]
    assert len(r["factors"]) == 1
    assert r["factors"][0]["role"] == "sun"
    assert r["score"] == _pair_score(a_sun, b_sun)
    assert r["score"] == r["factors"][0]["score"]


def test_no_rising_renormalizes_625_375():
    """无上升 → 太阳 62.5% + 月亮 37.5% 重归一化。"""
    a_sun, b_sun, a_moon, b_moon = "leo", "taurus", "cancer", "pisces"
    r = compute_compatibility(a_sun=a_sun, b_sun=b_sun, a_moon=a_moon, b_moon=b_moon)
    assert r["used"] == ["sun", "moon"]
    assert "rising" not in r["used"]
    assert r["estimated"] is True
    assert "62.5" in r["estimate_note"] and "37.5" in r["estimate_note"]
    expected = round(_pair_score(a_sun, b_sun) * 0.625 + _pair_score(a_moon, b_moon) * 0.375)
    assert r["score"] == expected
    # 每 factor 顺序：sun → moon
    assert [f["role"] for f in r["factors"]] == ["sun", "moon"]


def test_missing_moon_only_renormalizes():
    """缺月亮（有上升）→ 太阳/上升按剩余权重重归一化。"""
    a_sun, b_sun, a_rising, b_rising = "leo", "aquarius", "gemini", "libra"
    r = compute_compatibility(a_sun=a_sun, b_sun=b_sun, a_rising=a_rising, b_rising=b_rising)
    assert r["used"] == ["sun", "rising"]
    assert r["estimated"] is True
    assert "月亮" in r["estimate_note"]
    expected = round(
        _pair_score(a_sun, b_sun) * 0.5 / 0.7 + _pair_score(a_rising, b_rising) * 0.2 / 0.7
    )
    assert r["score"] == expected


def test_full_three_roles_uses_weights_50_30_20():
    """三要素齐全 → 权重 0.5/0.3/0.2，estimated=False 且 note 为空。"""
    a_sun, b_sun = "leo", "sagittarius"
    a_moon, b_moon = "cancer", "pisces"
    a_rising, b_rising = "gemini", "libra"
    r = compute_compatibility(
        a_sun=a_sun, b_sun=b_sun,
        a_moon=a_moon, b_moon=b_moon,
        a_rising=a_rising, b_rising=b_rising,
    )
    assert r["used"] == ["sun", "moon", "rising"]
    assert r["estimated"] is False
    assert r["estimate_note"] == ""
    assert [f["role"] for f in r["factors"]] == ["sun", "moon", "rising"]
    expected = round(
        _pair_score(a_sun, b_sun) * 0.5
        + _pair_score(a_moon, b_moon) * 0.3
        + _pair_score(a_rising, b_rising) * 0.2
    )
    assert r["score"] == expected


def test_asymmetric_missing_side_treated_as_missing_role():
    """单边缺要素（a 有 moon，b 没有）→ 该角色不参与，标注估算。"""
    r = compute_compatibility(a_sun="leo", b_sun="virgo", a_moon="cancer", b_moon=None)
    assert "moon" not in r["used"]
    assert r["estimated"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 档位边界
# ─────────────────────────────────────────────────────────────────────────────


def test_level_name_boundaries():
    """档位边界：85/84、70/69、55/54。"""
    assert level_name(85) == "星光共鸣"
    assert level_name(84) == "星光相映"
    assert level_name(70) == "星光相映"
    assert level_name(69) == "星光相伴"
    assert level_name(55) == "星光相伴"
    assert level_name(54) == "星光初见"
    assert level_name(95) == "星光共鸣"
    assert level_name(40) == "星光初见"


def test_result_level_consistent_with_level_name():
    """返回的 level_name 与 score 经 level_name() 一致。"""
    r = compute_compatibility(a_sun="leo", b_sun="sagittarius", a_moon="cancer", b_moon="pisces")
    assert r["level_name"] == level_name(r["score"])


# ─────────────────────────────────────────────────────────────────────────────
# 可解释：每分有出处
# ─────────────────────────────────────────────────────────────────────────────


def test_factors_reasons_explain_every_point():
    """每 factor：reason 非空、含元素描述（火/土/风/水）、delta 与 score 算术一致。"""
    r = compute_compatibility(
        a_sun="leo", b_sun="sagittarius",
        a_moon="cancer", b_moon="pisces",
        a_rising="gemini", b_rising="libra",
    )
    assert len(r["factors"]) == 3
    for f in r["factors"]:
        reason = f["reason"]
        assert reason, f"{f['role']} 的 reason 为空"
        assert any(zh in reason for zh in _ELEMENT_ZH), f"{f['role']} reason 缺元素描述: {reason}"
        m = re.search(r"([+-]\d+)\s*$", reason)
        assert m, f"{f['role']} reason 缺 delta: {reason}"
        assert f["score"] == 70 + int(m.group(1)), (
            f"{f['role']} 分 {f['score']} 与 reason delta {m.group(1)} 不一致"
        )


def test_factors_reason_mentions_relation_type():
    """reason 形如「同元素·火象相映 +N」：含关系类型描述。"""
    r = compute_compatibility(a_sun="leo", b_sun="sagittarius", a_moon="cancer", b_moon="pisces")
    reasons = [f["reason"] for f in r["factors"]]
    # leo/sagittarius 同为火元素
    assert any(reason.startswith("同元素·") for reason in reasons)
    # cancer/pisces 同为水元素
    assert any("水" in reason for reason in reasons)


# ─────────────────────────────────────────────────────────────────────────────
# 入参校验
# ─────────────────────────────────────────────────────────────────────────────


def test_invalid_zodiac_key_raises():
    """非法星座 key → ValueError。"""
    with pytest.raises(ValueError):
        compute_compatibility(a_sun="leo", b_sun="not_a_sign")


def test_missing_sun_raises():
    """缺太阳（必填）→ ValueError。"""
    with pytest.raises(ValueError):
        compute_compatibility(a_sun="leo")  # type: ignore[call-arg]


# ─────────────────────────────────────────────────────────────────────────────
# 合规：档位名与注释文案不涉预测
# ─────────────────────────────────────────────────────────────────────────────


def test_level_names_and_notes_comply_red_line():
    """档位名/估算注释不含 注定/天生一对 类禁词（输出是相合度框架非预测）。"""
    names = {level_name(s) for s in range(0, 101)}
    notes = [
        compute_compatibility(a_sun="leo", b_sun="aries")["estimate_note"],
        compute_compatibility(a_sun="leo", b_sun="aries", a_moon="cancer", b_moon="pisces")[
            "estimate_note"
        ],
    ]
    for text in list(names) + notes:
        for banned in BANNED_WORDS:
            assert banned not in text, f"禁词「{banned}」出现在: {text}"
