"""
星座能量引擎测试（星光映照）。

覆盖：
- 确定性规则：同日同人两次调用同值
- 归一化：clamp [35,98] + 非整十取整
- 平滑约束：与昨日差 ≤ 15
- 天文事件表命中：满月日爱情 +6 / 新月日事业 +8 / 水逆 / 节气
- 塔罗牌偏移：圣杯 → 爱情 +2、月亮牌 → 爱情 +3 健康 -2
- 日记情绪修正：累/焦虑 → 健康 -5 爱情 -3；工作/加班 → 事业 +3
- 无出生日期回退：user.created_at 近似，不报错
- 接口鉴权：未登录 401
- zodiac 校验：12 合法值（兼容中文名）
- 历史落库：horoscope_history upsert（user+date 唯一）
"""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.config import settings
from app.db.database import async_session
from app.models.diary import DiaryEntry
from app.models.horoscope import HoroscopeHistory
from app.services.energy_engine import (
    DIM_CAREER,
    DIM_HEALTH,
    DIM_LOVE,
    DIM_SOCIAL,
    MAX_DAY_DELTA,
    MAX_ENERGY,
    MIN_ENERGY,
    ZODIAC_OFFSETS,
    astral_events_on,
    biorhythm_on,
    compute_energy,
    normalize,
    smooth,
)

BIRTH = date(1995, 6, 15)


def _dev_key_headers() -> dict[str, str]:
    return {"X-Dev-Key": settings.DEV_LOGIN_KEY}


def _login(client: TestClient) -> str:
    resp = client.post("/auth/dev-login", headers=_dev_key_headers())
    assert resp.status_code == 200
    return resp.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# 引擎单元测试
# ─────────────────────────────────────────────────────────────────────────────


def test_engine_deterministic_same_inputs_same_output():
    """同日同人（相同输入）两次计算 → 完全一致。"""
    kwargs = dict(target_date=date(2026, 9, 27), birth_date=BIRTH, zodiac="leo")
    assert compute_energy(**kwargs) == compute_energy(**kwargs)


def test_biorhythm_zero_days_is_50():
    """出生日当天 days=0 → 三条正弦均为 50。"""
    base = biorhythm_on(0)
    assert base[DIM_LOVE] == 50.0
    assert base[DIM_CAREER] == 50.0
    assert base[DIM_HEALTH] == 50.0
    assert base[DIM_SOCIAL] == 50.0


def test_biorhythm_period_full_cycle_returns_50():
    """days = 完整周期 → sin(2π)=0 → 回到 50。"""
    assert abs(biorhythm_on(23)[DIM_HEALTH] - 50.0) < 1e-9
    assert abs(biorhythm_on(28)[DIM_LOVE] - 50.0) < 1e-9
    assert abs(biorhythm_on(33)[DIM_CAREER] - 50.0) < 1e-9


def test_normalize_rounds_to_integer_non_round_ten():
    """第 6 步：取非整十（round 到个位，73 而非 70）。"""
    out = normalize({DIM_LOVE: 72.6, DIM_CAREER: 49.4, DIM_SOCIAL: 80.0, DIM_HEALTH: 57.0})
    assert out[DIM_LOVE] == 73
    assert out[DIM_CAREER] == 49
    assert out[DIM_SOCIAL] == 80
    assert all(isinstance(v, int) for v in out.values())


def test_normalize_clamps_bounds():
    """clamp [35, 98]。"""
    assert normalize({DIM_LOVE: 200.0})[DIM_LOVE] == MAX_ENERGY
    assert normalize({DIM_LOVE: -10.0})[DIM_LOVE] == MIN_ENERGY
    assert normalize({DIM_LOVE: 50.0})[DIM_LOVE] == 50


def test_engine_energy_within_bounds():
    """任意输入组合下 4 维都在 [35, 98]。"""
    for zodiac in list(ZODIAC_OFFSETS) + [None]:
        for day in (date(2026, 1, 3), date(2026, 3, 14), date(2026, 8, 12), date(2026, 9, 27)):
            result = compute_energy(target_date=day, birth_date=BIRTH, zodiac=zodiac)
            for value in result["energy"].values():
                assert MIN_ENERGY <= value <= MAX_ENERGY


def test_full_moon_day_gives_love_plus_6():
    """2026-09-27 满月 → 爱情 factor +6，健康 -3。"""
    result = compute_energy(target_date=date(2026, 9, 27), birth_date=BIRTH)
    love_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_LOVE]}
    health_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_HEALTH]}
    assert love_deltas.get("满月") == 6
    assert health_deltas.get("满月") == -3
    assert result["astral"]["type"] == "full_moon"


def test_new_moon_day_gives_career_plus_8():
    """2026-11-05 天蝎新月 → 事业 factor +8。"""
    result = compute_energy(target_date=date(2026, 11, 5), birth_date=BIRTH)
    career_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_CAREER]}
    assert career_deltas.get("新月") == 8


def test_mercury_retrograde_day_impact():
    """水逆区间（2026-09-20）→ 人际 -8、事业 -5。"""
    result = compute_energy(target_date=date(2026, 9, 20), birth_date=BIRTH)
    social_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_SOCIAL]}
    career_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_CAREER]}
    assert social_deltas.get("水逆") == -8
    assert career_deltas.get("水逆") == -5


def test_solar_term_day_gives_health_plus_3():
    """节气日（2026-08-08 立秋）→ 健康 +3。"""
    result = compute_energy(target_date=date(2026, 8, 8), birth_date=BIRTH)
    health_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_HEALTH]}
    assert health_deltas.get("节气") == 3
    assert "立秋" in result["astral"]["label"]


def test_astral_event_table_covers_year():
    """2026 事件表 ~50 条常量，且包含定稿的关键事件。"""
    from app.services.energy_engine import ASTRAL_EVENTS_2026

    assert len(ASTRAL_EVENTS_2026) >= 45
    assert astral_events_on(date(2026, 8, 12))  # 狮子座新月 + 日全食
    types = {ev["type"] for ev in astral_events_on(date(2026, 8, 12))}
    assert {"new_moon", "solar_eclipse"} <= types
    # 水逆区间是区间事件（覆盖区间内每一天）
    assert astral_events_on(date(2026, 10, 1))


class _FakeCard:
    def __init__(self, arcana, suit, card_number, name_zh):
        self.arcana = arcana
        self.suit = suit
        self.card_number = card_number
        self.name_zh = name_zh


def test_tarot_cups_gives_love_plus_2():
    """圣杯（小牌）→ 爱情 +2。"""
    card = _FakeCard("minor", "cups", 23, "圣杯二")
    result = compute_energy(target_date=date(2026, 5, 1), birth_date=BIRTH, tarot_card=card)
    love_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_LOVE]}
    assert love_deltas.get("圣杯二") == 2


def test_tarot_moon_major_gives_love_3_health_minus_2():
    """月亮（大牌 18）→ 爱情 +3、健康 -2（定稿值）。"""
    card = _FakeCard("major", None, 18, "月亮")
    result = compute_energy(target_date=date(2026, 5, 1), birth_date=BIRTH, tarot_card=card)
    love_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_LOVE]}
    health_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_HEALTH]}
    assert love_deltas.get("月亮") == 3
    assert health_deltas.get("月亮") == -2


def test_tarot_wands_gives_career_plus_2():
    """权杖（小牌）→ 事业 +2。"""
    card = _FakeCard("minor", "wands", 22, "权杖王牌")
    result = compute_energy(target_date=date(2026, 5, 1), birth_date=BIRTH, tarot_card=card)
    career_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_CAREER]}
    assert career_deltas.get("权杖王牌") == 2


def test_diary_negative_mood_correction():
    """近 7 天日记含 累/焦虑 → 健康 -5、爱情 -3。"""
    result = compute_energy(
        target_date=date(2026, 5, 1),
        birth_date=BIRTH,
        diary_texts=["今天好累，加完班回家有点焦虑"],
    )
    health_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_HEALTH]}
    love_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_LOVE]}
    assert health_deltas.get("日记:低落") == -5
    assert love_deltas.get("日记:低落") == -3


def test_diary_positive_and_work_correction():
    """日记含 开心 → 爱情 +4；含 工作/加班 → 事业 +3。"""
    result = compute_energy(
        target_date=date(2026, 5, 1),
        birth_date=BIRTH,
        diary_texts=["今天很开心，项目顺利推进，加班也值得"],
    )
    love_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_LOVE]}
    career_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_CAREER]}
    assert love_deltas.get("日记:开心") == 4
    assert career_deltas.get("日记:工作") == 3


def test_diary_ignored_outside_7_days():
    """近 7 天之外（无日记文本）→ 无日记 factor。"""
    result = compute_energy(target_date=date(2026, 5, 1), birth_date=BIRTH, diary_texts=[])
    assert all(f["name"] != "日记:低落" for f in result["factors"][DIM_HEALTH])


def test_smooth_converges_to_plus_minus_15():
    """第 7 步：与昨日差超限收敛到 ±15 内。"""
    yesterday = {DIM_LOVE: 98, DIM_CAREER: 50, DIM_SOCIAL: 50, DIM_HEALTH: 50}
    raw = smooth({DIM_LOVE: 35, DIM_CAREER: 80, DIM_SOCIAL: 50, DIM_HEALTH: 50}, yesterday)
    assert raw[DIM_LOVE] == 98 - MAX_DAY_DELTA  # 35 → 收敛到 83
    assert raw[DIM_CAREER] == 50 + MAX_DAY_DELTA  # 80 → 收敛到 65
    assert smooth(raw, None) == raw  # 无昨日记录 → 原样


def test_zodiac_offset_reflected_in_factors():
    """狮子座常量偏移 → 事业 +3、爱情 +2 出现在 factors。"""
    result = compute_energy(target_date=date(2026, 5, 1), birth_date=BIRTH, zodiac="leo")
    career_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_CAREER]}
    love_deltas = {f["name"]: f["delta"] for f in result["factors"][DIM_LOVE]}
    assert career_deltas.get("狮子座") == 3
    assert love_deltas.get("狮子座") == 2


def test_no_birth_date_fallback_uses_created_at():
    """无出生日期（用 created_at 近似）→ 不报错且结果确定。"""
    fallback = date(2026, 1, 1)
    r1 = compute_energy(target_date=date(2026, 8, 8), birth_date=fallback)
    r2 = compute_energy(target_date=date(2026, 8, 8), birth_date=fallback)
    assert r1 == r2


def test_summary_and_tip_rule_generated():
    """summary/tip 由规则模板生成（非空，无恐吓词）。"""
    result = compute_energy(target_date=date(2026, 9, 27), birth_date=BIRTH, zodiac="leo")
    assert result["summary"]
    assert result["tip"]
    for banned in ("大凶", "血光", "灾", "祸"):
        assert banned not in result["summary"]


# ─────────────────────────────────────────────────────────────────────────────
# API 集成测试
# ─────────────────────────────────────────────────────────────────────────────


def test_daily_requires_auth(client: TestClient):
    """GET /horoscope/daily 未登录 → 401。"""
    assert client.get("/horoscope/daily").status_code == 401


def test_user_zodiac_requires_auth(client: TestClient):
    """POST /user/zodiac 未登录 → 401。"""
    assert client.post("/user/zodiac", json={"zodiac": "leo"}).status_code == 401


def test_user_birth_requires_auth(client: TestClient):
    """POST /user/birth 未登录 → 401。"""
    assert client.post("/user/birth", json={"birth_date": "1995-06-15"}).status_code == 401


def test_daily_structure_and_determinism(client: TestClient):
    """登录后 GET /horoscope/daily：结构完整；同日两次调用完全一致。"""
    token = _login(client)
    headers = _auth(token)

    r1 = client.get("/horoscope/daily", params={"date": "2026-05-20"}, headers=headers)
    r2 = client.get("/horoscope/daily", params={"date": "2026-05-20"}, headers=headers)
    assert r1.status_code == 200
    assert r1.json() == r2.json()  # 确定性：同日同人两次调用同值

    data = r1.json()
    assert data["date"] == "2026-05-20"
    assert set(data["energy"].keys()) == {DIM_LOVE, DIM_CAREER, DIM_SOCIAL, DIM_HEALTH}
    for value in data["energy"].values():
        assert isinstance(value, int)
        assert MIN_ENERGY <= value <= MAX_ENERGY
    # 解释链
    assert set(data["factors"].keys()) == {DIM_LOVE, DIM_CAREER, DIM_SOCIAL, DIM_HEALTH}
    for dim, items in data["factors"].items():
        assert all({"name", "delta"} <= set(f.keys()) for f in items)
    # 天象
    assert data["astral"]["type"]
    assert data["astral"]["label"]
    assert data["astral"]["note"]
    # 今日牌 + 文案
    assert data["tarot"]["name"]
    assert data["tarot"]["name_en"]
    assert data["tarot"]["image"].startswith("https://")
    assert data["summary"]
    assert data["tip"]


def test_daily_no_birth_date_fallback_200(client: TestClient):
    """用户无 birth_date → 用 created_at 近似，接口仍 200。"""
    token = _login(client)
    resp = client.get("/horoscope/daily", params={"date": "2026-03-05"}, headers=_auth(token))
    assert resp.status_code == 200


def test_daily_invalid_date_400(client: TestClient):
    """非法日期 → 400。"""
    token = _login(client)
    resp = client.get("/horoscope/daily", params={"date": "2026/05/20"}, headers=_auth(token))
    assert resp.status_code == 400


def test_full_moon_factor_via_api(client: TestClient):
    """API 层面满月日（2026-09-27）爱情 factor 含 满月 +6。"""
    token = _login(client)
    resp = client.get("/horoscope/daily", params={"date": "2026-09-27"}, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    love_factors = {f["name"]: f["delta"] for f in data["factors"][DIM_LOVE]}
    assert love_factors.get("满月") == 6
    assert data["astral"]["type"] == "full_moon"


def test_smoothing_via_api(client: TestClient):
    """连续两天：与昨日差 ≤ 15（读昨日历史平滑约束）。"""
    token = _login(client)
    headers = _auth(token)
    r_prev = client.get("/horoscope/daily", params={"date": "2026-08-07"}, headers=headers)
    r_today = client.get("/horoscope/daily", params={"date": "2026-08-08"}, headers=headers)
    assert r_prev.status_code == 200 and r_today.status_code == 200
    prev_energy = r_prev.json()["energy"]
    today_energy = r_today.json()["energy"]
    for dim in (DIM_LOVE, DIM_CAREER, DIM_SOCIAL, DIM_HEALTH):
        assert abs(today_energy[dim] - prev_energy[dim]) <= MAX_DAY_DELTA


def test_zodiac_save_and_validate(client: TestClient):
    """POST /user/zodiac：保存生效、响应体现、非法值 400。"""
    token = _login(client)
    headers = _auth(token)

    # 非法星座 → 400
    bad = client.post("/user/zodiac", json={"zodiac": "dragon"}, headers=headers)
    assert bad.status_code == 400

    # 合法 key 保存 → 生效
    ok = client.post("/user/zodiac", json={"zodiac": "leo"}, headers=headers)
    assert ok.status_code == 200
    assert ok.json()["zodiac"] == "leo"

    # GET /horoscope/daily 返回该星座，且 factors 含星座偏移
    resp = client.get("/horoscope/daily", params={"date": "2026-04-15"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["zodiac"] == "leo"
    career_factors = {f["name"]: f["delta"] for f in resp.json()["factors"][DIM_CAREER]}
    assert career_factors.get("狮子座") == ZODIAC_OFFSETS["leo"][DIM_CAREER]

    # 中文名也接受（归一化为 key）
    cn = client.post("/user/zodiac", json={"zodiac": "狮子座"}, headers=headers)
    assert cn.status_code == 200
    assert cn.json()["zodiac"] == "leo"


def test_birth_save_and_validate(client: TestClient):
    """POST /user/birth：保存生效；非法日期 400。"""
    token = _login(client)
    headers = _auth(token)

    bad = client.post("/user/birth", json={"birth_date": "not-a-date"}, headers=headers)
    assert bad.status_code == 400

    future = client.post("/user/birth", json={"birth_date": "2099-01-01"}, headers=headers)
    assert future.status_code == 400

    ok = client.post(
        "/user/birth",
        json={"birth_date": "1995-06-15", "birth_time": "08:30", "birth_city": "北京"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.json()["birth_date"] == "1995-06-15"
    assert ok.json()["birth_time"] == "08:30"
    assert ok.json()["birth_city"] == "北京"


def test_history_persisted_and_upsert(client: TestClient):
    """能量历史落库：user+date 唯一，重复请求不产生重复行。"""
    token = _login(client)
    headers = _auth(token)
    target = "2026-06-01"

    r1 = client.get("/horoscope/daily", params={"date": target}, headers=headers)
    r2 = client.get("/horoscope/daily", params={"date": target}, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200

    import asyncio

    async def _count_rows():
        async with async_session() as session:
            # 找到当前登录用户
            from app.models.user import User

            user = (await session.execute(
                select(User).where(User.openid == "dev_test_user_001")
            )).scalar_one()
            count = (await session.execute(
                select(func.count()).select_from(HoroscopeHistory).where(
                    HoroscopeHistory.user_id == user.id,
                    HoroscopeHistory.date == date.fromisoformat(target),
                )
            )).scalar_one()
            row = (await session.execute(
                select(HoroscopeHistory).where(
                    HoroscopeHistory.user_id == user.id,
                    HoroscopeHistory.date == date.fromisoformat(target),
                )
            )).scalar_one()
            return count, row.energy

    count, energy = asyncio.run(_count_rows())
    assert count == 1  # upsert：唯一约束不重复
    assert energy == r1.json()["energy"]  # 落库值与返回一致


def test_diary_mood_affects_horoscope_via_api(client: TestClient):
    """日记修正 API 链路：今日日记含 加班/累 → GET 今日能量含 日记:工作 +3。"""
    token = _login(client)
    headers = _auth(token)

    # 创建今日日记（reflection 含关键词）
    entry = client.post(
        "/diary/entries",
        json={"mood": "anxious", "reflection": "今天工作加班到很晚，很累"},
        headers=headers,
    )
    assert entry.status_code in (200, 201)

    # 今日能量（date 缺省 = 今天）
    resp = client.get("/horoscope/daily", headers=headers)
    assert resp.status_code == 200
    career_factors = {f["name"]: f["delta"] for f in resp.json()["factors"][DIM_CAREER]}
    health_factors = {f["name"]: f["delta"] for f in resp.json()["factors"][DIM_HEALTH]}
    assert career_factors.get("日记:工作") == 3
    assert health_factors.get("日记:低落") == -5


def test_tarot_card_same_as_cards_daily(client: TestClient):
    """今日牌与 /cards/daily 一致（同一确定性选牌逻辑；/cards/daily 用今天）。"""
    from datetime import date as _date

    token = _login(client)
    headers = _auth(token)
    today = _date.today().isoformat()

    horoscope = client.get("/horoscope/daily", params={"date": today}, headers=headers)
    daily_card = client.get("/cards/daily", headers=headers)
    assert horoscope.status_code == 200 and daily_card.status_code == 200
    assert horoscope.json()["tarot"]["name"] == daily_card.json()["name_zh"]


# ─────────────────────────────────────────────────────────────────────────────
# 开发06 · 输入校验加固：birth_time 范围 / birth_city 长度
# ─────────────────────────────────────────────────────────────────────────────


def test_birth_time_out_of_range_rejected(client: TestClient):
    """25:99 等非法时刻必须 400（原先只查格式不查范围，已修复）。"""
    token = _login(client)
    headers = _auth(token)

    for bad in ("25:99", "24:00", "12:60", "08:30:70", "99:00"):
        resp = client.post("/user/birth", json={"birth_time": bad}, headers=headers)
        assert resp.status_code == 400, f"birth_time={bad} 应 400，实际 {resp.status_code}: {resp.text}"

    for good in ("23:59", "0:00", "08:30", "06:15:30"):
        resp = client.post("/user/birth", json={"birth_time": good}, headers=headers)
        assert resp.status_code == 200, f"birth_time={good} 应 200，实际 {resp.status_code}: {resp.text}"


def test_birth_city_overlong_rejected(client: TestClient):
    """birth_city 超过 100 字 → 400。"""
    token = _login(client)
    headers = _auth(token)
    resp = client.post("/user/birth", json={"birth_city": "城" * 101}, headers=headers)
    assert resp.status_code == 400, resp.text
    resp = client.post("/user/birth", json={"birth_city": "北京"}, headers=headers)
    assert resp.status_code == 200, resp.text
