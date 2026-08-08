"""
满月复盘 API 测试。

覆盖：
- 空数据 → has_data=False（不发 AI 调用）
- 有愿望（无 AI）→ 本地温柔降级文案（守红线：不预测）
- 当天缓存：第二次 GET 命中缓存（cached=True），不重复生成
- POST /reviews/moon 手动重新生成（cached=False）
- mock AI：JSON 解析、幻觉愿望过滤、代码围栏剥离
- AI prompt 只感知日记情绪倾向、绝不注入日记原文（感知不引用红线）
"""

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db.database import async_session
from app.models.user import User
from app.utils.auth import create_token


def _new_user_headers(openid: str) -> dict[str, str]:
    """创建一个隔离测试用户并返回鉴权头（避免共享 dev-login 用户互相干扰）。"""

    async def _go() -> str:
        async with async_session() as session:
            user = User(openid=openid, nickname="复盘专用")
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return token

    token = asyncio.run(_go())
    return {"Authorization": f"Bearer {token}"}


def _dev_login(client: TestClient) -> dict[str, str]:
    resp = client.post("/auth/dev-login", headers={"X-Dev-Key": settings.DEV_LOGIN_KEY})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _add_wish(client: TestClient, headers: dict[str, str], content: str) -> str:
    resp = client.post("/wishes", json={"content": content}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _add_diary(client: TestClient, headers: dict[str, str], mood: str, reflection: str):
    resp = client.post(
        "/diary/entries",
        json={"mood": mood, "reflection": reflection},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 空态 ─────────────────────────────────────────────────


def test_review_empty_has_no_data(client: TestClient):
    headers = _new_user_headers("review_empty_user")
    resp = client.get("/reviews/moon", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is False
    assert data["wishes"] == []
    assert data["review"] == ""


# ── 本地降级（测试环境无 AI key）── ─────────────────────────────────


def test_review_fallback_with_wishes(client: TestClient):
    headers = _new_user_headers("review_fallback_user")
    _add_wish(client, headers, "换一座城市生活")
    _add_wish(client, headers, "学会游泳")

    resp = client.get("/reviews/moon", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is True
    assert len(data["wishes"]) == 2
    contents = {w["content"] for w in data["wishes"]}
    assert contents == {"换一座城市生活", "学会游泳"}
    assert all(w["status"] == "active" for w in data["wishes"])
    assert data["review"]
    assert len(data["tips"]) == 3
    # 红线：降级文案不得出现「一定会」式预测
    assert "一定会" not in data["review"]


# ── 缓存 ─────────────────────────────────────────────────


def test_review_cached_same_day(client: TestClient):
    headers = _new_user_headers("review_cache_user")
    _add_wish(client, headers, "每天 11 点前睡")

    first = client.get("/reviews/moon", headers=headers)
    assert first.status_code == 200
    assert first.json()["cached"] is False

    second = client.get("/reviews/moon", headers=headers)
    assert second.status_code == 200
    data = second.json()
    assert data["cached"] is True
    assert data["review"] == first.json()["review"]
    assert data["wishes"][0]["content"] == "每天 11 点前睡"


def test_review_force_regenerate(client: TestClient):
    headers = _new_user_headers("review_force_user")
    _add_wish(client, headers, "换一份工作")
    client.get("/reviews/moon", headers=headers)

    resp = client.post("/reviews/moon", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["cached"] is False


# ── mock AI ─────────────────────────────────────────────────


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


class _FakeChat:
    def __init__(self, content: str):
        self.completions = _FakeCompletions(content)


class _FakeAIClient:
    def __init__(self, content: str):
        self.chat = _FakeChat(content)


AI_REVIEW_JSON = (
    '{"wishes":['
    '{"content":"换一座城市生活","status":"grown","note":"八月第二周，offer 到了。你亲手把愿望种进土里，它长出来了。"},'
    '{"content":"编造的愿望","status":"active","note":"幻觉内容应被过滤掉"}'
    '],"review":"月亮没有辜负任何人。它只是用半个月，把愿望筛成了更真实的形状。",'
    '"tips":["给最在意的愿望安排一件明天就能做的小事","把还没动静的愿望轻声读一遍","满月之后是新芽"]}'
)


def test_review_ai_mocked_parses_and_filters(client: TestClient, monkeypatch):
    headers = _new_user_headers("review_ai_user")
    _add_wish(client, headers, "换一座城市生活")
    _add_diary(client, headers, "calm", "今天收拾了行李，心里轻了很多。")

    fake = _FakeAIClient(AI_REVIEW_JSON)
    monkeypatch.setattr("app.api.wishes._get_ai_client", lambda: fake)

    resp = client.get("/reviews/moon", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is True
    # 幻觉愿望被过滤，只留用户真实写下的
    assert [w["content"] for w in data["wishes"]] == ["换一座城市生活"]
    assert data["wishes"][0]["status"] == "grown"
    assert "种进土里" in data["wishes"][0]["note"]
    assert "编造的愿望" not in [w["content"] for w in data["wishes"]]
    assert "月亮没有辜负任何人" in data["review"]
    assert len(data["tips"]) == 3


def test_review_ai_prompt_respects_diary_sensing_redline(client: TestClient, monkeypatch):
    """AI prompt 只能包含日记情绪倾向，绝不能注入日记原文（感知不引用）。"""
    headers = _new_user_headers("review_redline_user")
    _add_wish(client, headers, "希望冬天之前搬进新家")
    _add_diary(client, headers, "anxious", "今天焦虑到失眠，夜里三点还在想工作的事。")

    fake = _FakeAIClient(AI_REVIEW_JSON)
    monkeypatch.setattr("app.api.wishes._get_ai_client", lambda: fake)

    client.get("/reviews/moon", headers=headers)

    prompt_calls = fake.chat.completions.calls
    assert prompt_calls, "应发起 AI 调用"
    user_content = prompt_calls[0]["messages"][1]["content"]
    system_content = prompt_calls[0]["messages"][0]["content"]
    # 情绪倾向进入 prompt（感知）
    assert "情绪倾向" in user_content
    # 日记原文绝不进入 prompt（不引用）
    assert "焦虑到失眠" not in user_content
    assert "夜里三点" not in user_content
    # 红线写在 system prompt 中
    assert "输出红线" in system_content
    assert "不引用、暗示或提及日记" in system_content


def test_review_ai_code_fence_stripped(client: TestClient, monkeypatch):
    headers = _new_user_headers("review_fence_user")
    _add_wish(client, headers, "想学画画")

    fenced = "```json\n" + AI_REVIEW_JSON + "\n```"
    fake = _FakeAIClient(fenced)
    monkeypatch.setattr("app.api.wishes._get_ai_client", lambda: fake)

    resp = client.get("/reviews/moon", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["has_data"] is True
    assert [w["content"] for w in resp.json()["wishes"]] == ["想学画画"]


def test_review_ai_broken_json_falls_back(client: TestClient, monkeypatch):
    headers = _new_user_headers("review_broken_user")
    _add_wish(client, headers, "每天散步半小时")

    fake = _FakeAIClient("这不是 JSON")
    monkeypatch.setattr("app.api.wishes._get_ai_client", lambda: fake)

    resp = client.get("/reviews/moon", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is True
    assert data["review"]  # 本地降级文案兜底
    assert [w["content"] for w in data["wishes"]] == ["每天散步半小时"]


# ── 鉴权 ─────────────────────────────────────────────────


def test_review_requires_auth(client: TestClient):
    assert client.get("/reviews/moon").status_code == 401
    assert client.post("/reviews/moon").status_code == 401


def test_review_diary_and_wishes_compose(client: TestClient):
    """愿望 + 日记混合场景：has_data=True，愿望完整呈现。"""
    headers = _new_user_headers("review_mix_user")
    wid = _add_wish(client, headers, "换一座城市生活")
    _add_diary(client, headers, "calm", "最近在准备面试。")

    resp = client.get("/reviews/moon", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is True
    assert data["wishes"][0]["content"] == "换一座城市生活"
    assert data["date_range"]

    # 愿望状态随 PUT 更新后，复盘里同步呈现
    client.put(f"/wishes/{wid}", json={"status": "grown"}, headers=headers)
    resp = client.post("/reviews/moon", headers=headers)
    assert resp.json()["wishes"][0]["status"] == "grown"
