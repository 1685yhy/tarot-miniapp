"""
Tests for the starlight journal calendar API (T1-1 星光手账月历聚合).

Covers:
- GET /journal/calendar — 401 when not logged in
- Empty month → days=[] and zero stats
- star_color determinism (same date twice + equals build_today_guidance result)
- 6 moods → correct 5-level brightness (excited=5 ... anxious|sad=1)
- has_reflection flips with reflection presence/absence
- month stats counting (bright_count >= 4, dim_count <= 2, streak)
- API 层跨月 streak：月初前连续回扫（跨月连续 / 长跨月 / 断档截断）
- invalid year/month params → 422
- mood=None / 未知 mood → 亮度 2 兜底
- current_streak pure function (0 / consecutive / gap breaks / cross-month)
"""

import asyncio
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import async_session
from app.models.diary import DiaryEntry
from app.models.user import User
from app.services.energy_engine import build_today_guidance
from app.services.journal import MOOD_BRIGHTNESS, current_streak
from app.services.stardust import tier_for
from app.utils.auth import create_token

CALENDAR_URL = "/journal/calendar"


def _run(coro):
    """Run an async coroutine on a fresh loop (same pattern as test_weekly_report)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_user(
    zodiac: str | None = None,
    *,
    stardust_total: int | None = None,
    star_tier: int | None = None,
    reward_week: str | None = None,
) -> tuple[str, str]:
    """Create an isolated user (with optional zodiac) and return (user_id, token).

    stardust_total / star_tier / reward_week：奖励测试用（T1-3），缺省不传
    （传 None 会覆盖模型默认值，故按需组装 kwargs）。
    """
    kwargs: dict = {}
    if stardust_total is not None:
        kwargs["stardust_total"] = stardust_total
    if star_tier is not None:
        kwargs["star_tier"] = star_tier
    if reward_week is not None:
        kwargs["journal_streak_reward_week"] = reward_week
    async with async_session() as session:
        user = User(
            openid=f"journal_test_{uuid.uuid4().hex[:10]}",
            nickname="手账测试",
            zodiac=zodiac,
            **kwargs,
        )
        session.add(user)
        await session.flush()
        user_id = str(user.id)
        token = create_token(user.id)
        await session.commit()
        return user_id, token


async def _seed_entries(user_id: str, rows: list[tuple[date, str | None, str | None, int | None]]) -> None:
    """Insert diary entries: (entry_date, mood, reflection, card_id)."""
    async with async_session() as session:
        for entry_date, mood, reflection, card_id in rows:
            session.add(DiaryEntry(
                id=str(uuid.uuid4()),
                user_id=user_id,
                entry_date=entry_date,
                mood=mood,
                reflection=reflection,
                card_id=card_id,
            ))
        await session.commit()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestCalendarAuth:
    """GET /journal/calendar — authentication"""

    def test_requires_login(self, client: TestClient):
        """Not logged in → 401."""
        resp = client.get(f"{CALENDAR_URL}?year=2026&month=8")
        assert resp.status_code == 401


class TestCalendarEmptyMonth:
    """GET /journal/calendar — empty month"""

    def test_empty_month_returns_empty_days_and_zero_stats(self, client: TestClient):
        """Fresh user, no entries → days=[] and all stats 0."""
        _, token = _run(_make_user())
        resp = client.get(f"{CALENDAR_URL}?year=2026&month=8", headers=_headers(token))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["days"] == []
        assert data["stats"] == {
            "days_recorded": 0,
            "bright_count": 0,
            "dim_count": 0,
            "current_streak": 0,
        }


class TestCalendarDeterminism:
    """star_color must be deterministic per (date, zodiac)."""

    def test_star_color_deterministic_and_matches_guidance(self, client: TestClient):
        """Two calls for the same date return the same star_color, equal to
        build_today_guidance(date, zodiac)['star_color']."""
        user_id, token = _run(_make_user(zodiac="leo"))
        _run(_seed_entries(user_id, [(date(2026, 8, 15), "happy", "八月十五", 1)]))
        headers = _headers(token)

        resp1 = client.get(f"{CALENDAR_URL}?year=2026&month=8", headers=headers)
        resp2 = client.get(f"{CALENDAR_URL}?year=2026&month=8", headers=headers)
        assert resp1.status_code == 200, resp1.text
        day1 = resp1.json()["days"][0]
        day2 = resp2.json()["days"][0]
        assert day1["date"] == "2026-08-15"
        assert day1["star_color"] == day2["star_color"], "star_color must be deterministic"

        expected = build_today_guidance(date(2026, 8, 15), "leo")["star_color"]
        assert day1["star_color"] == expected


class TestBrightnessMapping:
    """6 档情绪 → 5 档星光亮度"""

    def test_mood_brightness_constant_matches_spec(self):
        assert MOOD_BRIGHTNESS == {
            "excited": 5,
            "happy": 4,
            "calm": 3,
            "thoughtful": 2,
            "anxious": 1,
            "sad": 1,
        }

    def test_six_moods_map_to_correct_brightness(self, client: TestClient):
        user_id, token = _run(_make_user())
        moods = [
            ("excited", 5),
            ("happy", 4),
            ("calm", 3),
            ("thoughtful", 2),
            ("anxious", 1),
            ("sad", 1),
        ]
        _run(_seed_entries(user_id, [
            (date(2026, 7, 1 + i), mood, None, None) for i, (mood, _) in enumerate(moods)
        ]))
        resp = client.get(f"{CALENDAR_URL}?year=2026&month=7", headers=_headers(token))
        assert resp.status_code == 200, resp.text
        by_date = {d["date"]: d for d in resp.json()["days"]}
        assert len(by_date) == 6
        for i, (mood, expected) in enumerate(moods):
            day = by_date[f"2026-07-{1 + i:02d}"]
            assert day["mood"] == mood
            assert day["brightness"] == expected, f"{mood} 应映射到亮度 {expected}"


class TestHasReflection:
    """has_reflection 随 reflection 有无翻转"""

    def test_reflection_presence_flips_flag(self, client: TestClient):
        user_id, token = _run(_make_user())
        _run(_seed_entries(user_id, [
            (date(2026, 8, 1), "calm", "今天写了一段感悟", 1),
            (date(2026, 8, 2), "calm", None, 1),
            (date(2026, 8, 3), "calm", "", 1),
        ]))
        resp = client.get(f"{CALENDAR_URL}?year=2026&month=8", headers=_headers(token))
        assert resp.status_code == 200, resp.text
        by_date = {d["date"]: d for d in resp.json()["days"]}
        assert by_date["2026-08-01"]["has_reflection"] is True
        assert by_date["2026-08-02"]["has_reflection"] is False
        assert by_date["2026-08-03"]["has_reflection"] is False


class TestMonthStats:
    """月度统计：days_recorded / bright_count(≥4) / dim_count(≤2)"""

    def test_stats_counts_and_date_order(self, client: TestClient):
        user_id, token = _run(_make_user())
        # 动态构造“上个月”，避免固定日期断言（固定 2026-07 依赖今天已过该月）
        last_month = date.today().replace(day=1) - timedelta(days=1)
        y, m = last_month.year, last_month.month
        _run(_seed_entries(user_id, [
            (date(y, m, 1), "excited", "a", 1),   # brightness 5 → bright
            (date(y, m, 3), "happy", "b", 1),     # brightness 4 → bright
            (date(y, m, 5), "calm", "c", 1),      # brightness 3 → neither
            (date(y, m, 7), "anxious", "d", 1),   # brightness 1 → dim
            (date(y, m, 9), "sad", "e", 1),       # brightness 1 → dim
        ]))
        resp = client.get(f"{CALENDAR_URL}?year={y}&month={m}", headers=_headers(token))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["stats"]["days_recorded"] == 5
        assert data["stats"]["bright_count"] == 2
        assert data["stats"]["dim_count"] == 2
        assert data["stats"]["current_streak"] == 0  # 整月已完全过去 → 与今天不连续
        # days sorted ascending by date
        assert [d["date"] for d in data["days"]] == [
            f"{y}-{m:02d}-01", f"{y}-{m:02d}-03", f"{y}-{m:02d}-05", f"{y}-{m:02d}-07",
            f"{y}-{m:02d}-09",
        ]
        # card_id passthrough
        assert all(d["card_id"] == 1 for d in data["days"])

    def test_other_users_entries_not_counted(self, client: TestClient):
        user_id, token = _run(_make_user())
        other_id, _ = _run(_make_user())
        _run(_seed_entries(user_id, [(date(2026, 8, 1), "happy", "x", 1)]))
        _run(_seed_entries(other_id, [
            (date(2026, 8, 2), "excited", "y", 1),
            (date(2026, 8, 3), "excited", "z", 1),
        ]))
        resp = client.get(f"{CALENDAR_URL}?year=2026&month=8", headers=_headers(token))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert [d["date"] for d in data["days"]] == ["2026-08-01"]
        assert data["stats"]["days_recorded"] == 1


class TestCalendarStreak:
    """API 层 current_streak（以 date.today() 为锚点）"""

    def test_streak_counts_consecutive_days_ending_today(self, client: TestClient):
        user_id, token = _run(_make_user())
        today = date.today()
        _run(_seed_entries(user_id, [
            (today, "happy", "t", 1),
            (today - timedelta(days=1), "happy", "y", 1),
            (today - timedelta(days=2), "happy", "b", 1),
        ]))
        resp = client.get(
            f"{CALENDAR_URL}?year={today.year}&month={today.month}",
            headers=_headers(token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["stats"]["current_streak"] == 3

    def test_streak_breaks_on_missing_day(self, client: TestClient):
        user_id, token = _run(_make_user())
        today = date.today()
        _run(_seed_entries(user_id, [
            (today, "calm", "t", 1),
            (today - timedelta(days=2), "calm", "b", 1),  # yesterday missing → break
        ]))
        resp = client.get(
            f"{CALENDAR_URL}?year={today.year}&month={today.month}",
            headers=_headers(token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["stats"]["current_streak"] == 1

    def test_streak_spans_month_boundary(self, client: TestClient):
        """跨月连续：月初前的连续记录计入当月 streak（如 7-31→8-11 返回 12）。"""
        user_id, token = _run(_make_user())
        today = date.today()
        month_start = today.replace(day=1)
        # 月初前 4 天起连续到今天（无论今天几号都必然跨月）
        seed_start = month_start - timedelta(days=4)
        _run(_seed_entries(user_id, [
            (seed_start + timedelta(days=i), "happy", "x", 1)
            for i in range((today - seed_start).days + 1)
        ]))
        resp = client.get(
            f"{CALENDAR_URL}?year={today.year}&month={today.month}",
            headers=_headers(token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["stats"]["current_streak"] == (today - seed_start).days + 1
        # days 仍只含当月记录，跨月部分只进 streak
        assert len(data["days"]) == (today - month_start).days + 1

    def test_long_streak_spans_multiple_months(self, client: TestClient):
        """长跨月：连续 60+ 天（必然跨越至少两个月界）返回完整天数，不在月初截断。"""
        user_id, token = _run(_make_user())
        today = date.today()
        seed_start = today - timedelta(days=60)
        _run(_seed_entries(user_id, [
            (seed_start + timedelta(days=i), "calm", "x", 1)
            for i in range(61)  # 60 天前到今天，含两端共 61 天
        ]))
        resp = client.get(
            f"{CALENDAR_URL}?year={today.year}&month={today.month}",
            headers=_headers(token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["stats"]["current_streak"] == 61

    def test_streak_cross_month_truncates_at_gap(self, client: TestClient):
        """断档：月中缺一天即截断，月初前的更早记录不得并入。"""
        user_id, token = _run(_make_user())
        today = date.today()
        month_start = today.replace(day=1)
        seed_start = month_start - timedelta(days=6)
        gap_day = seed_start + timedelta(days=4)  # 中间缺一天 → 之后全部截断
        rows = [
            (seed_start + timedelta(days=i), "happy", "x", 1)
            for i in range((today - seed_start).days + 1)
            if seed_start + timedelta(days=i) != gap_day
        ]
        _run(_seed_entries(user_id, rows))
        resp = client.get(
            f"{CALENDAR_URL}?year={today.year}&month={today.month}",
            headers=_headers(token),
        )
        assert resp.status_code == 200, resp.text
        # 断档后只数到今天为止的连续段：今天−断档日 之间的天（不含断档日）
        expected = (today - gap_day).days
        assert resp.json()["stats"]["current_streak"] == expected


class TestCalendarValidation:
    """GET /journal/calendar — 非法参数 → 422"""

    def test_out_of_range_year_month_returns_422(self, client: TestClient):
        _, token = _run(_make_user())
        headers = _headers(token)
        for params in (
            "year=1999&month=8",   # year < 2000
            "year=2101&month=8",   # year > 2100
            "year=2026&month=0",   # month < 1
            "year=2026&month=13",  # month > 12
        ):
            resp = client.get(f"{CALENDAR_URL}?{params}", headers=headers)
            assert resp.status_code == 422, params

    def test_missing_or_non_integer_params_returns_422(self, client: TestClient):
        _, token = _run(_make_user())
        headers = _headers(token)
        assert client.get(f"{CALENDAR_URL}?year=2026", headers=headers).status_code == 422
        assert client.get(f"{CALENDAR_URL}?month=8", headers=headers).status_code == 422
        assert client.get(f"{CALENDAR_URL}?year=abc&month=8", headers=headers).status_code == 422


class TestMoodFallback:
    """缺失/未知 mood → 按“思考”(2) 兜底"""

    def test_null_mood_falls_back_to_thoughtful_brightness(self, client: TestClient):
        user_id, token = _run(_make_user())
        _run(_seed_entries(user_id, [(date(2026, 8, 5), None, None, None)]))
        resp = client.get(f"{CALENDAR_URL}?year=2026&month=8", headers=_headers(token))
        assert resp.status_code == 200, resp.text
        day = resp.json()["days"][0]
        assert day["mood"] is None
        assert day["brightness"] == 2  # MOOD_BRIGHTNESS["thoughtful"]

    def test_null_and_unknown_mood_fallback_unit(self):
        from app.services.journal import brightness_for

        assert brightness_for(None) == 2
        assert brightness_for("not-a-mood") == 2
        assert brightness_for("") == 2


class TestCurrentStreak:
    """current_streak 纯函数"""

    def test_no_records_returns_zero(self):
        assert current_streak(set(), date(2026, 8, 11)) == 0

    def test_three_consecutive_days(self):
        dates = {date(2026, 8, 9), date(2026, 8, 10), date(2026, 8, 11)}
        assert current_streak(dates, date(2026, 8, 11)) == 3

    def test_gap_breaks_streak(self):
        # today and day-before-yesterday recorded, yesterday missing → 1
        dates = {date(2026, 8, 9), date(2026, 8, 11)}
        assert current_streak(dates, date(2026, 8, 11)) == 1
        # today itself not recorded → 0
        dates = {date(2026, 8, 9), date(2026, 8, 10)}
        assert current_streak(dates, date(2026, 8, 11)) == 0

    def test_cross_month_consecutive_counts(self):
        dates = {date(2026, 8, 1), date(2026, 7, 31), date(2026, 7, 30)}
        assert current_streak(dates, date(2026, 8, 1)) == 3


# ═══════════════════════════════════════════════════════════════════════
# T1-3 · POST /journal/entries 手账记录 + 连续 7 天星尘奖励（ISO 周幂等）
# ═══════════════════════════════════════════════════════════════════════

JOURNAL_ENTRIES_URL = "/journal/entries"


def _iso_week_key(day: date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


async def _fetch_user_stardust(user_id: str) -> tuple[int, int | None, str | None]:
    """返回 (stardust_total, star_tier, journal_streak_reward_week)。"""
    async with async_session() as session:
        row = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()
        return row.stardust_total, row.star_tier, row.journal_streak_reward_week


class TestJournalEntryAuth:
    """POST /journal/entries — 鉴权"""

    def test_requires_login(self, client: TestClient):
        resp = client.post(JOURNAL_ENTRIES_URL, json={"mood": "happy"})
        assert resp.status_code == 401


class TestJournalEntryCreate:
    """POST /journal/entries — 记录/更新今日星点"""

    def test_create_entry_returns_mood_brightness_star_color_and_card(self, client: TestClient):
        """新建记录：mood/brightness/star_color/card 正确，streak=1、reward=false。"""
        _, token = _run(_make_user(zodiac="leo"))
        resp = client.post(
            JOURNAL_ENTRIES_URL,
            json={"mood": "excited", "reflection": "今天星光很亮"},
            headers=_headers(token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        today = date.today()
        assert data["date"] == today.isoformat()
        assert data["mood"] == "excited"
        assert data["brightness"] == 5  # MOOD_BRIGHTNESS["excited"]
        assert data["star_color"] == build_today_guidance(today, "leo")["star_color"]
        assert data["card"] is not None
        for field in ("id", "name_zh", "meaning_upright"):
            assert field in data["card"], f"card 缺少 {field}"
        assert data["reflection"] == "今天星光很亮"
        assert data["streak"] == 1
        assert data["reward"] is False

    def test_same_day_resubmit_updates_instead_of_duplicating(self, client: TestClient):
        """同日再次提交 → 更新而非新建（无重复行）。"""
        user_id, token = _run(_make_user())
        headers = _headers(token)
        resp1 = client.post(
            JOURNAL_ENTRIES_URL,
            json={"mood": "sad", "reflection": "第一次"},
            headers=headers,
        )
        assert resp1.status_code == 200, resp1.text
        entry_id = resp1.json()["id"]

        resp2 = client.post(
            JOURNAL_ENTRIES_URL,
            json={"mood": "happy", "reflection": "更新了"},
            headers=headers,
        )
        assert resp2.status_code == 200, resp2.text
        data2 = resp2.json()
        assert data2["id"] == entry_id, "同日应更新同一行"
        assert data2["mood"] == "happy"
        assert data2["reflection"] == "更新了"

        async def _count_today_rows() -> int:
            async with async_session() as session:
                result = await session.execute(
                    select(DiaryEntry).where(
                        DiaryEntry.user_id == user_id,
                        DiaryEntry.entry_date == date.today(),
                    )
                )
                return len(result.scalars().all())

        assert _run(_count_today_rows()) == 1, "同日提交不得产生重复行"

    def test_invalid_mood_returns_422(self, client: TestClient):
        """mood 必填且限 6 档枚举 → 非法 422。"""
        _, token = _run(_make_user())
        headers = _headers(token)
        assert (
            client.post(JOURNAL_ENTRIES_URL, json={"mood": "angry"}, headers=headers).status_code
            == 422
        )
        assert client.post(JOURNAL_ENTRIES_URL, json={}, headers=headers).status_code == 422
        assert (
            client.post(JOURNAL_ENTRIES_URL, json={"mood": None}, headers=headers).status_code
            == 422
        )

    def test_provided_card_id_is_used(self, client: TestClient):
        _, token = _run(_make_user())
        resp = client.post(
            JOURNAL_ENTRIES_URL,
            json={"mood": "calm", "card_id": 7},
            headers=_headers(token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["card"]["id"] == 7

    def test_nonexistent_card_id_returns_404(self, client: TestClient):
        _, token = _run(_make_user())
        resp = client.post(
            JOURNAL_ENTRIES_URL,
            json={"mood": "calm", "card_id": 99999},
            headers=_headers(token),
        )
        assert resp.status_code == 404


class TestJournalStreakReward:
    """连续 7 天记录 → +1 星尘（ISO 周幂等，同周不重复；star_tier 同步推导）"""

    def test_seventh_day_grants_reward_and_syncs_tier(self, client: TestClient):
        """前 6 天连续（含昨天）+ 今天 POST → 第 7 天：reward=true、星尘+1、星阶同步。"""
        user_id, token = _run(_make_user(stardust_total=6, star_tier=0))
        today = date.today()
        _run(_seed_entries(user_id, [
            (today - timedelta(days=i), "happy", "x", 1) for i in range(1, 7)
        ]))
        resp = client.post(
            JOURNAL_ENTRIES_URL, json={"mood": "happy"}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["streak"] == 7
        assert data["reward"] is True
        stardust, tier, week = _run(_fetch_user_stardust(user_id))
        assert stardust == 7, "奖励应 +1 星尘"
        assert tier == tier_for(7) == 1, "星尘 7 → 星阶 1「星光」"
        assert week == _iso_week_key(today), "应记录本周 ISO 周键"

    def test_reward_idempotent_within_same_week(self, client: TestClient):
        """同周再次提交（同日更新）→ 不再奖励、星尘不变。"""
        user_id, token = _run(_make_user(stardust_total=6, star_tier=0))
        today = date.today()
        _run(_seed_entries(user_id, [
            (today - timedelta(days=i), "happy", "x", 1) for i in range(1, 7)
        ]))
        headers = _headers(token)
        resp1 = client.post(JOURNAL_ENTRIES_URL, json={"mood": "happy"}, headers=headers)
        assert resp1.status_code == 200, resp1.text
        assert resp1.json()["reward"] is True

        resp2 = client.post(JOURNAL_ENTRIES_URL, json={"mood": "calm"}, headers=headers)
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["reward"] is False

        stardust, tier, _ = _run(_fetch_user_stardust(user_id))
        assert stardust == 7, "同周不重复发放"
        assert tier == 1

    def test_eighth_day_same_week_no_second_reward(self, client: TestClient):
        """同周第 8 天记录（7 天前已达标发过奖、周键已写）→ reward=false。"""
        today = date.today()
        user_id, token = _run(_make_user(
            stardust_total=7,
            star_tier=1,
            reward_week=_iso_week_key(today),
        ))
        # 前 7 天连续 → 今天提交后为第 8 天，且本周已发过奖
        _run(_seed_entries(user_id, [
            (today - timedelta(days=i), "happy", "x", 1) for i in range(1, 8)
        ]))
        resp = client.post(
            JOURNAL_ENTRIES_URL, json={"mood": "happy"}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["streak"] == 8
        assert data["reward"] is False
        stardust, _, week = _run(_fetch_user_stardust(user_id))
        assert stardust == 7, "同周第 8 天不得再奖励"
        assert week == _iso_week_key(today)

    def test_streak_of_eight_first_time_rewards(self, client: TestClient):
        """阈值边界：连续 ≥7 即奖励——第 8 天首次达标（本周未奖）同样发放。"""
        user_id, token = _run(_make_user())
        today = date.today()
        _run(_seed_entries(user_id, [
            (today - timedelta(days=i), "happy", "x", 1) for i in range(1, 8)
        ]))
        resp = client.post(
            JOURNAL_ENTRIES_URL, json={"mood": "happy"}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["streak"] == 8
        assert data["reward"] is True
        stardust, tier, week = _run(_fetch_user_stardust(user_id))
        assert stardust == 1
        assert tier == tier_for(1) == 0
        assert week == _iso_week_key(today)

    def test_six_days_no_reward(self, client: TestClient):
        """边界：连续 6 天（5 天已录 + 今天）→ 不奖励。"""
        user_id, token = _run(_make_user())
        today = date.today()
        _run(_seed_entries(user_id, [
            (today - timedelta(days=i), "calm", "x", 1) for i in range(1, 6)
        ]))
        resp = client.post(
            JOURNAL_ENTRIES_URL, json={"mood": "calm"}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["streak"] == 6
        assert data["reward"] is False
        stardust, _, _ = _run(_fetch_user_stardust(user_id))
        assert stardust == 0

    def test_other_users_records_do_not_extend_streak(self, client: TestClient):
        """隔离性：他人连续 6 天不影响本用户 streak。"""
        user_id, token = _run(_make_user())
        other_id, _ = _run(_make_user())
        today = date.today()
        _run(_seed_entries(other_id, [
            (today - timedelta(days=i), "happy", "x", 1) for i in range(1, 7)
        ]))
        resp = client.post(
            JOURNAL_ENTRIES_URL, json={"mood": "happy"}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["streak"] == 1
        assert data["reward"] is False
