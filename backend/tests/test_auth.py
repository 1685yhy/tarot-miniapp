"""
Tests for the auth API endpoint.

- POST /auth/dev-login            — create / retrieve dev user (X-Dev-Key required)
- POST /auth/dev-login?member=true — create a member user
- DELETE /auth/me                 — account deletion (anonymization)
"""

from fastapi.testclient import TestClient

from app.config import settings


def _dev_key_headers() -> dict[str, str]:
    return {"X-Dev-Key": settings.DEV_LOGIN_KEY}


def test_dev_login_returns_token_and_user(client: TestClient):
    """POST /auth/dev-login should return a token and user info."""
    response = client.post("/auth/dev-login", headers=_dev_key_headers())
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


def test_dev_login_requires_dev_key(client: TestClient):
    """Without the X-Dev-Key header dev-login must be rejected (401)."""
    response = client.post("/auth/dev-login")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid dev key"


def test_dev_login_rejects_wrong_dev_key(client: TestClient):
    """A mismatched X-Dev-Key must be rejected (401)."""
    response = client.post(
        "/auth/dev-login",
        headers={"X-Dev-Key": "wrong-key-123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid dev key"


def test_dev_login_member(client: TestClient):
    """POST /auth/dev-login?member=true should return a member user."""
    response = client.post("/auth/dev-login?member=true", headers=_dev_key_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["is_member"] is True


def test_dev_login_idempotent(client: TestClient):
    """Multiple calls to dev-login should succeed (upsert)."""
    r1 = client.post("/auth/dev-login", headers=_dev_key_headers())
    r2 = client.post("/auth/dev-login", headers=_dev_key_headers())
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both should return the same user (same openid)
    assert r1.json()["user"]["id"] == r2.json()["user"]["id"]


def test_delete_me_anonymizes_and_invalidates_token(client: TestClient):
    """DELETE /auth/me must anonymize the user and invalidate old tokens."""
    login = client.post("/auth/dev-login", headers=_dev_key_headers())
    assert login.status_code == 200
    token = login.json()["token"]
    user_id = login.json()["user"]["id"]
    auth = {"Authorization": f"Bearer {token}"}

    # Sanity: token works before deletion
    r = client.get("/share/invite-code", headers=auth)
    assert r.status_code == 200

    # Delete the account
    resp = client.delete("/auth/me", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Old token is now invalid (token_version bumped)
    r = client.get("/share/invite-code", headers=auth)
    assert r.status_code == 401

    # A brand-new dev-login produces a DIFFERENT user (old one was anonymized,
    # not deleted — the deleted openid is masked and never reused)
    login2 = client.post("/auth/dev-login", headers=_dev_key_headers())
    assert login2.status_code == 200
    assert login2.json()["user"]["id"] != user_id
