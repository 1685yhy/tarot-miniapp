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


# ---------------------------------------------------------------------------
# Task 7 · 星光名片：GET /share/wxacode（带 scene=邀请码 的小程序码）
#   + GET /share/card-info（扫码落地页按邀请码查星阶/星光数/昵称）
# ---------------------------------------------------------------------------

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-wxacode-png-bytes"


def _async_ret(value):
    """Wrap a value into an async callable returning it (mock helper)."""
    async def _f(*args, **kwargs):
        return value
    return _f


def test_wxacode_requires_auth(client: TestClient):
    """GET /share/wxacode without a token must be rejected (401)."""
    r = client.get("/share/wxacode")
    assert r.status_code == 401


def test_wxacode_returns_png_with_mocked_wechat(client: TestClient, monkeypatch):
    """Logged-in user gets image/png; WeChat API mocked — wxacode is called
    with scene=invite_code, page=card-landing, env_version=trial."""
    import app.api.share as share_api

    calls = []

    async def fake_get_wxacode(**kwargs):
        calls.append(kwargs)
        return _FAKE_PNG

    monkeypatch.setattr(share_api, "get_wxacode", fake_get_wxacode)

    user = _create_user(f"card_uid_{uuid.uuid4().hex[:8]}", "名片主")
    r = client.get("/share/wxacode", headers=_auth(user["token"]))

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == _FAKE_PNG

    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["scene"].startswith("STAR-")  # user's invite code
    assert kwargs["page"] == "pages/card-landing/card-landing"
    assert kwargs["env_version"] == "trial"  # 体验版即可扫码打开


def test_wxacode_cached_7_days(client: TestClient, monkeypatch):
    """A second request within the cache window does not re-call WeChat."""
    import app.api.share as share_api

    calls = []

    async def fake_get_wxacode(**kwargs):
        calls.append(kwargs)
        return _FAKE_PNG

    monkeypatch.setattr(share_api, "get_wxacode", fake_get_wxacode)

    user = _create_user(f"cache_uid_{uuid.uuid4().hex[:8]}", "缓存用户")
    auth = _auth(user["token"])

    r1 = client.get("/share/wxacode", headers=auth)
    r2 = client.get("/share/wxacode", headers=auth)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.content == _FAKE_PNG
    assert len(calls) == 1  # cache hit — WeChat called exactly once


def test_wxacode_cache_bounded_and_evicts_oldest(client: TestClient, monkeypatch):
    """缓存有界（最终审查 F-4）：条目超上限时逐出最旧；过期条目惰性清理。

    默认上限 500 不便断言，monkeypatch 缩小为 3：
    - 写满 3 条后第 4 个用户写入 → 最旧条目（第一个用户）被逐出
    - TTL 改为已过期（-1s）→ 下次写入时过期条目被清理，只留新条目
    """
    import app.api.share as share_api

    async def fake_get_wxacode(**kwargs):
        return _FAKE_PNG

    monkeypatch.setattr(share_api, "get_wxacode", fake_get_wxacode)
    monkeypatch.setattr(share_api, "_WXACODE_CACHE_MAX", 3)

    users = []
    for tag in ("a", "b", "c"):
        u = _create_user(f"cap_uid_{tag}_{uuid.uuid4().hex[:8]}", f"缓存{tag}")
        r = client.get("/share/wxacode", headers=_auth(u["token"]))
        assert r.status_code == 200
        users.append(u)
    assert len(share_api._wxacode_cache) == 3

    # 第 4 个用户 → 超上限，逐出最旧（第一个用户）
    u_d = _create_user(f"cap_uid_d_{uuid.uuid4().hex[:8]}", "缓存d")
    r = client.get("/share/wxacode", headers=_auth(u_d["token"]))
    assert r.status_code == 200
    assert len(share_api._wxacode_cache) == 3
    assert users[0]["id"] not in share_api._wxacode_cache  # 最旧被逐出
    assert u_d["id"] in share_api._wxacode_cache

    # 过期条目惰性清理：把存量条目的过期时间改为过去（模拟 7 天 TTL 到期）
    # → 下次写入时被 _prune_wxacode_cache 清除，只留新条目
    for key in list(share_api._wxacode_cache):
        share_api._wxacode_cache[key] = (0.0, share_api._wxacode_cache[key][1])
    u_e = _create_user(f"cap_uid_e_{uuid.uuid4().hex[:8]}", "缓存e")
    r = client.get("/share/wxacode", headers=_auth(u_e["token"]))
    assert r.status_code == 200
    assert len(share_api._wxacode_cache) == 1  # 3 条旧条目已过期被清
    assert u_e["id"] in share_api._wxacode_cache


def test_wxacode_service_passes_env_version(monkeypatch):
    """wxacode service must forward env_version into the getwxacodeunlimit body."""
    import app.services.wxacode as svc

    captured = {}

    class _FakeResp:
        headers = {"content-type": "image/png"}
        content = _FAKE_PNG

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return _FakeResp()

    monkeypatch.setattr(svc, "_get_access_token", _async_ret("fake-token"))
    monkeypatch.setattr(svc.httpx, "AsyncClient", _FakeClient)

    png = asyncio.run(svc.get_wxacode(
        scene="STAR-AB12",
        page="pages/card-landing/card-landing",
        env_version="trial",
    ))
    assert png == _FAKE_PNG
    assert "getwxacodeunlimit" in captured["url"]
    assert captured["json"]["env_version"] == "trial"
    assert captured["json"]["scene"] == "STAR-AB12"
    assert captured["json"]["page"] == "pages/card-landing/card-landing"


def test_card_info_returns_star_profile(client: TestClient):
    """GET /share/card-info?code=... → nickname + star tier + stardust (public)."""
    user = _create_user(f"info_uid_{uuid.uuid4().hex[:8]}", "名片主")
    code = client.get("/share/invite-code", headers=_auth(user["token"])).json()["invite_code"]

    # Give the user stardust so the tier is 星光 (index 1), not 微光 (0)
    async def _bump():
        async with async_session() as session:
            u = await session.get(User, user["id"])
            u.stardust_total = 8
            u.star_tier = 1
            await session.commit()
    asyncio.run(_bump())

    r = client.get("/share/card-info", params={"code": code})
    assert r.status_code == 200
    data = r.json()
    assert data["invite_code"] == code
    assert data["nickname"] == "名片主"
    assert data["star_tier"] == 1
    assert data["star_tier_name"] == "星光"
    assert data["stardust_total"] == 8


def test_card_info_null_star_tier_derived_from_stardust(client: TestClient):
    """star_tier=NULL 的用户：card-info 的星阶走 tier_for(stardust_total) 推导。

    test_card_info_returns_star_profile 显式设 star_tier=1（命中直接读取分支），
    本用例补上 NULL 分支（share.py `is not None` 兜底）：stardust 40 ≥ 30
    → tier_for(40) = 2（星辉），不依赖 star_tier 字段本身。
    """
    user = _create_user(f"nulltier_uid_{uuid.uuid4().hex[:8]}", "推导用户")
    code = client.get("/share/invite-code", headers=_auth(user["token"])).json()["invite_code"]

    async def _bump():
        async with async_session() as session:
            u = await session.get(User, user["id"])
            u.stardust_total = 40  # ≥30 阈值 → 星辉（tier 2），<100 星冠
            u.star_tier = None     # 显式 NULL → 走 tier_for 推导分支
            await session.commit()
    asyncio.run(_bump())

    r = client.get("/share/card-info", params={"code": code})
    assert r.status_code == 200
    data = r.json()
    assert data["star_tier"] == 2
    assert data["star_tier_name"] == "星辉"
    assert data["stardust_total"] == 40


def test_card_info_unknown_code_404(client: TestClient):
    """GET /share/card-info with an unknown invite code → 404."""
    r = client.get("/share/card-info", params={"code": "STAR-NOPE"})
    assert r.status_code == 404


def test_card_info_rate_limited_30_per_min_per_ip(client: TestClient):
    """Public /share/card-info caps at 30 req/min per IP (anti-enumeration).

    邀请码 STAR-XXXX 空间小、接口无鉴权，若无限流可被离线枚举批量确认账号。
    用独立 X-Forwarded-For IP 隔离本测试，不影响套件默认 key 的配额。
    """
    ip_headers = {"X-Forwarded-For": "203.0.113.77"}
    for _ in range(30):
        r = client.get("/share/card-info", params={"code": "STAR-UNKNOWN"}, headers=ip_headers)
        assert r.status_code == 404  # 窗口内放行（查询正常执行）
    r = client.get("/share/card-info", params={"code": "STAR-UNKNOWN"}, headers=ip_headers)
    assert r.status_code == 429  # 第 31 次超限
    assert "频繁" in r.json()["detail"]
