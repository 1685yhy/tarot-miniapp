"""
月相计算测试 —— 确定性天文算法（无第三方库）。

用已知天文事实互验：
- 锚点 2000-01-06 18:14 UTC 是新月（历书参考新月）
- 2026-08-12 日全食 → 新月（本方案新月日 ±1 天内）
- 2026-08-28 月偏食 → 满月（方案精确命中当天）
- 新月 + 半周期 ≈ 满月；周期内相位顺序自洽
"""

from datetime import date

from app.services.moon import (
    SYNODIC_MONTH,
    moon_age_on,
    moon_phase_on,
    next_full_moon_after,
    next_new_moon_after,
)

VALID_PHASES = {"new_moon", "waxing", "first_quarter", "full_moon", "last_quarter", "waning"}


def test_anchor_is_new_moon():
    """锚点 2000-01-06 必须是新月。"""
    phase = moon_phase_on(date(2000, 1, 6))
    assert phase["phase"] == "new_moon"
    assert phase["emoji"] == "🌑"
    assert phase["label"] == "新月"


def test_anchor_plus_half_cycle_is_full_moon():
    """锚点 + 半周期（≈14.77 天）是满月。"""
    full = moon_phase_on(date(2000, 1, 21))
    assert full["phase"] == "full_moon"
    assert full["label"] == "满月"


def test_quarter_days_around_anchor():
    """锚点 + 1/4 周期 = 上弦，+ 3/4 周期 = 下弦。"""
    first_q = moon_phase_on(date(2000, 1, 14))
    assert first_q["phase"] == "first_quarter"
    last_q = moon_phase_on(date(2000, 1, 28))
    assert last_q["phase"] == "last_quarter"


def test_known_solar_eclipse_2026_08_12_is_new_moon_within_one_day():
    """2026-08-12 日全食 → 新月（方案新/满月判定与其对齐在 ±1 天内）。"""
    eclipse_day = date(2026, 8, 12)
    phases = {moon_phase_on(eclipse_day)["phase"], moon_phase_on(date(2026, 8, 13))["phase"]}
    assert "new_moon" in phases


def test_known_lunar_eclipse_2026_08_28_is_full_moon():
    """2026-08-28 月偏食 → 满月当天（方案精确命中）。"""
    assert moon_phase_on(date(2026, 8, 28))["phase"] == "full_moon"


def test_cycle_length_and_determinism():
    """周期长度 ≈ 29.53 天；同输入必同输出（确定性）。"""
    nm1 = next_new_moon_after(date(2026, 8, 4))
    nm2 = next_new_moon_after(nm1)
    assert abs((nm2 - nm1).days - SYNODIC_MONTH) <= 1

    d = date(2026, 8, 9)
    assert moon_phase_on(d) == moon_phase_on(d)


def test_phase_keys_always_valid():
    """任意日期返回的 phase 都必须是六态之一，且 emoji/label 存在。"""
    d = date(2026, 1, 1)
    for _ in range(120):  # 扫 120 天
        phase = moon_phase_on(d)
        assert phase["phase"] in VALID_PHASES
        assert phase["emoji"]
        assert phase["label"]
        d = d.fromordinal(d.toordinal() + 1)


def test_next_new_moon_is_new_moon_day():
    """next_new_moon_after 返回的日期，当天确实被判定为新月。"""
    d = date(2026, 8, 4)
    nm = next_new_moon_after(d)
    assert nm > d
    assert moon_phase_on(nm)["phase"] == "new_moon"


def test_next_full_moon_is_full_moon_day():
    """next_full_moon_after 返回的日期，当天确实被判定为满月。"""
    d = date(2026, 8, 9)
    fm = next_full_moon_after(d)
    assert fm > d
    assert moon_phase_on(fm)["phase"] == "full_moon"


def test_next_new_and_full_alternate():
    """新月与满月交替出现：两次新月之间恰有一个满月。"""
    nm = next_new_moon_after(date(2026, 8, 4))
    fm = next_full_moon_after(nm)
    nm2 = next_new_moon_after(fm)
    assert nm < fm < nm2
    assert (fm - nm).days >= 13
    assert (fm - nm).days <= 17
    assert (nm2 - fm).days >= 13
    assert (nm2 - fm).days <= 17


def test_moon_age_range():
    """月龄永远在 [0, 29.53) 区间。"""
    d = date(2026, 1, 1)
    for _ in range(100):
        age = moon_age_on(d)
        assert 0 <= age < SYNODIC_MONTH
        d = d.fromordinal(d.toordinal() + 1)


def test_phase_response_contains_dates():
    """moon_phase_on 响应包含 next_new_moon / next_full_moon。"""
    phase = moon_phase_on(date(2026, 8, 9))
    assert phase["next_new_moon"] >= phase["date"]
    assert phase["next_full_moon"] >= phase["date"]
