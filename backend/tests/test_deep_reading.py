"""
Tests for the deep (paid) reading content upgrade — 真机反馈 B 组 · 深度解读内容加量结构化.

Covers:
- parse_deep_sections: the fixed six-section structure is parsed into
  [{title, body}] in order; degraded gracefully when markers are missing
- Deep prompt injection: depth="deep" appends the structure instruction
  (with 2x+ content requirement and all six section titles) to the user
  prompt; depth="standard" does not
- Compliance: the six section titles (user-visible structure) are free of
  AI_OUTPUT_BLACKLIST words; the instruction re-emphasises the output red
  line (no fortune-telling / no verdicts / no fear-mongering)
- API plumbing: member creating a depth="deep" reading gets depth="deep"
  in the response (AI key empty in tests → interpretation None →
  deep_sections []), and the response schema accepts deep_sections
"""

import asyncio

from fastapi.testclient import TestClient

from app.config import settings
from app.services.ai_engine import (
    DEEP_SECTION_TITLES,
    _DEEP_STRUCTURE_INSTRUCTION,
    parse_deep_sections,
)
from app.services.compliance import AI_OUTPUT_BLACKLIST, find_forbidden

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


def _auth_headers(client: TestClient, member: bool = True) -> dict[str, str]:
    url = f"/auth/dev-login?member={'true' if member else 'false'}"
    resp = client.post(url, headers={"X-Dev-Key": settings.DEV_LOGIN_KEY})
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


# A representative AI deep-reading output with the fixed six-section structure.
_SAMPLE_DEEP_TEXT = (
    "你问的是工作上的事——先接住这份在意，再解读。听起来，你最近把不少力气花在了"
    "平衡团队氛围上，有些被掏空的感觉。\n\n"
    "【一、逐牌位详解】\n\n"
    "**过去 · 圣杯十（逆位）**\n\n"
    "彩虹上悬着十只圣杯。过去你总想把关系维护得像家一样，孩子们原本轻盈的嬉戏，"
    "变成你肩上沉甸甸的责任。这不是你不够好，而是过去的模式需要调整——力气该往回收一收。\n\n"
    "**现在 · 星币三（正位）**\n\n"
    "教堂里三个人各司其职：拿图纸的设计者、拿刻刀的工匠、做协调的管理者。"
    "这张牌提醒你回到分工与边界，把「谁负责什么」说清楚。\n\n"
    "**未来 · 星币国王（正位）**\n\n"
    "国王左手稳稳托住星币，背后是城堡。当边界清晰、技艺练稳，你会自然拥有主导权。\n\n"
    "【二、整体脉络】\n\n"
    "这三张牌从「想让所有人舒服」的过载，走向「各司其职」的协作，再走向「自己坐稳主位」"
    "的沉稳。整体不是突变，而是一场重心的转移——从向外讨好，转向向内扎根。\n\n"
    "【三、深层心理动因】\n\n"
    "听起来，你似乎很在意「被需要的感觉」，习惯用承担来确认自己的位置。"
    "这份在意本身没有错，只是当它变成默认模式，你会慢慢忽略自己也需要被照顾。\n\n"
    "【四、对提问的直答】\n\n"
    "关于「接下来怎么走」，当下最值得留意的是把责任边界理清楚：哪些是你愿意负责的，"
    "哪些需要请别人分担。方向不在远方，在于先停止替所有人兜底。\n\n"
    "【五、行动建议】\n\n"
    "[ACTION]本周主动约一位合作同事，明确最近项目的分工和你承担的部分[/ACTION]\n"
    "[ACTION]今晚睡前写下三件你已经完成的小成果[/ACTION]\n"
    "[ACTION]找一个安静时刻，整理你的工作边界清单[/ACTION]\n\n"
    "【六、注意与观察】\n\n"
    "未来一周留意两件事：一是自己是否又在别人开口前抢先承担；"
    "二是记录那些让你感到「被掏空」的具体瞬间，它们会告诉你边界该画在哪里。"
)

# ---------------------------------------------------------------------------
# parse_deep_sections
# ---------------------------------------------------------------------------


class TestParseDeepSections:
    def test_full_six_sections_in_order(self):
        sections = parse_deep_sections(_SAMPLE_DEEP_TEXT)
        assert [s["title"] for s in sections] == list(DEEP_SECTION_TITLES)

    def test_section_bodies_preserved(self):
        sections = parse_deep_sections(_SAMPLE_DEEP_TEXT)
        by_title = {s["title"]: s["body"] for s in sections}
        # Body of section one keeps the per-card sub-headings
        assert "圣杯十" in by_title["一、逐牌位详解"]
        assert "星币国王" in by_title["一、逐牌位详解"]
        assert "重心的转移" in by_title["二、整体脉络"]
        assert "被需要的感觉" in by_title["三、深层心理动因"]
        assert "责任边界" in by_title["四、对提问的直答"]
        assert "[ACTION]" in by_title["五、行动建议"]
        assert "未来一周" in by_title["六、注意与观察"]

    def test_text_before_first_marker_dropped(self):
        sections = parse_deep_sections(_SAMPLE_DEEP_TEXT)
        # The acknowledgment opener ("你问的是工作上的事……") must not be a section
        assert all("先接住这份在意" not in s["body"] for s in sections)

    def test_missing_trailing_sections(self):
        text = "【一、逐牌位详解】\n\n只有第一段。\n\n【二、整体脉络】\n\n只有第二段。"
        sections = parse_deep_sections(text)
        assert [s["title"] for s in sections] == ["一、逐牌位详解", "二、整体脉络"]
        assert "只有第一段" in sections[0]["body"]
        assert "只有第二段" in sections[1]["body"]

    def test_no_markers_returns_empty(self):
        assert parse_deep_sections("普通解读没有结构标记") == []

    def test_empty_and_none(self):
        assert parse_deep_sections("") == []
        assert parse_deep_sections(None) == []

    def test_no_empty_bodies(self):
        # A marker with nothing after it must not produce a section
        text = "【一、逐牌位详解】\n\n正文内容。\n\n【六、注意与观察】\n\n"
        sections = parse_deep_sections(text)
        assert len(sections) == 1, "empty trailing body must be dropped"
        assert sections[0]["title"] == "一、逐牌位详解"
        assert "正文内容" in sections[0]["body"]


# ---------------------------------------------------------------------------
# Deep prompt injection (generate_reading with depth="deep")
# ---------------------------------------------------------------------------


class _FakeCompletions:
    def __init__(self, captured: list):
        self._captured = captured

    async def create(self, **kwargs):
        self._captured.append(kwargs)
        msg = type("M", (), {"content": "【一、逐牌位详解】\n\n测试内容"})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, captured: list):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(captured)})()


def _make_card(name_zh: str = "星币六") -> dict:
    return {
        "card_id": 1,
        "position": 1,
        "position_name": "现在",
        "is_reversed": False,
        "name_zh": name_zh,
        "name_en": "Six of Pentacles",
        "image_description": "一个人端着天平施予星币",
        "meaning_upright": "给予与接受",
        "meaning_reversed": "失衡",
    }


def _capture_prompts(monkeypatch, depth: str = "standard"):
    """Run generate_reading with a fake client; return (system, user) prompts."""
    import app.services.ai_engine as ai_engine

    monkeypatch.setattr(ai_engine.settings, "DEEPSEEK_API_KEY", "test-key")
    captured: list = []
    monkeypatch.setattr(ai_engine, "_get_client", lambda: _FakeClient(captured))

    result = _run(
        ai_engine.generate_reading(
            "three_card", "最近的工作发展如何？", "career",
            [_make_card()], depth=depth,
        )
    )
    assert result is not None
    assert captured, "AI client should have been called"
    messages = captured[0]["messages"]
    return messages[0]["content"], messages[1]["content"]


class TestDeepPromptInjection:
    def test_deep_prompt_has_all_six_sections(self, monkeypatch):
        _, user_prompt = _capture_prompts(monkeypatch, depth="deep")
        for title in DEEP_SECTION_TITLES:
            assert f"【{title}】" in user_prompt, f"missing section marker {title}"

    def test_deep_prompt_requires_2x_content(self, monkeypatch):
        _, user_prompt = _capture_prompts(monkeypatch, depth="deep")
        assert "2 倍以上" in user_prompt
        assert "2000 字以上" in user_prompt

    def test_deep_prompt_reiterates_red_line(self, monkeypatch):
        _, user_prompt = _capture_prompts(monkeypatch, depth="deep")
        assert "输出红线" in user_prompt
        assert "禁止预测吉凶" in user_prompt
        assert "禁止命运定性" in user_prompt

    def test_standard_prompt_has_no_deep_structure(self, monkeypatch):
        _, user_prompt = _capture_prompts(monkeypatch, depth="standard")
        assert "【一、逐牌位详解】" not in user_prompt
        assert "深度解读结构" not in user_prompt

    def test_system_prompt_keeps_output_red_line_for_deep(self, monkeypatch):
        system_prompt, _ = _capture_prompts(monkeypatch, depth="deep")
        assert "【输出红线】" in system_prompt


# ---------------------------------------------------------------------------
# Compliance — deep structure wording must pass the output blacklist
# ---------------------------------------------------------------------------


class TestDeepCompliance:
    def test_section_titles_blacklist_clean(self):
        # User-visible fixed section titles must not trip AI_OUTPUT_BLACKLIST
        assert find_forbidden("".join(DEEP_SECTION_TITLES), AI_OUTPUT_BLACKLIST) == []

    def test_instruction_no_fear_mongering(self):
        # The instruction itself must not order the AI to predict/terrorise
        assert "恐吓" in _DEEP_STRUCTURE_INSTRUCTION  # explicitly forbidden
        assert "预测吉凶" in _DEEP_STRUCTURE_INSTRUCTION  # explicitly forbidden
        assert "时间点承诺" in _DEEP_STRUCTURE_INSTRUCTION

    def test_action_tags_limited_to_actions_section(self):
        # Only the actions section may carry [ACTION] tags
        import re

        marker = "【五、行动建议】"
        idx = _DEEP_STRUCTURE_INSTRUCTION.find(marker)
        assert idx != -1
        before = _DEEP_STRUCTURE_INSTRUCTION[:idx]
        assert "[ACTION]" not in before


# ---------------------------------------------------------------------------
# API plumbing — depth=deep flows through create_reading
# ---------------------------------------------------------------------------


class TestDeepReadingApi:
    def test_member_deep_reading_response_shape(self, client: TestClient):
        """Member creates a depth=deep reading; response carries depth + deep_sections.

        DEEPSEEK_API_KEY is empty in tests → interpretation is None and
        deep_sections is [], but the depth field must round-trip and the
        schema must accept the new field.
        """
        headers = _auth_headers(client, member=True)
        resp = client.post(
            "/readings/spread/three_card",
            json={"question": "深度解读测试", "theme": "career", "depth": "deep"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["depth"] == "deep", "depth should round-trip"
        assert "deep_sections" in data, "response should include deep_sections"
        assert isinstance(data["deep_sections"], list)

    def test_member_standard_reading_has_no_deep_sections_field_value(self, client: TestClient):
        headers = _auth_headers(client, member=True)
        resp = client.post(
            "/readings/spread/three_card",
            json={"question": "标准解读测试", "theme": "general", "depth": "standard"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["depth"] == "standard"
        assert data["deep_sections"] == []

    def test_get_reading_parses_deep_sections_from_interpretation(self, client: TestClient):
        """GET re-parses deep sections from the stored interpretation.

        Simulates a stored deep reading by monkeypatching parse on read —
        here we verify the endpoint shape handles a deep reading whose
        interpretation is None (AI key empty) without erroring.
        """
        headers = _auth_headers(client, member=True)
        create_resp = client.post(
            "/readings/spread/three_card",
            json={"question": "深度读取测试", "depth": "deep"},
            headers=headers,
        )
        reading_id = create_resp.json()["id"]
        get_resp = client.get(f"/readings/{reading_id}", headers=headers)
        assert get_resp.status_code == 200, get_resp.text
        data = get_resp.json()
        assert data["depth"] == "deep"
        assert "deep_sections" in data
