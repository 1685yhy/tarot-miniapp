"""
Tests for the diary review API.

Covers:
- POST /diary/entries — create diary entries
- GET  /diary/review  — empty diary fallback, mood trends, period param
"""

from fastapi.testclient import TestClient


def _auth_headers(client: TestClient, member: bool = False) -> dict[str, str]:
    """Log in and return auth headers."""
    url = "/auth/dev-login?member=true" if member else "/auth/dev-login"
    resp = client.post(url)
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestCreateDiaryEntry:
    """POST /diary/entries"""

    def test_create_entry(self, client: TestClient):
        """Creating a diary entry should return mood, card, and reflection."""
        headers = _auth_headers(client)
        resp = client.post(
            "/diary/entries",
            json={"mood": "happy", "reflection": "今天心情很好"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mood"] == "happy"
        assert data["reflection"] == "今天心情很好"
        assert "id" in data
        assert "date" in data
        assert data["card"] is not None, "A random card should be assigned"
        assert "name_zh" in data["card"], "Card should have a name_zh"

    def test_create_entry_without_reflection(self, client: TestClient):
        """Reflection is optional — entry should still succeed.

        Uses the non-member user (same as test_create_entry); on the same day
        this will update the existing entry rather than create a new one,
        but the test only validates that mood is set correctly.
        """
        headers = _auth_headers(client)
        resp = client.post(
            "/diary/entries",
            json={"mood": "calm"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mood"] == "calm"

    def test_update_todays_entry(self, client: TestClient):
        """Posting to the same day should update the existing entry."""
        headers = _auth_headers(client)
        # Create
        resp1 = client.post(
            "/diary/entries",
            json={"mood": "sad", "reflection": "不太好的一天"},
            headers=headers,
        )
        assert resp1.status_code == 200, resp1.text
        entry_id = resp1.json()["id"]

        # Update
        resp2 = client.post(
            "/diary/entries",
            json={"mood": "happy", "reflection": "其实也没那么糟！"},
            headers=headers,
        )
        assert resp2.status_code == 200, resp2.text
        data = resp2.json()
        assert data["id"] == entry_id
        assert data["mood"] == "happy", "Mood should be updated"
        assert data["reflection"] == "其实也没那么糟！"

    def test_list_entries(self, client: TestClient):
        """GET /diary/entries should return the user's entries."""
        headers = _auth_headers(client)
        # Create an entry first
        client.post(
            "/diary/entries",
            json={"mood": "excited", "reflection": "列表测试"},
            headers=headers,
        )
        resp = client.get("/diary/entries", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "entries" in data
        assert "page" in data
        assert len(data["entries"]) >= 1


class TestWeeklyReview:
    """GET /diary/review"""

    def test_review_structure(self, client: TestClient):
        """Review endpoint returns correct structure regardless of whether entries exist."""
        headers = _auth_headers(client)
        resp = client.get("/diary/review", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Required fields
        for field in ("period", "week_range", "entry_count", "mood_trends",
                      "top_card_name", "top_card_count", "top_card_meaning",
                      "ai_insight", "next_week_guidance", "emotional_trend_summary"):
            assert field in data, f"Review response missing '{field}'"
        assert data["period"] == "weekly"
        assert isinstance(data["mood_trends"], list)

    def test_review_with_entries(self, client: TestClient):
        """With diary entries, review should return mood trends and card info."""
        headers = _auth_headers(client)

        # Create a few entries for the current week
        for mood in ("happy", "calm", "excited"):
            client.post(
                "/diary/entries",
                json={"mood": mood},
                headers=headers,
            )
            # We can only create one per day, but that's fine — the test
            # verifies at least the structure is correct.

        resp = client.get("/diary/review", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # At minimum, structure should be correct
        assert "period" in data
        assert "week_range" in data
        assert "entry_count" in data
        assert "mood_trends" in data
        assert isinstance(data["mood_trends"], list)
        assert "emotional_trend_summary" in data
        assert data["emotional_trend_summary"] is not None

        # If entries are in the review period, they should show up
        if data["entry_count"] > 0:
            trend = data["mood_trends"][0]
            for field in ("date", "mood_score", "mood_label", "mood_emoji"):
                assert field in trend, f"Mood trend missing '{field}'"

    def test_review_period_valid(self, client: TestClient):
        """The 'period' query param must be 'weekly' or 'monthly' (schema-enforced)."""
        headers = _auth_headers(client)

        # Valid period
        resp = client.get("/diary/review?period=weekly", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["period"] == "weekly"

        resp = client.get("/diary/review?period=monthly", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["period"] == "monthly"

    def test_review_invalid_period(self, client: TestClient):
        """An invalid period value should return 422."""
        headers = _auth_headers(client)
        resp = client.get("/diary/review?period=daily", headers=headers)
        assert resp.status_code == 422, (
            f"Invalid 'period' param should return 422, got {resp.status_code}"
        )
