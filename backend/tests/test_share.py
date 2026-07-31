"""
Tests for the share / invite API.

- GET  /share/invite-code   — returns (and keeps stable) the user's invite code
- POST /share/invite        — rewards BOTH inviter and invitee +1 free deep reading
                             (not membership, not cash)
- POST /share/invite        — rejects: invalid code / self-invite / double accept
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.db.database import async_session
from app.models.user import User
from app.utils.auth import create_token


def _create_user(openid: str, nickname: str) -> dict:
    """Create a user directly in the test DB; returns {id, token}."""
    async def _run():
        async with async_session() as session:
            user = User(openid=openid, nickname=nickname)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return {"id": user.id, "nickname": user.nickname}
    user = asyncio.run(_run())
    user["token"] = create_token(user["id"])
    return user


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_invite_code_generated_and_stable(client: TestClient):
    """GET /share/invite-code returns a STAR-XXXX code, stable across calls."""
    user = _create_user(f"inv_uid_{uuid.uuid4().hex[:8]}", "邀请方")
    r1 = client.get("/share/invite-code", headers=_auth(user["token"]))
    assert r1.status_code == 200
    code = r1.json()["invite_code"]
    assert code.startswith("STAR-")

    r2 = client.get("/share/invite-code", headers=_auth(user["token"]))
    assert r2.status_code == 200
    assert r2.json()["invite_code"] == code  # stable — no new code per call


def test_invite_requires_auth(client: TestClient):
    """POST /share/invite with an invalid token should be rejected (401)."""
    r = client.post(
        "/share/invite",
        json={"invite_code": "STAR-TEST"},
        headers=_auth("not-a-real-token"),
    )
    assert r.status_code == 401


def test_invite_rewards_both_plus_one(client: TestClient):
    """Accepting a valid invite code gives BOTH users +1 free deep reading."""
    inviter = _create_user(f"inv_uid_{uuid.uuid4().hex[:8]}", "邀请方")
    invitee = _create_user(f"inv_uid_{uuid.uuid4().hex[:8]}", "被邀请方")

    # Inviter gets their code
    code = client.get("/share/invite-code", headers=_auth(inviter["token"])).json()["invite_code"]

    # Invitee accepts the code
    r = client.post("/share/invite", json={"invite_code": code}, headers=_auth(invitee["token"]))
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["inviter_reward"] == 1
    assert data["invitee_reward"] == 1
    assert data["inviter_name"] == "邀请方"

    # Both users should have exactly +1 free deep reading
    for uid in (inviter["id"], invitee["id"]):
        async def _fetch(_uid=uid):
            async with async_session() as session:
                u = await session.get(User, _uid)
                return u.free_deep_readings
        assert asyncio.run(_fetch()) == 1


def test_invite_invalid_code_rejected(client: TestClient):
    """POST /share/invite with an unknown code should 400."""
    user = _create_user(f"inv_uid_{uuid.uuid4().hex[:8]}", "新用户")
    r = client.post("/share/invite", json={"invite_code": "STAR-NOPE"}, headers=_auth(user["token"]))
    assert r.status_code == 400


def test_invite_self_invite_rejected(client: TestClient):
    """A user cannot accept their own invite code."""
    user = _create_user(f"inv_uid_{uuid.uuid4().hex[:8]}", "自己")
    code = client.get("/share/invite-code", headers=_auth(user["token"])).json()["invite_code"]
    r = client.post("/share/invite", json={"invite_code": code}, headers=_auth(user["token"]))
    assert r.status_code == 400


def test_invite_double_accept_rejected(client: TestClient):
    """A user can only accept an invite once — no double reward."""
    inviter_a = _create_user(f"inv_uid_{uuid.uuid4().hex[:8]}", "邀请方A")
    inviter_b = _create_user(f"inv_uid_{uuid.uuid4().hex[:8]}", "邀请方B")
    invitee = _create_user(f"inv_uid_{uuid.uuid4().hex[:8]}", "被邀请方")

    code_a = client.get("/share/invite-code", headers=_auth(inviter_a["token"])).json()["invite_code"]
    code_b = client.get("/share/invite-code", headers=_auth(inviter_b["token"])).json()["invite_code"]

    assert client.post("/share/invite", json={"invite_code": code_a}, headers=_auth(invitee["token"])).status_code == 200

    # Second accept (even with a different valid code) must be rejected
    r = client.post("/share/invite", json={"invite_code": code_b}, headers=_auth(invitee["token"]))
    assert r.status_code == 400

    # Invitee still has exactly +1 — no double reward
    async def _fetch():
        async with async_session() as session:
            u = await session.get(User, invitee["id"])
            return u.free_deep_readings
    assert asyncio.run(_fetch()) == 1
