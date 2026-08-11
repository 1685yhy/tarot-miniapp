"""
月度星光复盘 API 测试（SDD P1 · T1-2）。

覆盖：
- 鉴权：三端点未登录 401
- 空月份 → 空 stats + 友好文案（不发 AI、不耗配额、不落缓存）
- 首次调用调 AI（mock client）并落缓存；第二次 cached=true 且 AI 只调 1 次；
  缓存命中不消耗非会员配额
- 非会员当日已用满 FREE_DIARY_AI_DAILY → 402（GET 与 regenerate 同受配额）
- 会员不受配额限制
- regenerate 覆盖当月缓存（内容变化后缓存随之更新）
- AI 抛异常 → 降级模板且缓存仍写入（source=fallback）
- AI 返回非法 JSON → 降级模板
- trend_summary/insight/next_guide 与降级文案不含黑名单词
  （注定 / 越来越糟 / 越来越差 / 天生 / 命）
- share-preview 脱敏：无昵称、无日记原文，摘要来自缓存 AI 文案
- 非法月份参数 → 422

测试数据全部直插 DB（显式 entry_date），不依赖当前日期。
"""

import asyncio
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db.database import async_session
from app.models.diary import DiaryEntry
from app.models.star_monthly_review import StarMonthlyReview
from app.models.user import User
from app.utils.auth import create_token

BLACKLIST_WORDS = ("注定", "越来越糟", "越来越差", "天生", "命")

# ── helpers ─────────────────────────────────────────────────────────────


def _new_user(
    openid: str, member: bool = False, quota_used: int = 0
) -> tuple[str, dict[str, str]]:
    """创建隔离测试用户，返回 (user_id, auth_headers)。"""

    async def _go() -> tuple[str, str]:
        async with async_session() as session:
            user = User(openid=openid, nickname="月度复盘", is_member=member)
            if quota_used:
                user.diary_ai_count_today = quota_used
                user.quota_reset_date = datetime.now(timezone.utc).date()
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return user.id, token

    uid, token = asyncio.run(_go())
    return uid, {"Authorization": f"Bearer {token}"}


def _insert_entries(uid: str, entries: list[dict]) -> None:
    """直插当月日记（显式 entry_date，不依赖今天）。"""

    async def _go() -> None:
        async with async_session() as session:
            for e in entries:
                session.add(DiaryEntry(
                    user_id=uid,
                    entry_date=date.fromisoformat(e["date"]),
                    mood=e.get("mood"),
                    card_id=e.get("card_id"),
                    reflection=e.get("reflection"),
                ))
            await session.commit()

    asyncio.run(_go())


def _quota_count(uid: str) -> int:
    async def _go() -> int:
        async with async_session() as session:
            user = await session.get(User, uid)
            return user.diary_ai_count_today

    return asyncio.run(_go())


def _cache_row(uid: str, month: str) -> dict | None:
    async def _go() -> dict | None:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(StarMonthlyReview).where(
                        StarMonthlyReview.user_id == uid,
                        StarMonthlyReview.month == month,
                    )
                )
            ).scalar_one_or_none()
            return json.loads(row.data) if row else None

    return asyncio.run(_go())


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


AI_MONTHLY_JSON = (
    '{"trend_summary":"这个月你的夜空由静默转向明亮，情绪如星火般渐次点亮。",'
    '"insight":"星光不会说谎——你记录的每个夜晚，都是与自己的一次温柔对话。",'
    '"next_guide":"下个月，试着在低落的夜晚也留下一句心情，让星空看清完整的你。"}'
)

AI_MONTHLY_JSON_B = (
    '{"trend_summary":"重新生成：这个月明亮与微暗交错，像夜空自己的呼吸。",'
    '"insight":"重新生成后的洞察。",'
    '"next_guide":"重新生成后的建议。"}'
)


def _assert_no_blacklist(text: str | None) -> None:
    if text is None:
        return
    for word in BLACKLIST_WORDS:
        assert word not in text, f"文案含黑名单词「{word}」: {text}"


# ── 鉴权 ───────────────────────────────────────────────────────────────


def test_review_requires_auth(client: TestClient):
    assert client.get("/journal/review?month=2026-08").status_code == 401
    assert (
        client.post(
            "/journal/review/regenerate", json={"month": "2026-08"}
        ).status_code
        == 401
    )
    assert (
        client.get("/journal/review/share-preview?month=2026-08").status_code
        == 401
    )


# ── 空月份 ─────────────────────────────────────────────────────────────


def test_review_empty_month(client: TestClient):
    uid, headers = _new_user("review_empty_month")
    resp = client.get("/journal/review?month=2026-01", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["month"] == "2026-01"
    assert data["stats"] == {
        "days_recorded": 0,
        "bright_count": 0,
        "dim_count": 0,
        "bright_ratio": 0.0,
    }
    assert data["mood_series"] == []
    assert data["star_color_counts"] == []
    assert data["top_cards"] == []
    # 友好文案（无 AI、无黑名单词）
    assert data["trend_summary"]
    assert "夜空" in data["trend_summary"]
    _assert_no_blacklist(data["trend_summary"])
    assert data["insight"] is None
    assert data["next_guide"] is None
    assert data["cached"] is False
    # 空月不落缓存、不耗配额
    assert _cache_row(uid, "2026-01") is None
    assert _quota_count(uid) == 0


# ── 生成 + 缓存 ─────────────────────────────────────────────────────────


def test_review_generates_then_caches_ai_once(client: TestClient, monkeypatch):
    uid, headers = _new_user("review_cache_month")
    _insert_entries(uid, [
        {"date": "2026-08-03", "mood": "happy", "card_id": 1,
         "reflection": "今天把房间收拾了一遍，心里轻了很多。"},
        {"date": "2026-08-05", "mood": "sad", "card_id": 1},
    ])

    fake = _FakeAIClient(AI_MONTHLY_JSON)
    monkeypatch.setattr("app.services.journal._get_ai_client", lambda: fake)

    resp1 = client.get("/journal/review?month=2026-08", headers=headers)
    assert resp1.status_code == 200, resp1.text
    d1 = resp1.json()
    assert d1["cached"] is False
    assert d1["stats"]["days_recorded"] == 2
    assert d1["stats"]["bright_count"] == 1      # happy=4
    assert d1["stats"]["dim_count"] == 1         # sad=1
    assert d1["stats"]["bright_ratio"] == 0.5
    assert len(d1["mood_series"]) == 2
    assert d1["mood_series"][0]["date"] == "2026-08-03"
    assert d1["mood_series"][0]["mood"] == "happy"
    assert d1["mood_series"][0]["brightness"] == 4
    assert d1["star_color_counts"], "应有星光色统计"
    assert d1["top_cards"] == [{"name": "卡牌1", "count": 2}]
    assert "由静默转向明亮" in d1["trend_summary"]
    assert d1["insight"] and d1["next_guide"]
    _assert_no_blacklist(d1["trend_summary"])
    assert len(fake.chat.completions.calls) == 1, "首次生成应恰好调用一次 AI"

    # AI prompt 含当月数据（卡牌 + 天象 + 情绪标签）
    user_content = fake.chat.completions.calls[0]["messages"][1]["content"]
    system_content = fake.chat.completions.calls[0]["messages"][0]["content"]
    assert "卡牌1" in user_content
    assert "心情: 开心" in user_content
    assert "天象" in user_content
    assert "输出红线" in system_content

    # 第二次命中缓存：不重复调 AI
    resp2 = client.get("/journal/review?month=2026-08", headers=headers)
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["cached"] is True
    assert len(fake.chat.completions.calls) == 1, "缓存命中不得重复调用 AI"

    # 缓存命中不消耗配额（非会员生成时 +1，命中不再加）
    assert _quota_count(uid) == 1


def test_review_ai_prompt_has_astral_events(client: TestClient, monkeypatch):
    """2026-08 有 8-12 狮子座新月 + 日全食，应进入 prompt。"""
    uid, headers = _new_user("review_astral_month")
    _insert_entries(uid, [{"date": "2026-08-01", "mood": "calm"}])

    fake = _FakeAIClient(AI_MONTHLY_JSON)
    monkeypatch.setattr("app.services.journal._get_ai_client", lambda: fake)

    client.get("/journal/review?month=2026-08", headers=headers)
    user_content = fake.chat.completions.calls[0]["messages"][1]["content"]
    assert "狮子座新月" in user_content


# ── 配额（非会员与 FREE_DIARY_AI_DAILY 共享）────────────────────────────


def test_review_nonmember_quota_exhausted_402(client: TestClient):
    uid, headers = _new_user(
        "review_quota_user", quota_used=settings.FREE_DIARY_AI_DAILY
    )
    _insert_entries(uid, [{"date": "2026-08-03", "mood": "happy"}])
    resp = client.get("/journal/review?month=2026-08", headers=headers)
    assert resp.status_code == 402, resp.text

    resp = client.post(
        "/journal/review/regenerate", json={"month": "2026-08"}, headers=headers
    )
    assert resp.status_code == 402, resp.text


def test_review_member_ignores_quota(client: TestClient):
    uid, headers = _new_user(
        "review_member_user", member=True, quota_used=settings.FREE_DIARY_AI_DAILY
    )
    _insert_entries(uid, [{"date": "2026-08-03", "mood": "happy"}])
    resp = client.get("/journal/review?month=2026-08", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cached"] is False


# ── regenerate 覆盖缓存 ─────────────────────────────────────────────────


def test_review_regenerate_overwrites_cache(client: TestClient, monkeypatch):
    uid, headers = _new_user("review_regen_user")
    _insert_entries(uid, [{"date": "2026-08-03", "mood": "happy"}])

    fake = _FakeAIClient(AI_MONTHLY_JSON)
    monkeypatch.setattr("app.services.journal._get_ai_client", lambda: fake)
    d1 = client.get("/journal/review?month=2026-08", headers=headers).json()
    assert "由静默转向明亮" in d1["trend_summary"]
    assert d1["cached"] is False

    # 换一个 AI 输出后 regenerate → 内容变化且覆盖缓存
    fake = _FakeAIClient(AI_MONTHLY_JSON_B)
    resp = client.post(
        "/journal/review/regenerate", json={"month": "2026-08"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    d2 = resp.json()
    assert d2["cached"] is False
    assert "重新生成" in d2["trend_summary"]

    # 后续 GET 命中新缓存
    d3 = client.get("/journal/review?month=2026-08", headers=headers).json()
    assert d3["cached"] is True
    assert "重新生成" in d3["trend_summary"]

    # 非会员 regenerate 也计入当日配额（1 次生成 + 1 次 regenerate）
    assert _quota_count(uid) == 2


# ── 降级（AI 失败/无 key）──────────────────────────────────────────────


def test_review_ai_exception_falls_back_and_caches(
    client: TestClient, monkeypatch
):
    uid, headers = _new_user("review_fallback_month")
    _insert_entries(uid, [
        {"date": "2026-08-03", "mood": "excited"},
        {"date": "2026-08-04", "mood": "happy"},
    ])

    def _boom():
        raise RuntimeError("AI 服务不可用")

    monkeypatch.setattr("app.services.journal._get_ai_client", _boom)

    resp = client.get("/journal/review?month=2026-08", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["trend_summary"]  # 降级模板
    assert data["insight"] and data["next_guide"]
    _assert_no_blacklist(data["trend_summary"])
    _assert_no_blacklist(data["insight"])
    _assert_no_blacklist(data["next_guide"])

    # 降级结果同样落缓存，且 source=fallback
    cached = _cache_row(uid, "2026-08")
    assert cached is not None
    assert cached["source"] == "fallback"
    assert cached["trend_summary"] == data["trend_summary"]

    # 第二次命中缓存，不再尝试 AI
    resp2 = client.get("/journal/review?month=2026-08", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["cached"] is True


def test_review_ai_broken_json_falls_back(client: TestClient, monkeypatch):
    uid, headers = _new_user("review_broken_month")
    _insert_entries(uid, [{"date": "2026-08-03", "mood": "calm"}])

    fake = _FakeAIClient("这不是 JSON")
    monkeypatch.setattr("app.services.journal._get_ai_client", lambda: fake)

    resp = client.get("/journal/review?month=2026-08", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["trend_summary"]  # 降级模板兜底
    _assert_no_blacklist(data["trend_summary"])


def test_review_fallback_without_ai_key(client: TestClient):
    """无 DEEPSEEK_API_KEY（测试环境默认）→ 直接降级模板。"""
    uid, headers = _new_user("review_nokey_month")
    _insert_entries(uid, [{"date": "2026-08-03", "mood": "happy"}])
    resp = client.get("/journal/review?month=2026-08", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["trend_summary"]
    assert _cache_row(uid, "2026-08")["source"] == "fallback"


# ── 黑名单词（AI 输出后处理 + 降级模板合规）────────────────────────────


def test_review_blacklist_words_sanitized(client: TestClient, monkeypatch):
    """AI 输出含黑名单词时，落库/返回前必须被清洗。"""
    uid, headers = _new_user("review_blacklist_month")
    _insert_entries(uid, [{"date": "2026-08-03", "mood": "happy"}])

    dirty = (
        '{"trend_summary":"你注定越来越好，天生就是发光的人，命运在暗中帮忙。",'
        '"insight":"越来越糟的日子总会过去，命里有时终须有。",'
        '"next_guide":"别信命，往前走。"}'
    )
    fake = _FakeAIClient(dirty)
    monkeypatch.setattr("app.services.journal._get_ai_client", lambda: fake)

    resp = client.get("/journal/review?month=2026-08", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for field in ("trend_summary", "insight", "next_guide"):
        _assert_no_blacklist(data[field])

    # 缓存里也是清洗后的内容
    cached = _cache_row(uid, "2026-08")
    assert cached["source"] == "ai"
    for field in ("trend_summary", "insight", "next_guide"):
        _assert_no_blacklist(cached[field])


# ── share-preview（脱敏）───────────────────────────────────────────────


def test_share_preview_desensitized(client: TestClient, monkeypatch):
    uid, headers = _new_user("review_share_user")
    _insert_entries(uid, [
        {"date": "2026-08-03", "mood": "happy",
         "reflection": "私人秘密内容：今天哭了一场，工作的事压得喘不过气。"},
    ])

    fake = _FakeAIClient(AI_MONTHLY_JSON)
    monkeypatch.setattr("app.services.journal._get_ai_client", lambda: fake)
    client.get("/journal/review?month=2026-08", headers=headers)

    resp = client.get(
        "/journal/review/share-preview?month=2026-08", headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) == {"month", "stats", "star_color_counts", "summary"}
    assert data["month"] == "2026-08"
    assert data["summary"]  # 来自缓存的 AI 摘要
    assert data["stats"]["days_recorded"] == 1
    # 脱敏：无昵称、无日记原文
    raw = json.dumps(data, ensure_ascii=False)
    assert "私人秘密内容" not in raw
    assert "哭了一场" not in raw
    assert "月度复盘" not in raw  # 测试用户昵称


def test_share_preview_without_cache(client: TestClient):
    """无缓存时 share-preview 只回本地统计，summary 为空，不触发 AI/配额。"""
    uid, headers = _new_user("review_share_empty")
    _insert_entries(uid, [{"date": "2026-08-03", "mood": "happy"}])
    resp = client.get(
        "/journal/review/share-preview?month=2026-08", headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["summary"] == ""
    assert data["stats"]["days_recorded"] == 1
    assert _quota_count(uid) == 0
    assert _cache_row(uid, "2026-08") is None


# ── 参数校验 ───────────────────────────────────────────────────────────


def test_review_invalid_month_422(client: TestClient):
    uid, headers = _new_user("review_invalid_month")
    assert (
        client.get("/journal/review?month=2026-13", headers=headers).status_code
        == 422
    )
    assert (
        client.get("/journal/review?month=2026-8", headers=headers).status_code
        == 422
    )
    assert client.get("/journal/review", headers=headers).status_code == 422
    assert (
        client.post(
            "/journal/review/regenerate",
            json={"month": "bad-month"},
            headers=headers,
        ).status_code
        == 422
    )
