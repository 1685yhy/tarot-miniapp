"""
Security-hardening tests (P0 fixes).

- /share/track requires auth and forces sharer_id to the authenticated user
- /admin requires a JWT (no header → 403; invalid → 401; non-admin → 403)
- /orders/callback rejects requests missing the mandatory V3 signature headers
- /orders/{order_no}/status is ownership-checked
- Community posts require auth and are content-screened
- Non-member AI-extras quotas (reinterpret 3/day, diary reflection-prompt 5/day)
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import async_session
from app.models.order import Order
from app.models.user import User
from app.utils.auth import create_token


def _dev_login(client: TestClient, member: bool = False) -> dict:
    """Dev-login and return {token, user}.

    The member flag is ALWAYS passed explicitly — the dev user is shared
    across the whole test session, so relying on "keep existing state"
    would make these tests order-dependent.
    """
    url = f"/auth/dev-login?member={'true' if member else 'false'}"
    resp = client.post(url, headers={"X-Dev-Key": settings.DEV_LOGIN_KEY})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user"]["is_member"] is member
    return {"token": data["token"], "user": data["user"]}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_user(openid: str, nickname: str, member: bool = False) -> dict:
    """Create a user directly in the test DB; returns {id, token}.

    A FRESH user per test is essential for quota tests: the dev-login user is
    shared across the whole session and other test files may already have
    consumed its daily AI quota / flipped its member state.
    """
    from datetime import datetime, timedelta, timezone

    async def _run():
        async with async_session() as session:
            user = User(
                openid=openid,
                nickname=nickname,
                is_member=member,
                member_expires_at=(
                    datetime.now(timezone.utc) + timedelta(days=30)
                    if member else None
                ),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return {"id": user.id, "nickname": user.nickname}
    user = asyncio.run(_run())
    user["token"] = create_token(user["id"])
    return user


# ---------------------------------------------------------------------------
# /share/track (H5)
# ---------------------------------------------------------------------------


def test_share_track_requires_auth(client: TestClient):
    """POST /share/track without a token must be rejected (401)."""
    resp = client.post("/share/track", json={"channel": "wechat_friend"})
    assert resp.status_code == 401


def test_share_track_forces_sharer_id(client: TestClient):
    """The sharer is always the authenticated user; body.sharer_id is ignored."""
    attacker = _create_user(f"atk_{uuid.uuid4().hex[:8]}", "攻击者")
    victim = _create_user(f"vic_{uuid.uuid4().hex[:8]}", "受害者")

    resp = client.post(
        "/share/track",
        json={"sharer_id": victim["id"], "channel": "wechat_friend"},
        headers=_auth(attacker["token"]),
    )
    assert resp.status_code == 200

    # The attacker's share_count incremented; the victim's did not.
    async def _counts():
        async with async_session() as session:
            a = (await session.execute(
                User.__table__.select().where(User.id == attacker["id"])
            )).first()
            v = (await session.execute(
                User.__table__.select().where(User.id == victim["id"])
            )).first()
            return a.share_count, v.share_count
    attacker_count, victim_count = asyncio.run(_counts())
    assert attacker_count == 1
    assert victim_count == 0


# ---------------------------------------------------------------------------
# Admin (H3)
# ---------------------------------------------------------------------------


def test_admin_requires_jwt(client: TestClient):
    """No Authorization header → 403."""
    resp = client.get("/admin")
    assert resp.status_code == 403


def test_admin_rejects_invalid_jwt(client: TestClient):
    """A garbage token → 401."""
    resp = client.get("/admin", headers=_auth("not-a-real-token"))
    assert resp.status_code == 401


def test_admin_rejects_non_admin_jwt(client: TestClient):
    """A valid token for a non-super-admin user → 403."""
    dev = _dev_login(client)
    resp = client.get("/admin", headers=_auth(dev["token"]))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Orders callback (H2)
# ---------------------------------------------------------------------------


def test_orders_callback_requires_signature_headers(client: TestClient):
    """Callback without the mandatory V3 headers must be rejected (401)."""
    resp = client.post("/orders/callback", json={"out_trade_no": "TAROT123"})
    assert resp.status_code == 401


def test_orders_status_ownership(client: TestClient):
    """GET /orders/{order_no}/status is only visible to the order owner."""
    owner = _dev_login(client)
    other = _create_user(f"oth_{uuid.uuid4().hex[:8]}", "另一位用户")  # distinct user
    order_no = f"TAROT{uuid.uuid4().hex[:10].upper()}"

    async def _seed_order():
        async with async_session() as session:
            order = Order(
                user_id=owner["user"]["id"],
                order_no=order_no,
                product_type="single_reading",
                amount=9.90,
                status="pending",
            )
            session.add(order)
            await session.commit()
    asyncio.run(_seed_order())

    # Owner sees the order
    resp = client.get(f"/orders/{order_no}/status", headers=_auth(owner["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_no"] == order_no
    assert data["status"] == "pending"
    assert data["paid"] is False
    assert data["amount"] == 9.90

    # Another user cannot see it
    resp = client.get(f"/orders/{order_no}/status", headers=_auth(other["token"]))
    assert resp.status_code == 403

    # Unknown order
    resp = client.get(
        f"/orders/{uuid.uuid4().hex[:12].upper()}/status",
        headers=_auth(owner["token"]),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Community content safety (M3)
# ---------------------------------------------------------------------------


def test_community_post_requires_auth(client: TestClient):
    """POST /community/posts without a token must be rejected (401)."""
    resp = client.post(
        "/community/posts",
        json={"topic_id": 1, "content": "你好呀"},
    )
    assert resp.status_code == 401


def test_community_post_blocks_sensitive_content(client: TestClient):
    """Obvious sensitive content must be rejected (400)."""
    dev = _dev_login(client)
    resp = client.post(
        "/community/posts",
        json={"topic_id": 1, "content": "快来加群赌博赢钱"},
        headers=_auth(dev["token"]),
    )
    assert resp.status_code == 400
    assert "违规" in resp.json()["detail"]


def test_community_post_ok_with_auth(client: TestClient):
    """A normal post with a valid token succeeds (201)."""
    dev = _dev_login(client)
    # Get today's topic (auto-created)
    topic = client.get("/community/today")
    assert topic.status_code == 200
    topic_id = topic.json()["topic"]["id"]
    resp = client.post(
        "/community/posts",
        json={"topic_id": topic_id, "content": "今天抽到了星星牌，很受触动"},
        headers=_auth(dev["token"]),
    )
    assert resp.status_code == 201
    assert resp.json()["content"] == "今天抽到了星星牌，很受触动"


# ---------------------------------------------------------------------------
# AI-extras quotas (M4)
# ---------------------------------------------------------------------------


def test_reinterpret_quota_non_member_3_per_day(client: TestClient):
    """Non-members: 3 reinterprets/day; the 4th must be rejected (402)."""
    user = _create_user(f"rei_{uuid.uuid4().hex[:8]}", "重解用户")  # fresh user
    auth = _auth(user["token"])

    # Seed a reading directly (avoids the shared dev user's consumed quota).
    reading_id = str(uuid.uuid4())
    async def _seed_reading():
        from app.models.reading import DrawnCard, Reading
        async with async_session() as session:
            reading = Reading(
                id=reading_id,
                user_id=user["id"],
                spread_type="three_card",
                question="我的财运如何",
                theme="finance",
            )
            session.add(reading)
            for position in (1, 2, 3):
                session.add(DrawnCard(
                    reading_id=reading_id,
                    card_id=position,
                    position=position,
                    position_name=f"位置{position}",
                    is_reversed=False,
                ))
            await session.commit()
    asyncio.run(_seed_reading())

    for _ in range(3):
        resp = client.post(f"/readings/{reading_id}/reinterpret", headers=auth)
        assert resp.status_code == 200, resp.text

    resp = client.post(f"/readings/{reading_id}/reinterpret", headers=auth)
    assert resp.status_code == 402


def test_reflection_prompt_quota_non_member_5_per_day(client: TestClient):
    """Non-members: 5 diary-AI calls/day (reflection-prompt); the 6th → 402.

    Uses a fresh user — the shared dev user's daily diary-AI budget may
    already be partly consumed by /diary/review calls in other test files.
    """
    user = _create_user(f"ref_{uuid.uuid4().hex[:8]}", "日记用户")
    auth = _auth(user["token"])

    for _ in range(5):
        resp = client.post(
            "/diary/reflection-prompt",
            json={"card_id": 1, "card_name": "星星"},
            headers=auth,
        )
        assert resp.status_code == 200, resp.text

    resp = client.post(
        "/diary/reflection-prompt",
        json={"card_id": 1, "card_name": "星星"},
        headers=auth,
    )
    assert resp.status_code == 402


def test_member_bypasses_ai_quotas(client: TestClient):
    """Members are unlimited: 6+ reflection prompts still succeed."""
    user = _create_user(f"mem_{uuid.uuid4().hex[:8]}", "会员用户", member=True)
    auth = _auth(user["token"])
    for _ in range(6):
        resp = client.post(
            "/diary/reflection-prompt",
            json={"card_id": 1, "card_name": "星星"},
            headers=auth,
        )
        assert resp.status_code == 200, resp.text
