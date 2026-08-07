"""
P0 regression tests (audit fixes).

Covers:
- P0-1: /report/annual — non-member blocked (402); annual_report_paid
        grants access (purchase callback grants the entitlement).
- P0-2: deep readings — free_deep_readings / paid_readings_balance are
        consumed on deep requests; without balance deep downgrades to
        standard.
- P1-6: premium spreads (celtic_cross / horseshoe / relationship /
        year_ahead) are 402 for non-members.
- P1-8: /cards/daily is deterministic per user+date.
- P0-4: /notify/subscribe returns 400 "推送服务未开通" while no real
        template ID is configured.

NOTE on shared dev user: dev-login is idempotent on one user for the whole
test session, so the member flag is ALWAYS passed explicitly and any test
that needs its own balances creates a fresh user (same pattern as
tests/test_security.py).
"""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db.database import async_session
from app.models.user import User
from app.utils.auth import create_token


def _dev_login(client: TestClient, member: bool = False) -> dict:
    url = f"/auth/dev-login?member={'true' if member else 'false'}"
    resp = client.post(url, headers={"X-Dev-Key": settings.DEV_LOGIN_KEY})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user"]["is_member"] is member
    return {"token": data["token"], "user": data["user"]}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_user(openid: str, nickname: str, member: bool = False) -> dict:
    """Create a fresh user directly in the test DB; returns {id, token}."""

    async def _run():
        async with async_session() as session:
            user = User(
                openid=openid,
                nickname=nickname,
                is_member=member,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    user = asyncio.run(_run())
    return {"id": user.id, "token": create_token(user.id, user.token_version)}


async def _patch_user(uid: str, **fields):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == uid))
        u = result.scalar_one()
        for key, value in fields.items():
            setattr(u, key, value)
        await session.commit()


# ---------------------------------------------------------------------------
# P0-1: Annual report entitlement
# ---------------------------------------------------------------------------


def test_annual_report_requires_member_or_purchase(client: TestClient):
    """Non-member without annual_report_paid gets 402."""
    login = _dev_login(client, member=False)
    resp = client.get("/report/annual", headers=_auth(login["token"]))
    assert resp.status_code == 402, resp.text


def test_annual_report_member_allowed(client: TestClient):
    """Members get the report (200; AI is disabled in tests)."""
    login = _dev_login(client, member=True)
    resp = client.get("/report/annual", headers=_auth(login["token"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["year"] > 0


def test_annual_report_purchase_grants_access(client: TestClient):
    """Setting annual_report_paid (what the order callback does) unblocks
    /report/annual for a non-member."""
    user = _create_user(f"annual_{uuid.uuid4().hex[:8]}", "年报单买用户")
    asyncio.run(_patch_user(user["id"], annual_report_paid=True))

    resp = client.get("/report/annual", headers=_auth(user["token"]))
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# P0-2: Deep reading consumption
# ---------------------------------------------------------------------------


def _get_balance(uid: str) -> tuple[int, int]:
    """Return (free_deep_readings, paid_readings_balance) for a user."""

    async def _run():
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == uid))
            u = result.scalar_one()
            return u.free_deep_readings, u.paid_readings_balance

    return asyncio.run(_run())


def _post_reading(client: TestClient, token: str, spread: str = "three_card",
                  depth: str = "standard", question: str = "测试问题"):
    return client.post(
        f"/readings/spread/{spread}",
        json={"question": question, "theme": "general", "depth": depth},
        headers=_auth(token),
    )


def test_deep_reading_consumes_free_deep_readings(client: TestClient):
    """Non-member with free_deep_readings=1 requesting depth=deep gets a deep
    reading and the balance drops to 0."""
    user = _create_user(f"deep_free_{uuid.uuid4().hex[:8]}", "免费深度用户")
    asyncio.run(_patch_user(user["id"], free_deep_readings=1))

    resp = _post_reading(client, user["token"], depth="deep", question="深度测试")
    assert resp.status_code == 200, resp.text
    assert resp.json()["depth"] == "deep"

    free, paid = _get_balance(user["id"])
    assert free == 0, "free_deep_readings must be consumed"
    assert paid == 0


def test_deep_reading_consumes_paid_balance(client: TestClient):
    """Non-member with paid_readings_balance=1 requesting depth=deep gets a
    deep reading and the balance drops to 0."""
    user = _create_user(f"deep_paid_{uuid.uuid4().hex[:8]}", "付费深度用户")
    asyncio.run(_patch_user(user["id"], paid_readings_balance=1))

    resp = _post_reading(client, user["token"], depth="deep", question="付费深度测试")
    assert resp.status_code == 200, resp.text
    assert resp.json()["depth"] == "deep"

    free, paid = _get_balance(user["id"])
    assert paid == 0, "paid_readings_balance must be consumed"


def test_deep_reading_prefers_free_balance(client: TestClient):
    """free_deep_readings is consumed before paid_readings_balance."""
    user = _create_user(f"deep_both_{uuid.uuid4().hex[:8]}", "双余额用户")
    asyncio.run(_patch_user(user["id"], free_deep_readings=2, paid_readings_balance=2))

    resp = _post_reading(client, user["token"], depth="deep")
    assert resp.status_code == 200, resp.text
    assert resp.json()["depth"] == "deep"

    free, paid = _get_balance(user["id"])
    assert (free, paid) == (1, 2), "must burn free balance first"


def test_deep_reading_downgrades_without_balance(client: TestClient):
    """Non-member with no deep/paid balance requesting depth=deep falls back
    to standard (and nothing is consumed)."""
    user = _create_user(f"deep_none_{uuid.uuid4().hex[:8]}", "无余额用户")

    resp = _post_reading(client, user["token"], depth="deep", question="无余额深度测试")
    assert resp.status_code == 200, resp.text
    assert resp.json()["depth"] == "standard"

    free, paid = _get_balance(user["id"])
    assert (free, paid) == (0, 0)


def test_deep_reading_member_unlimited(client: TestClient):
    """Members get deep readings without consuming balances."""
    user = _create_user(f"deep_member_{uuid.uuid4().hex[:8]}", "会员深度用户", member=True)
    asyncio.run(_patch_user(user["id"], free_deep_readings=2, paid_readings_balance=2))

    resp = _post_reading(client, user["token"], depth="deep")
    assert resp.status_code == 200, resp.text
    assert resp.json()["depth"] == "deep"

    free, paid = _get_balance(user["id"])
    assert (free, paid) == (2, 2), "member balances must stay untouched"


# ---------------------------------------------------------------------------
# P1-6: Premium spread server-side gate
# ---------------------------------------------------------------------------


def test_premium_spread_requires_member(client: TestClient):
    """celtic_cross for a non-member is rejected server-side (402)."""
    login = _dev_login(client, member=False)
    resp = _post_reading(client, login["token"], spread="celtic_cross")
    assert resp.status_code == 402, resp.text


def test_premium_spread_member_allowed(client: TestClient):
    """Members can use premium spreads."""
    login = _dev_login(client, member=True)
    resp = _post_reading(client, login["token"], spread="celtic_cross")
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# P1-8: Daily card determinism
# ---------------------------------------------------------------------------


def test_daily_card_deterministic_per_user_per_day(client: TestClient):
    """Same user + same date → same card."""
    login = _dev_login(client, member=False)
    headers = _auth(login["token"])

    r1 = client.get("/cards/daily", headers=headers)
    r2 = client.get("/cards/daily", headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["name_zh"] == r2.json()["name_zh"]


def test_daily_card_anonymous_still_works(client: TestClient):
    """Anonymous callers keep getting a card (random)."""
    resp = client.get("/cards/daily")
    assert resp.status_code == 200
    assert resp.json()["id"] >= 1


# ---------------------------------------------------------------------------
# P0-4: Push subscription gating
# ---------------------------------------------------------------------------


def test_push_subscribe_rejected_when_templates_unconfigured(client: TestClient):
    """With no real template ID configured, subscribe returns 400."""
    from app.services.push import is_template_configured

    assert not is_template_configured("TEMPLATE_DAILY_CARD"), (
        "test env must start with templates unconfigured"
    )

    login = _dev_login(client, member=False)
    resp = client.post(
        "/notify/subscribe",
        json={
            "openid": "test-openid",
            "template_id": "TEMPLATE_DAILY_CARD",
            "accept": True,
        },
        headers=_auth(login["token"]),
    )
    assert resp.status_code == 400, resp.text
    assert "推送服务未开通" in resp.json()["detail"]


def test_push_send_subscribe_message_placeholder_not_sent(client: TestClient):
    """send_subscribe_message with a placeholder ID returns failure without
    calling WeChat (access token never fetched)."""
    from app.services.push import send_subscribe_message

    async def _run():
        return await send_subscribe_message(
            openid="test-openid",
            template_id="TEMPLATE_DAILY_CARD",
            data={"thing1": {"value": "测试"}},
        )

    result = asyncio.run(_run())
    assert result["errcode"] == -1
    assert "模板未配置" in result["errmsg"]
