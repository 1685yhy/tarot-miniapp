"""
Tests for the starlight journal calendar API (T1-1 星光手账月历聚合).

Covers:
- GET /journal/calendar — 401 when not logged in
- Empty month → days=[] and zero stats
- star_color determinism (same date twice + equals build_today_guidance result)
- 6 moods → correct 5-level brightness (excited=5 ... anxious|sad=1)
- has_reflection flips with reflection presence/absence
- month stats counting (bright_count >= 4, dim_count <= 2, streak)
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


async def _make_user(zodiac: str | None = None) -> tuple[str, str]:
    """Create an isolated user (with optional zodiac) and return (user_id, token)."""
    async with async_session() as session:
        user = User(
            openid=f"journal_test_{uuid.uuid4().hex[:10]}",
            nickname="手账测试",
            zodiac=zodiac,
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
        _run(_seed_entries(user_id, [
            (date(2026, 7, 1), "excited", "a", 1),   # brightness 5 → bright
            (date(2026, 7, 3), "happy", "b", 1),     # brightness 4 → bright
            (date(2026, 7, 5), "calm", "c", 1),      # brightness 3 → neither
            (date(2026, 7, 7), "anxious", "d", 1),   # brightness 1 → dim
            (date(2026, 7, 9), "sad", "e", 1),       # brightness 1 → dim
        ]))
        resp = client.get(f"{CALENDAR_URL}?year=2026&month=7", headers=_headers(token))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["stats"]["days_recorded"] == 5
        assert data["stats"]["bright_count"] == 2
        assert data["stats"]["dim_count"] == 2
        assert data["stats"]["current_streak"] == 0  # July 2026 fully in the past
        # days sorted ascending by date
        assert [d["date"] for d in data["days"]] == [
            "2026-07-01", "2026-07-03", "2026-07-05", "2026-07-07", "2026-07-09",
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
