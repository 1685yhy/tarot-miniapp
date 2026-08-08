"""
Tests for the AI reading "psychological touch" enhancements.

Covers:
- Diary state-awareness injection (last-7-day window, mood tendency + focus
  topics distilled from diary, raw content NEVER injected)
- Expired diary entries (>7 days) excluded
- Empty-question state guidance (with / without user context)
- 【输出红线】: AI must never mention/quote/imply diary or history content
- Sentiment layer skipped for empty questions
- End-to-end: the injected blocks actually reach the AI prompt
"""

import asyncio
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.api.readings import _build_user_context_block
from app.config import settings
from app.db.database import async_session
from app.models.diary import DiaryEntry
from app.models.user import User
from app.services.ai_engine import (
    _analyze_sentiment,
    _build_no_question_guidance,
    generate_reading,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _create_user(openid: str) -> str:
    """Create a user directly in the test DB, return their id."""

    async def _inner() -> str:
        async with async_session() as session:
            user = User(openid=openid, nickname="心理触达测试")
            session.add(user)
            await session.flush()
            uid = user.id
            await session.commit()
            return uid

    return _run(_inner())


def _add_diary(user_id: str, entry_date: date, mood: str | None, reflection: str | None) -> None:
    async def _inner():
        async with async_session() as session:
            session.add(
                DiaryEntry(
                    user_id=user_id,
                    entry_date=entry_date,
                    mood=mood,
                    card_id=1,  # seeded card
                    reflection=reflection,
                )
            )
            await session.commit()

    _run(_inner())


def _build_ctx(user_id: str) -> str:
    async def _inner() -> str:
        async with async_session() as session:
            return await _build_user_context_block(session, user_id)

    return _run(_inner())


def _auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/auth/dev-login?member=true",
        headers={"X-Dev-Key": settings.DEV_LOGIN_KEY},
    )
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fake AI client — captures the built prompt so we can assert on it
# ---------------------------------------------------------------------------


class _FakeCompletions:
    def __init__(self, captured: list):
        self._captured = captured

    async def create(self, **kwargs):
        self._captured.append(kwargs)
        msg = type("M", (), {"content": "测试解读内容"})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, captured: list):
        # ai_engine calls client.chat.completions.create(...)
        self.chat = type("Chat", (), {"completions": _FakeCompletions(captured)})()


_SAMPLE_CARDS = [
    {
        "card_id": 1,
        "position": 1,
        "position_name": "过去",
        "is_reversed": False,
        "name_zh": "卡牌1",
        "name_en": "Card 1",
        "image_description": "测试画面",
        "meaning_upright": "正位含义",
        "meaning_reversed": "逆位含义",
    }
]


def _capture_prompt(monkeypatch, question, user_context):
    """Run generate_reading with a fake client, return the user prompt."""
    import app.services.ai_engine as ai_engine

    monkeypatch.setattr(ai_engine.settings, "DEEPSEEK_API_KEY", "test-key")
    captured: list = []
    monkeypatch.setattr(ai_engine, "_get_client", lambda: _FakeClient(captured))

    result = _run(
        generate_reading(
            "three_card", question, "general", _SAMPLE_CARDS, user_context=user_context
        )
    )
    assert result == "测试解读内容", "fake client content should be returned"
    assert captured, "AI client should have been called"
    return captured[0]["messages"][1]["content"]


# ---------------------------------------------------------------------------
# Task 1 — diary state-awareness injection
# ---------------------------------------------------------------------------


class TestDiaryAwarenessBlock:
    def test_injects_mood_tendency_and_focus_without_content(self):
        """Recent diary is distilled to mood tendency + focus topics;
        raw reflection text is never injected."""
        uid = _create_user("psych_touch_window")
        today = date.today()
        _add_diary(uid, today, "happy", "今天抽到星币七，开始学着耐心等待好结果")
        _add_diary(uid, today - timedelta(days=3), "anxious", "工作的事情还是想不明白")

        ctx = _build_ctx(uid)

        assert "【用户近况（最近7天状态感知，仅用于调整语气，严禁在回复中提及）】" in ctx
        # Mood tendency: both moods within the window are injected (CN labels)
        assert "· 用户近期情绪倾向：开心/焦虑" in ctx
        # Focus topics: distilled keyword categories, not quotes
        assert "· 用户近期关注点：工作" in ctx
        # Raw diary content must NOT appear anywhere
        assert "星币七" not in ctx
        assert "想不明白" not in ctx
        assert "抽到" not in ctx

    def test_expired_diary_entries_are_excluded(self):
        """Diary entries older than 7 days must not influence the state."""
        uid = _create_user("psych_touch_expired")
        today = date.today()
        _add_diary(uid, today, "happy", "今天很好")
        _add_diary(uid, today - timedelta(days=8), "sad", "上个月的旧心事，已经过去了")
        _add_diary(uid, today - timedelta(days=30), "sad", "更久远的事情")

        ctx = _build_ctx(uid)

        assert "开心" in ctx
        assert "低落" not in ctx, "8-day-old sad entry must not leak into mood"
        assert "旧心事" not in ctx
        assert "更久远" not in ctx

    def test_only_expired_entries_omits_block(self):
        """User with only expired diary → no diary block at all."""
        uid = _create_user("psych_touch_only_old")
        today = date.today()
        _add_diary(uid, today - timedelta(days=9), "sad", "很久以前的事")

        ctx = _build_ctx(uid)
        assert ctx == ""
        assert "用户近况" not in ctx

    def test_user_without_any_diary_or_history_returns_empty(self):
        uid = _create_user("psych_touch_fresh")
        assert _build_ctx(uid) == ""

    def test_mood_only_entries_still_inject_mood_tendency(self):
        """An entry with mood but no reflection contributes the mood only."""
        uid = _create_user("psych_touch_mood_only")
        _add_diary(uid, date.today(), "calm", None)

        ctx = _build_ctx(uid)
        assert "情绪倾向：平静" in ctx
        assert "关注点" not in ctx

    def test_limit_5_newest_entries(self):
        """At most the 5 newest entries are considered for distillation."""
        uid = _create_user("psych_touch_limit")
        today = date.today()
        for i in range(6):
            _add_diary(uid, today - timedelta(days=i), "calm", "今天天气不错")
        # 6th-newest entry (still within 7 days) mentions 面试 — must be excluded
        _add_diary(uid, today - timedelta(days=5), "calm", "面试的事情让我紧张")

        ctx = _build_ctx(uid)
        assert "工作" not in ctx
        assert "关注点" not in ctx
        assert "面试" not in ctx
        assert "情绪倾向：平静" in ctx

    def test_unmapped_mood_falls_back_to_raw_key(self):
        """Moods outside the known map show the raw key instead of dropping out."""
        uid = _create_user("psych_touch_unmapped")
        _add_diary(uid, date.today(), "weird_key", "今天一般般")

        ctx = _build_ctx(uid)
        assert "情绪倾向：weird_key" in ctx


# ---------------------------------------------------------------------------
# Task 2 — empty-question state guidance (unit level)
# ---------------------------------------------------------------------------


class TestNoQuestionGuidance:
    def test_with_context(self):
        g = _build_no_question_guidance(None, "【关于这位占卜者】\n- 累计占卜次数：3 次")
        assert "【用户未提问】" in g
        assert "像一位懂他的老朋友" in g
        assert "不要直接说「你没有提问」" in g

    def test_blank_question_still_triggers_guidance(self):
        g = _build_no_question_guidance("   ", "some-context")
        assert "【用户未提问】" in g

    def test_fresh_user_no_context(self):
        for ctx in ("", None):
            g = _build_no_question_guidance(None, ctx)
            assert "【用户未提问且无历史】" in g
            assert "第一次使用" in g
            assert "【用户未提问】" not in g, "fresh-user block must not be confused with the with-context block"

    def test_question_present_skips_guidance(self):
        assert _build_no_question_guidance("我和TA的关系走向？", "") == ""
        assert _build_no_question_guidance("  有内容  ", "ctx") == ""

    def test_sentiment_layer_skipped_for_empty_question(self):
        assert _analyze_sentiment(None) == ""
        assert _analyze_sentiment("   ") == ""
        # Sanity: non-empty question still gets tone guidance
        assert "【语气指引】" in _analyze_sentiment("好担心这段关系怎么办")


# ---------------------------------------------------------------------------
# End-to-end: injected blocks reach the AI prompt; content never leaks
# ---------------------------------------------------------------------------


class TestPromptInjection:
    def test_empty_question_prompt_has_guidance_and_red_line(self, monkeypatch):
        ctx = "【关于这位占卜者】\n- 累计占卜次数：3 次\n- 最近占卜记录：\n  · 上次问的是：「工作发展」"
        prompt = _capture_prompt(monkeypatch, None, ctx)

        assert "【用户未提问】" in prompt
        assert "【输出红线】" in prompt
        assert "你感觉到了" in prompt
        # Guidance must sit after the user context
        assert prompt.index("【用户未提问】") > prompt.index("累计占卜次数")

    def test_fresh_user_empty_question_gets_welcome_only(self, monkeypatch):
        prompt = _capture_prompt(monkeypatch, None, "")

        assert "【用户未提问且无历史】" in prompt
        assert "【用户未提问】" not in prompt, "must not inject the with-context block"
        assert "【输出红线】" not in prompt, "no context → nothing to leak → no red line"

    def test_with_question_context_still_gets_red_line(self, monkeypatch):
        prompt = _capture_prompt(monkeypatch, "最近的工作发展如何？", "【关于这位占卜者】\n- 累计占卜次数：5 次")

        assert "【用户未提问" not in prompt
        assert "【输出红线】" in prompt, "history context exists → red line still required"

    def test_with_question_no_context_no_extra_blocks(self, monkeypatch):
        prompt = _capture_prompt(monkeypatch, "最近的工作发展如何？", "")

        assert "【用户未提问" not in prompt
        assert "【输出红线】" not in prompt

    def test_diary_awareness_reaches_prompt_without_quoting(self, monkeypatch):
        """Full chain: DB diary → context block → prompt. The prompt carries
        the distilled state but never the diary text."""
        uid = _create_user("psych_touch_e2e")
        _add_diary(uid, date.today(), "happy", "今天抽到星币七，开始学着耐心等待好结果")
        _add_diary(uid, date.today() - timedelta(days=2), "anxious", "工作的事情还是想不明白")

        ctx = _build_ctx(uid)
        prompt = _capture_prompt(monkeypatch, None, ctx)

        assert "用户近况" in prompt
        assert "情绪倾向：开心/焦虑" in prompt
        assert "关注点：工作" in prompt
        # Diary raw content must never reach the prompt
        assert "星币七" not in prompt
        assert "想不明白" not in prompt
        assert "抽到" not in prompt


# ---------------------------------------------------------------------------
# API level: empty-question reading is accepted end to end
# ---------------------------------------------------------------------------


def test_api_accepts_empty_question_reading(client: TestClient):
    """POST /readings/spread/three_card with a blank question returns 200."""
    headers = _auth_headers(client)
    resp = client.post(
        "/readings/spread/three_card",
        json={"question": "", "theme": "general"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["question"] == ""
    assert len(data["drawn_cards"]) == 3
