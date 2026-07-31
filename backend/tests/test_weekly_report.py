"""
Tests for the AI weekly report API — GET /report/weekly.

Covers:
- Empty week fallback (has_data=False, no crash)
- Mood trend from diary entries (last 7 days)
- Most frequent card from readings (last 7 days)
- Top keywords from the most frequent card
- AI one-line summary fallback when AI is disabled
"""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import async_session
from app.models.card import TarotCard
from app.models.diary import DiaryEntry
from app.models.reading import DrawnCard, Reading
from app.models.user import User
from app.utils.auth import create_token

WEEKLY_URL = "/report/weekly"


async def _make_isolated_user() -> tuple[str, str]:
    """Create a dedicated user (isolated from shared dev users) + token."""
    async with async_session() as session:
        user = User(
            openid=f"weekly_report_test_{uuid.uuid4().hex[:10]}",
            nickname="周报测试",
        )
        session.add(user)
        await session.flush()
        user_id = str(user.id)
        token = create_token(user.id)
        await session.commit()
        return user_id, token


async def _seed_weekly_data(user_id: str) -> None:
    """Insert diary entries + readings for the last 7 days for one user."""
    async with async_session() as session:
        # ── Diary entries: 2 recorded days with moods ──
        today = date.today()
        entries = [
            ("happy", today - timedelta(days=1), "今天心情很好"),
            ("calm", today - timedelta(days=3), "平静的一天"),
        ]
        for mood_key, entry_date, reflection in entries:
            session.add(DiaryEntry(
                id=str(uuid.uuid4()),
                user_id=user_id,
                entry_date=entry_date,
                mood=mood_key,
                reflection=reflection,
            ))

        # ── Diary entry exactly 7 days ago — outside the 7-day window ──
        session.add(DiaryEntry(
            id=str(uuid.uuid4()),
            user_id=user_id,
            entry_date=today - timedelta(days=7),
            mood="sad",
            reflection="一周前的记录，不应计入周报",
        ))

        # ── Readings with drawn cards: 卡牌1 drawn 3x, 卡牌2 drawn 1x ──
        now = datetime.now(timezone.utc)
        for i, card_id in enumerate([1, 1, 1, 2]):
            reading = Reading(
                id=str(uuid.uuid4()),
                user_id=user_id,
                spread_type="daily",
                question=None,
                theme="general",
                created_at=now - timedelta(days=i),
            )
            session.add(reading)
            session.add(DrawnCard(
                reading_id=reading.id,
                card_id=card_id,
                position=0,
                position_name="主牌",
                is_reversed=False,
            ))

        # ── Give 卡牌1 valid JSON keywords for the keyword test ──
        card1 = (await session.execute(
            select(TarotCard).where(TarotCard.id == 1)
        )).scalar_one()
        card1.keywords_upright = '["勇气", "开始", "冒险"]'

        # ── One reading outside the 7-day window (must be ignored) ──
        old_reading = Reading(
            id=str(uuid.uuid4()),
            user_id=user_id,
            spread_type="daily",
            theme="general",
            created_at=now - timedelta(days=30),
        )
        session.add(old_reading)
        session.add(DrawnCard(
            reading_id=old_reading.id,
            card_id=5,
            position=0,
            position_name="主牌",
            is_reversed=False,
        ))

        await session.commit()


def _run(coro):
    """Run an async coroutine on a fresh loop (same pattern as conftest)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestWeeklyReport:
    """GET /report/weekly"""

    def test_empty_week_returns_fallback(self, client: TestClient):
        """Fresh user with no data — 200 with has_data=False and no crash."""
        user_id, token = _run(_make_isolated_user())
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get(WEEKLY_URL, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["has_data"] is False
        assert len(data["week_dates"]) == 7
        assert data["mood_trends"] == []
        assert data["most_frequent_card"] is None
        assert data["top_keywords"] == []
        assert data["ai_summary"], "Fallback summary should be present"
        assert user_id

    def test_weekly_report_shape_and_content(self, client: TestClient):
        """With 7-day data — mood trend, top card, keywords, summary."""
        user_id, token = _run(_make_isolated_user())
        _run(_seed_weekly_data(user_id))
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get(WEEKLY_URL, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Shape
        assert data["has_data"] is True
        assert data["total_readings"] == 4, "30-day-old reading must be excluded"
        assert data["diary_count"] == 2
        assert len(data["week_dates"]) == 7
        assert "week_range" in data and "~" in data["week_range"]

        # Mood trend — 2 recorded days (7-day-old entry must be excluded)
        assert len(data["mood_trends"]) == 2
        assert "😢" not in [t["mood_emoji"] for t in data["mood_trends"]], \
            "Entry exactly 7 days ago must be outside the window"
        for t in data["mood_trends"]:
            assert t["mood_emoji"], "Emoji must be mapped from mood key"
            assert t["mood_label"]
            assert t["mood_score"] > 0

        # Most frequent card — 卡牌1 drawn 3x
        card = data["most_frequent_card"]
        assert card is not None
        assert card["name"] == "卡牌1"
        assert card["count"] == 3
        assert card["meaning"]

        # Top keywords from valid JSON keywords_upright
        assert data["top_keywords"] == ["勇气", "开始", "冒险"]

        # AI summary — fallback line mentioning the top card
        assert data["ai_summary"]
        assert "卡牌1" in data["ai_summary"]
        assert "3" in data["ai_summary"]
