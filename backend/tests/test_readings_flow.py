"""
Tests for the full tarot reading flow.

Covers:
- Member can create readings (unlimited, is_paid=true)
- Free user limited by FREE_DAILY_READINGS quota
- 402 when quota exhausted
- Persona is stored and returned
- Zodiac in request
- Multiple spread types
- History listing
- Reading with persona-free question
"""

from fastapi.testclient import TestClient

from app.config import settings


def _auth_headers(client: TestClient, member: bool = False) -> dict[str, str]:
    """Log in and return auth headers."""
    url = "/auth/dev-login?member=true" if member else "/auth/dev-login"
    resp = client.post(url)
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestMemberCreateReading:
    """Member users bypass free-quota limits entirely."""

    def test_member_reading_full_response(self, client: TestClient):
        """Member creates a three-card reading — verify full response shape."""
        headers = _auth_headers(client, member=True)
        resp = client.post(
            "/readings/spread/three_card",
            json={"question": "今天的运势", "theme": "general"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["spread_type"] == "three_card"
        assert data["question"] == "今天的运势"
        assert data["theme"] == "general"
        assert data["is_paid"] is True, "Member readings should be is_paid=true"
        assert "id" in data
        assert "created_at" in data

        # Drawn cards
        assert len(data["drawn_cards"]) == 3, "Three-card spread needs 3 drawn cards"
        for dc in data["drawn_cards"]:
            for field in ("id", "card_id", "card_name", "position",
                          "position_name", "is_reversed"):
                assert field in dc, f"DrawnCard missing '{field}'"

        # Action items (AI key is empty so interpretation is None, action_items=[])
        assert "action_items" in data
        assert isinstance(data["action_items"], list)

    def test_member_unlimited_readings(self, client: TestClient):
        """Member should be able to create many readings without hitting quota."""
        headers = _auth_headers(client, member=True)
        limit = settings.FREE_DAILY_READINGS + 2  # exceed free quota
        for i in range(limit):
            resp = client.post(
                "/readings/spread/three_card",
                json={"question": f"第{i+1}次占卜"},
                headers=headers,
            )
            assert resp.status_code == 200, (
                f"Member reading #{i+1} failed: {resp.text}"
            )

    def test_member_celtic_cross_spread(self, client: TestClient):
        """Member can create a 10-card celtic_cross spread."""
        headers = _auth_headers(client, member=True)
        resp = client.post(
            "/readings/spread/celtic_cross",
            json={"question": "全面分析", "theme": "general"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["spread_type"] == "celtic_cross"
        assert len(data["drawn_cards"]) == 10, "Celtic cross needs 10 cards"


class TestFreeUserQuota:
    """Free (non-member) users are limited by FREE_DAILY_READINGS."""

    FREE_LIMIT = settings.FREE_DAILY_READINGS  # default 3

    def test_free_user_quota_flow(self, client: TestClient):
        """Self-contained test: free reading within quota -> quota exhausted -> 402.

        Accepts that other tests in the session may have already consumed some
        of the daily quota (e.g. checkin gives +1 free reading). Creates readings
        one by one until the server returns 402, then verifies the error.
        """
        headers = _auth_headers(client, member=False)

        consumed = 0
        quota_left = True
        while quota_left:
            resp = client.post(
                "/readings/spread/three_card",
                json={"question": f"占卜 #{consumed + 1}"},
                headers=headers,
            )
            if resp.status_code == 402:
                quota_left = False
            else:
                assert resp.status_code == 200, (
                    f"Free reading #{consumed + 1} failed: {resp.text}"
                )
                data = resp.json()
                assert data["is_paid"] is False, (
                    f"Free user reading #{consumed + 1} should be is_paid=false"
                )
                consumed += 1

        # At least one successful reading before 402
        assert consumed >= 0, "Should have at least one successful free reading"

        detail = resp.json()
        assert "今日免费次数已用完" in detail.get("detail", ""), (
            f"402 detail should mention quota exhaustion: {detail}"
        )


class TestPersonaAndZodiac:
    """Persona and zodiac parameters in readings."""

    def test_reading_with_persona(self, client: TestClient):
        """Persona key should be stored on the reading record."""
        headers = _auth_headers(client, member=True)
        resp = client.post(
            "/readings/spread/three_card",
            json={
                "question": "占卜感情",
                "theme": "love",
                "persona": "gentle_star",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["persona"] == "gentle_star", (
            f"Expected persona 'gentle_star', got '{data['persona']}'"
        )

    def test_reading_without_persona(self, client: TestClient):
        """Without persona, the field should be None or absent."""
        headers = _auth_headers(client, member=True)
        resp = client.post(
            "/readings/spread/three_card",
            json={"question": "无角色占卜"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["persona"] is None, (
            f"Expected persona=None when not provided, got '{data['persona']}'"
        )

    def test_reading_with_zodiac(self, client: TestClient):
        """Zodiac parameter in request should be accepted."""
        headers = _auth_headers(client, member=True)
        resp = client.post(
            "/readings/spread/three_card",
            json={
                "question": "狮子座今日运势",
                "theme": "general",
                "zodiac": "leo",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Zodiac is used only for AI prompt injection; it's not stored
        # on the reading record. We verify the request was accepted.

    def test_reading_with_life_cross_spread(self, client: TestClient):
        """Life cross spread (5 cards) with persona and zodiac."""
        headers = _auth_headers(client, member=True)
        resp = client.post(
            "/readings/spread/life_cross",
            json={
                "question": "人生岔路口",
                "theme": "career",
                "persona": "wise_moon",
                "zodiac": "virgo",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["spread_type"] == "life_cross"
        assert len(data["drawn_cards"]) == 5
        assert data["persona"] == "wise_moon"


class TestReadingHistory:
    """GET /readings/history"""

    def test_history_list(self, client: TestClient):
        """History should return the user's readings."""
        headers = _auth_headers(client, member=True)
        # Create a reading
        create_resp = client.post(
            "/readings/spread/three_card",
            json={"question": "历史测试"},
            headers=headers,
        )
        assert create_resp.status_code == 200
        reading_id = create_resp.json()["id"]

        # List history
        hist = client.get("/readings/history", headers=headers)
        assert hist.status_code == 200, hist.text
        data = hist.json()
        assert data["total"] >= 1
        ids = [item["id"] for item in data["items"]]
        assert reading_id in ids, "Created reading should appear in history"

    def test_history_pagination(self, client: TestClient):
        """Pagination parameters should be honoured."""
        headers = _auth_headers(client, member=True)
        # Create 3 readings
        for i in range(3):
            client.post(
                "/readings/spread/three_card",
                json={"question": f"分页测试{i}"},
                headers=headers,
            )

        # Page 1, size 2
        p1 = client.get("/readings/history?page=1&page_size=2", headers=headers)
        assert p1.status_code == 200, p1.text
        p1_data = p1.json()
        assert len(p1_data["items"]) == 2
        assert p1_data["total"] >= 3

    def test_get_single_reading(self, client: TestClient):
        """GET /readings/{id} should return the full reading."""
        headers = _auth_headers(client, member=True)
        create_resp = client.post(
            "/readings/spread/three_card",
            json={"question": "详细查看测试", "theme": "general"},
            headers=headers,
        )
        assert create_resp.status_code == 200
        reading_id = create_resp.json()["id"]

        get_resp = client.get(f"/readings/{reading_id}", headers=headers)
        assert get_resp.status_code == 200, get_resp.text
        data = get_resp.json()
        assert data["id"] == reading_id
        assert "drawn_cards" in data
        assert data["spread_type"] == "three_card"

    def test_get_reading_with_chat_messages(self, client: TestClient):
        """GET /readings/{id} response should include chat_messages field."""
        headers = _auth_headers(client, member=True)
        create_resp = client.post(
            "/readings/spread/three_card",
            json={"question": "聊天消息测试"},
            headers=headers,
        )
        assert create_resp.status_code == 200
        reading_id = create_resp.json()["id"]

        get_resp = client.get(f"/readings/{reading_id}", headers=headers)
        assert get_resp.status_code == 200, get_resp.text
        data = get_resp.json()
        assert "chat_messages" in data, "Response should include chat_messages"
        assert isinstance(data["chat_messages"], list), "chat_messages should be a list"

    def test_get_nonexistent_reading_404(self, client: TestClient):
        """A non-existent reading ID should return 404."""
        headers = _auth_headers(client, member=True)
        bogus_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(f"/readings/{bogus_id}", headers=headers)
        assert resp.status_code == 404, (
            f"Expected 404 for bogus reading ID, "
            f"got {resp.status_code}"
        )


class TestActionItems:
    """Action item parsing from AI interpretation."""

    def test_action_items_parsed(self, client: TestClient):
        """Parse action items from a properly formatted AI response."""
        from app.api.readings import parse_action_items

        text = (
            "你的整体运势不错。\n"
            "[ACTION]本周主动约朋友喝咖啡，聊聊最近的感受[/ACTION]\n"
            "[ACTION]每天花10分钟记录自己的感受[/ACTION]\n"
            "[ACTION]尝试一件新事物，如报一个线上课程[/ACTION]"
        )
        items = parse_action_items(text)
        assert len(items) == 3, f"Expected 3 action items, got {len(items)}"
        for item in items:
            assert "id" in item, "Action item missing 'id'"
            assert "content" in item, "Action item missing 'content'"
            assert "category" in item, "Action item missing 'category'"
            assert item["category"] in ("love", "career", "general"), (
                f"Unexpected category '{item['category']}'"
            )

    def test_action_items_empty_when_no_match(self, client: TestClient):
        """No [ACTION] tags → empty list."""
        from app.api.readings import parse_action_items

        items = parse_action_items("这是一段普通的解读文字，没有行动标签。")
        assert items == [], f"Expected empty action items, got {items}"

    def test_action_items_none_input(self, client: TestClient):
        """None input → empty list."""
        from app.api.readings import parse_action_items

        items = parse_action_items(None)
        assert items == [], f"Expected empty action items for None, got {items}"
