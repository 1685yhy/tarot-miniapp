"""
Tests for the reading API endpoints.

POST /readings/spread/three_card  — creates a new reading (requires auth + DB)
GET  /readings/history            — lists the user's reading history (requires auth)

The POST endpoint calls the AI interpretation engine internally.
Since DEEPSEEK_API_KEY is set to "" in tests, the AI function returns
None immediately and the reading is saved without an interpretation.
This is fine — the endpoint is still exercised end-to-end.
"""

from fastapi.testclient import TestClient


def _auth_headers(client: TestClient) -> dict[str, str]:
    """Helper: log in as a member (unlimited readings) and return auth headers."""
    resp = client.post("/auth/dev-login?member=true")
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_reading_requires_auth(client: TestClient):
    """
    POST /readings/spread/three_card without token should return 422.

    FastAPI validates ``Header(...)`` at the parameter-binding layer before
    the handler runs, so a missing required header yields 422, not 401.
    """
    response = client.post(
        "/readings/spread/three_card",
        json={"question": "今天的运势如何？"},
    )
    assert response.status_code == 422


def test_create_reading_and_get_history(client: TestClient):
    """
    Full flow: login -> create reading -> list history.

    Note: The interpretation field will be ``None`` because the AI engine
    returns None when DEEPSEEK_API_KEY is empty (controlled via env var).
    This is intentional — the test validates the HTTP/response plumbing
    without depending on a real AI provider.
    """
    headers = _auth_headers(client)

    # ── Create a three-card spread reading ──
    create_resp = client.post(
        "/readings/spread/three_card",
        json={"question": "测试问题", "theme": "general"},
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    reading = create_resp.json()

    assert reading["spread_type"] == "three_card"
    assert reading["question"] == "测试问题"
    assert reading["theme"] == "general"
    assert reading["is_paid"] is True  # member user, so paid
    assert "id" in reading
    assert "created_at" in reading
    assert len(reading["drawn_cards"]) == 3  # three-card spread

    # First card info
    first = reading["drawn_cards"][0]
    assert "card_id" in first
    assert "card_name" in first
    assert "position" in first
    assert "position_name" in first
    assert "is_reversed" in first

    # ── List history ──
    hist_resp = client.get("/readings/history", headers=headers)
    assert hist_resp.status_code == 200
    hist = hist_resp.json()
    assert hist["total"] >= 1
    assert any(item["id"] == reading["id"] for item in hist["items"])

    # History item shape
    item = hist["items"][0]
    for key in ("id", "spread_type", "question", "interpretation",
                "is_paid", "created_at"):
        assert key in item


def test_history_pagination(client: TestClient):
    """GET /readings/history with page & page_size should honour them."""
    headers = _auth_headers(client)

    # Create two readings so there's at least something to paginate
    for _ in range(2):
        client.post(
            "/readings/spread/three_card",
            json={"question": "分页测试"},
            headers=headers,
        )

    # Request page 1 with page_size=1
    resp = client.get("/readings/history?page=1&page_size=1", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["total"] >= 2
