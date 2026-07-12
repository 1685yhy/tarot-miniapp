"""
Tests for the auth API endpoint.

- POST /auth/dev-login            — create / retrieve dev user
- POST /auth/dev-login?member=true — create a member user
"""

from fastapi.testclient import TestClient


def test_dev_login_returns_token_and_user(client: TestClient):
    """POST /auth/dev-login should return a token and user info."""
    response = client.post("/auth/dev-login")
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert isinstance(data["token"], str)
    assert len(data["token"]) > 0

    user = data["user"]
    assert user["nickname"] == "测试用户"
    assert user["is_member"] is False
    assert "id" in user
    assert "free_readings_today" in user


def test_dev_login_member(client: TestClient):
    """POST /auth/dev-login?member=true should return a member user."""
    response = client.post("/auth/dev-login?member=true")
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["is_member"] is True


def test_dev_login_idempotent(client: TestClient):
    """Multiple calls to dev-login should succeed (upsert)."""
    r1 = client.post("/auth/dev-login")
    r2 = client.post("/auth/dev-login")
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both should return the same user (same openid)
    assert r1.json()["user"]["id"] == r2.json()["user"]["id"]
