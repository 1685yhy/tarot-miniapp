"""
新月许愿 API 测试：CRUD + 鉴权 + 长度校验 + 状态枚举 + 月相接口。

每个测试用独立用户（直接插库 + 签发 token），避免共享 dev-login 用户互相干扰。

覆盖：
- GET /moon/phase 需要登录，返回六态之一
- POST /wishes 创建（长度 1~100、空白拒绝、月相记录）
- 同时生长愿望上限 10 条
- GET /wishes 列表（倒序 + status 过滤）
- PUT /wishes/{id} 状态枚举校验 + 属主校验
- DELETE /wishes/{id} 属主校验
- POST /wishes/{id}/bless AI 不可用时本地模板降级
"""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db.database import async_session
from app.models.user import User
from app.utils.auth import create_token


def _user_headers(openid: str) -> dict[str, str]:
    """创建一个隔离测试用户并返回鉴权头。"""

    async def _go() -> str:
        async with async_session() as session:
            user = User(openid=openid, nickname="许愿专用")
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return token

    token = asyncio.run(_go())
    return {"Authorization": f"Bearer {token}"}


def _fresh_headers() -> dict[str, str]:
    return _user_headers(f"wish_user_{uuid4().hex[:12]}")


def _create(client: TestClient, headers: dict[str, str], content: str) -> dict:
    resp = client.post("/wishes", json={"content": content}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── 鉴权 ─────────────────────────────────────────────────


def test_moon_phase_requires_auth(client: TestClient):
    resp = client.get("/moon/phase")
    assert resp.status_code == 401


def test_wishes_require_auth(client: TestClient):
    assert client.get("/wishes").status_code == 401
    assert client.post("/wishes", json={"content": "x"}).status_code == 401


def test_moon_phase_returns_valid_phase(client: TestClient):
    headers = _fresh_headers()
    resp = client.get("/moon/phase", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["phase"] in {"new_moon", "waxing", "first_quarter", "full_moon", "last_quarter", "waning"}
    assert data["emoji"]
    assert data["label"]
    assert data["next_new_moon"]
    assert data["next_full_moon"]


# ── 创建 ─────────────────────────────────────────────────


def test_create_wish_success(client: TestClient):
    headers = _fresh_headers()
    data = _create(client, headers, "愿秋天能在新的城市安定下来")
    assert data["content"] == "愿秋天能在新的城市安定下来"
    assert data["status"] == "active"
    assert data["moon_phase"] in {"new_moon", "waxing", "first_quarter", "full_moon", "last_quarter", "waning"}
    assert data["id"]


def test_create_wish_trims_whitespace(client: TestClient):
    headers = _fresh_headers()
    data = _create(client, headers, "  想学游泳  ")
    assert data["content"] == "想学游泳"


def test_create_wish_empty_rejected(client: TestClient):
    headers = _fresh_headers()
    assert client.post("/wishes", json={"content": "   "}, headers=headers).status_code == 400
    assert client.post("/wishes", json={"content": ""}, headers=headers).status_code == 422


def test_create_wish_too_long_rejected(client: TestClient):
    headers = _fresh_headers()
    resp = client.post("/wishes", json={"content": "愿" * 101}, headers=headers)
    assert resp.status_code in (400, 422)


def test_create_wish_any_time_allowed(client: TestClient):
    """宽松策略：新月前后 3 天以外的日子也允许许愿（只记录月相）。"""
    headers = _fresh_headers()
    data = _create(client, headers, "任何时候都可以许愿")
    assert data["moon_phase"]  # 月相被记录


def test_active_wish_cap_10(client: TestClient):
    headers = _fresh_headers()
    for i in range(10):
        _create(client, headers, f"愿望{i}")
    resp = client.post("/wishes", json={"content": "第11个"}, headers=headers)
    assert resp.status_code == 400
    assert "10" in resp.json()["detail"]
    # 把一条愿望标记为已生长后，可继续许愿
    wishes = client.get("/wishes", headers=headers).json()["wishes"]
    client.put(f"/wishes/{wishes[0]['id']}", json={"status": "grown"}, headers=headers)
    assert client.post("/wishes", json={"content": "第11个"}, headers=headers).status_code == 201


# ── 列表 ─────────────────────────────────────────────────


def test_list_wishes_desc_order_and_status_filter(client: TestClient):
    headers = _fresh_headers()
    w1 = _create(client, headers, "第一个")
    w2 = _create(client, headers, "第二个")

    resp = client.get("/wishes", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    # 倒序：最新在前
    assert data["wishes"][0]["content"] == "第二个"
    assert data["active_count"] == 2

    # 状态过滤
    client.put(f"/wishes/{w2['id']}", json={"status": "grown"}, headers=headers)
    resp = client.get("/wishes?status=active", headers=headers)
    contents = [w["content"] for w in resp.json()["wishes"]]
    assert "第一个" in contents
    assert "第二个" not in contents
    resp = client.get("/wishes?status=grown", headers=headers)
    assert resp.json()["wishes"][0]["content"] == "第二个"
    # active_count 随状态变化
    assert client.get("/wishes", headers=headers).json()["active_count"] == 1


def test_list_wishes_invalid_status_filter(client: TestClient):
    headers = _fresh_headers()
    resp = client.get("/wishes?status=hacked", headers=headers)
    assert resp.status_code == 400


def test_wishes_isolated_between_users(client: TestClient):
    """A 用户的愿望对 B 用户不可见。"""
    ha = _fresh_headers()
    hb = _fresh_headers()
    _create(client, ha, "A的秘密愿望")
    _create(client, hb, "B的愿望")
    contents_a = [w["content"] for w in client.get("/wishes", headers=ha).json()["wishes"]]
    assert contents_a == ["A的秘密愿望"]


# ── 更新 ─────────────────────────────────────────────────


def test_update_wish_status_enum(client: TestClient):
    headers = _fresh_headers()
    wid = _create(client, headers, "改状态")["id"]
    for status in ("active", "grown", "answered"):
        resp = client.put(f"/wishes/{wid}", json={"status": status}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == status
    resp = client.put(f"/wishes/{wid}", json={"status": "evil"}, headers=headers)
    assert resp.status_code == 422


def test_update_wish_not_found(client: TestClient):
    headers = _fresh_headers()
    resp = client.put("/wishes/00000000-0000-0000-0000-000000000000", json={"status": "grown"}, headers=headers)
    assert resp.status_code == 404


# ── 删除与属主隔离 ─────────────────────────────────────────────────


def test_delete_wish_owner_only(client: TestClient):
    headers = _fresh_headers()
    wid = _create(client, headers, "要删的")["id"]
    # 未登录不能删
    assert client.delete(f"/wishes/{wid}").status_code == 401
    # 属主删除成功
    resp = client.delete(f"/wishes/{wid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert client.delete(f"/wishes/{wid}", headers=headers).status_code == 404


def test_update_wish_requires_owner(client: TestClient):
    """B 用户不能更新/删除 A 用户的愿望（属主校验）。"""
    ha = _fresh_headers()
    hb = _fresh_headers()
    wid = _create(client, ha, "A的愿望")["id"]

    resp = client.put(f"/wishes/{wid}", json={"status": "grown"}, headers=hb)
    assert resp.status_code == 404
    assert client.delete(f"/wishes/{wid}", headers=hb).status_code == 404
    assert client.post(f"/wishes/{wid}/bless", headers=hb).status_code == 404

    # 属主仍可操作
    assert client.put(f"/wishes/{wid}", json={"status": "grown"}, headers=ha).status_code == 200


# ── AI 祝福降级 ─────────────────────────────────────────────────


def test_bless_falls_back_to_local_template(client: TestClient):
    """测试环境无 DEEPSEEK_API_KEY → 走本地温柔模板（不预测，只陪伴）。"""
    headers = _fresh_headers()
    wid = _create(client, headers, "想要一只猫")["id"]
    resp = client.post(f"/wishes/{wid}/bless", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == wid
    assert data["blessing"]
    assert "一定会" not in data["blessing"]
