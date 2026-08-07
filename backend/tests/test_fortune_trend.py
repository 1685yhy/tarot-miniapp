"""
Tests for the fortune-trend endpoint (留存功能第一批 · 功能 2：牌运曲线).

GET /readings/fortune-trend?days=30 — aggregates the current user's readings:
total count, top-5 frequent cards, arcana/suit distribution, rule-based mood,
and a per-day trend series.

Covers:
- 401 without auth
- empty state shape (fresh user)
- aggregation over inserted readings + drawn cards
- arcana / suit distribution counts
- rule-based mood (major>minor → 转折之年; wands → 行动力强)
- trend series is zero-padded to `days`
"""

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.config import settings
from app.db.database import async_session
from app.models.reading import DrawnCard, Reading


def _auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/auth/dev-login?member=true",
        headers={"X-Dev-Key": settings.DEV_LOGIN_KEY},
    )
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _login_user_id(client: TestClient) -> str:
    resp = client.post(
        "/auth/dev-login?member=true",
        headers={"X-Dev-Key": settings.DEV_LOGIN_KEY},
    )
    return resp.json()["user"]["id"]


async def _clear_readings(user_id: str) -> None:
    """Delete the user's readings (tests share one dev user — avoid pollution)."""
    async with async_session() as session:
        sub = select(Reading.id).where(Reading.user_id == user_id)
        await session.execute(delete(DrawnCard).where(DrawnCard.reading_id.in_(sub)))
        await session.execute(delete(Reading).where(Reading.user_id == user_id))
        await session.commit()


async def _insert_reading(user_id: str, card_ids: list[int], days_ago: int) -> None:
    """Insert a reading (with drawn cards) directly, N days ago from now."""
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    async with async_session() as session:
        reading = Reading(
            user_id=user_id,
            spread_type="three_card",
            question="测试问题",
            created_at=created,
        )
        session.add(reading)
        await session.flush()
        for i, cid in enumerate(card_ids):
            session.add(
                DrawnCard(
                    reading_id=reading.id,
                    card_id=cid,
                    position=i,
                    position_name=f"位置{i + 1}",
                    is_reversed=False,
                )
            )
        await session.commit()


def test_fortune_trend_requires_auth(client: TestClient):
    """Without a token the endpoint must return 401."""
    resp = client.get("/readings/fortune-trend?days=30")
    assert resp.status_code == 401


def test_fortune_trend_empty_state(client: TestClient):
    """A fresh user gets a zero-filled, valid-shaped response."""
    headers = _auth_headers(client)
    resp = client.get("/readings/fortune-trend?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["days"] == 30
    assert data["total_readings"] == 0
    assert data["cards"] == []
    assert data["arcana_dist"] == {"major": 0, "minor": 0}
    assert data["suit_dist"] == {"wands": 0, "cups": 0, "swords": 0, "pentacles": 0}
    assert data["mood"] == "星光初启，牌运之旅待你开启"
    assert len(data["trend"]) == 30
    assert all(t["count"] == 0 for t in data["trend"])
    # trend dates are consecutive, newest last
    dates = [t["date"] for t in data["trend"]]
    assert dates == sorted(dates)


def test_fortune_trend_aggregation(client: TestClient):
    """
    Insert readings with controlled cards:
      - today:     card 1 (major), card 23 (minor/wands)
      - yesterday: card 23 (wands), card 24 (wands)

    Expect:
      - total_readings = 2
      - top cards: 卡牌23 ×2, 卡牌1 ×1, 卡牌24 ×1
      - arcana_dist = {major: 1, minor: 3}
      - suit_dist = {wands: 3, cups: 0, swords: 0, pentacles: 0}
      - mood: minor dominant + wands → 行动力强
      - trend: today 1, yesterday 1, rest 0
    """
    user_id = _login_user_id(client)
    asyncio.run(_clear_readings(user_id))
    asyncio.run(_insert_reading(user_id, [1, 23], days_ago=0))
    asyncio.run(_insert_reading(user_id, [23, 24], days_ago=1))

    headers = _auth_headers(client)
    resp = client.get("/readings/fortune-trend?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total_readings"] == 2

    by_name = {c["name"]: c for c in data["cards"]}
    assert by_name["卡牌23"]["count"] == 2
    assert by_name["卡牌23"]["name_en"] == "Card 23"
    assert by_name["卡牌1"]["count"] == 1
    assert by_name["卡牌24"]["count"] == 1
    assert len(data["cards"]) <= 5

    assert data["arcana_dist"] == {"major": 1, "minor": 3}
    assert data["suit_dist"] == {"wands": 3, "cups": 0, "swords": 0, "pentacles": 0}
    assert "行动力强" in data["mood"]

    counts = [t["count"] for t in data["trend"]]
    assert counts[-1] == 1  # today
    assert counts[-2] == 1  # yesterday
    assert all(c == 0 for c in counts[:-2])


def test_fortune_trend_major_mood(client: TestClient):
    """major 大阿卡那多于 minor 时 → 转折之年."""
    user_id = _login_user_id(client)
    asyncio.run(_clear_readings(user_id))
    asyncio.run(_insert_reading(user_id, [1, 2, 3, 4, 5], days_ago=0))  # 5× major

    headers = _auth_headers(client)
    resp = client.get("/readings/fortune-trend?days=7", headers=headers)
    data = resp.json()
    assert data["arcana_dist"] == {"major": 5, "minor": 0}
    assert "转折之年" in data["mood"]
    assert len(data["trend"]) == 7  # days param honored


def test_fortune_trend_respects_days_window(client: TestClient):
    """Readings outside the window are excluded."""
    user_id = _login_user_id(client)
    asyncio.run(_clear_readings(user_id))
    # 40 days ago — outside a 30-day window
    asyncio.run(_insert_reading(user_id, [1], days_ago=40))

    headers = _auth_headers(client)
    resp = client.get("/readings/fortune-trend?days=30", headers=headers)
    data = resp.json()
    assert data["total_readings"] == 0
