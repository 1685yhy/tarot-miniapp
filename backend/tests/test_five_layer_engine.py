"""
Tests for the five-layer psychological mechanism system in ai_engine.py.

Layer 1 认领层    — _build_acknowledgment_layer
                     (self-verification theory: 先接住，再引导)
Layer 2 外化重构  — _build_reframing_block
                     (narrative externalization for difficulty/reversed cards)
Layer 3 行动层    — _build_action_layer
                     (reflection question + 30-second action ending structure)
Layer 4 红线      — _OUTPUT_RED_LINE extended to the full 10 forbidden rules
Layer 5 危机      — _detect_crisis + crisis companionship mode in prompts

Also covers the full assembly order inside generate_reading.
"""

import asyncio

from app.services.ai_engine import (
    _OUTPUT_RED_LINE,
    _build_acknowledgment_layer,
    _build_action_layer,
    _build_reframing_block,
    _detect_crisis,
    _extract_diary_state,
    _extract_mood_labels,
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


def _make_card(name_zh: str, is_reversed: bool = False) -> dict:
    return {
        "card_id": 1,
        "position": 1,
        "position_name": "过去",
        "is_reversed": is_reversed,
        "name_zh": name_zh,
        "name_en": "Card 1",
        "image_description": "测试画面",
        "meaning_upright": "正位含义",
        "meaning_reversed": "逆位含义",
    }


_DIARY_BLOCK = (
    "【用户近况（最近7天状态感知，仅用于调整语气，严禁在回复中提及）】\n"
    "· 用户近期情绪倾向：低落/焦虑\n"
    "· 用户近期关注点：工作\n"
)


# ---------------------------------------------------------------------------
# Fake AI client — captures both prompts
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


def _capture_prompts(monkeypatch, question, user_context="", cards=None,
                     theme=None, persona=None):
    """Run generate_reading with a fake client; return (system, user) prompts."""
    import app.services.ai_engine as ai_engine

    monkeypatch.setattr(ai_engine.settings, "DEEPSEEK_API_KEY", "test-key")
    captured: list = []
    monkeypatch.setattr(ai_engine, "_get_client", lambda: _FakeClient(captured))

    result = _run(
        generate_reading(
            "three_card", question, theme, cards or [_make_card("星币六")],
            persona=persona, user_context=user_context,
        )
    )
    assert result == "测试解读内容", "fake client content should be returned"
    assert captured, "AI client should have been called"
    messages = captured[0]["messages"]
    return messages[0]["content"], messages[1]["content"]


# ---------------------------------------------------------------------------
# Layer 1 — acknowledgment
# ---------------------------------------------------------------------------


class TestAcknowledgmentLayer:
    def test_question_career_references_intent(self):
        b = _build_acknowledgment_layer("这次跳槽能成吗？", "career", None)
        assert "工作上的事" in b
        assert "先接住" in b
        assert "再解读" in b

    def test_question_love_references_love(self):
        b = _build_acknowledgment_layer("TA还爱我吗？", "love", None)
        assert "感情上的事" in b

    def test_question_general_no_verbatim_copy(self):
        q = "我和同事闹矛盾了怎么办"
        b = _build_acknowledgment_layer(q, None, None)
        assert "心里挂念的这件事" in b
        assert q not in b, "opening must reference intent, never the verbatim question"

    def test_diary_mood_echo_without_content(self):
        b = _build_acknowledgment_layer(None, None, None, diary_state=_DIARY_BLOCK)
        assert "低落/焦虑" in b
        assert "疲惫" in b, "gentle echo example expected"
        assert "绝不能引用" in b, "must forbid quoting diary content"
        assert "关注点" not in b, "focus topics must not be echoed into the opener"

    def test_universal_opener_when_no_context(self):
        b = _build_acknowledgment_layer(None, None, None)
        assert "深夜问牌的人，心里都藏着一句没说完的话" in b

    def test_order_rule_forced(self):
        b = _build_acknowledgment_layer("不知道该怎么办", "general", None)
        assert "顺序强制" in b
        assert "先接住" in b
        assert "新视角" in b


# ---------------------------------------------------------------------------
# Layer 2 — externalization reframing
# ---------------------------------------------------------------------------


class TestReframingBlock:
    def test_tower_template(self):
        b = _build_reframing_block([_make_card("高塔")])
        assert "有些结构本来就是用来拆掉的" in b
        assert "这不是…而是…" in b
        assert "禁止" in b and "你的命" in b

    def test_death_template(self):
        b = _build_reframing_block([_make_card("死神")])
        assert "转化" in b
        assert "再撑一下" in b

    def test_sword_ten_template(self):
        b = _build_reframing_block([_make_card("宝剑十")])
        assert "可以放下了" in b

    def test_devil_template(self):
        b = _build_reframing_block([_make_card("恶魔")])
        assert "钥匙已经在你手里" in b

    def test_reversed_any_card_gets_generic_template(self):
        b = _build_reframing_block([_make_card("圣杯七", is_reversed=True)])
        assert "逆位不是凶" in b
        assert "向内收" in b

    def test_upright_normal_cards_return_empty(self):
        assert _build_reframing_block([_make_card("星币六")]) == ""

    def test_empty_cards_return_empty(self):
        assert _build_reframing_block([]) == ""

    def test_mixed_tower_and_reversed_both_templates(self):
        b = _build_reframing_block([
            _make_card("高塔"),
            _make_card("星币九", is_reversed=True),
        ])
        assert "有些结构本来就是用来拆掉的" in b
        assert "逆位不是凶" in b

    def test_no_duplicate_templates(self):
        b = _build_reframing_block([
            _make_card("高塔"),
            _make_card("高塔", is_reversed=True),
        ])
        assert b.count("有些结构本来就是用来拆掉的") == 1
        assert b.count("逆位不是凶") == 1


# ---------------------------------------------------------------------------
# Layer 3 — action layer
# ---------------------------------------------------------------------------


class TestActionLayer:
    def test_fixed_ending_structure(self):
        b = _build_action_layer("general", [_make_card("星币六")])
        assert "给你两个问题，不用现在回答" in b
        assert "30 秒的小事" in b

    def test_common_questions_present(self):
        b = _build_action_layer("general", [_make_card("星币六")])
        assert "重要的到底是什么" in b
        assert "一年后的你回头看今天" in b

    def test_love_question(self):
        b = _build_action_layer("love", [_make_card("恋人")])
        assert "如果这段关系继续，你希望它是什么形状" in b

    def test_career_question(self):
        b = _build_action_layer("career", [_make_card("权杖十")])
        assert "上一次你成功走过类似情况" in b

    def test_no_self_blame_questions(self):
        b = _build_action_layer("general", [_make_card("星币六")])
        assert "禁止自责" in b
        assert "是不是你不够好" in b, "the forbidden self-blame example must be stated"

    def test_thirty_second_actions_pool(self):
        b = _build_action_layer("general", [_make_card("星币六")])
        assert "写进今天的日记" in b
        assert "设为壁纸" in b
        assert "不用发出去" in b

    def test_reversed_card_wallpaper_variant(self):
        b = _build_action_layer("general", [_make_card("宝剑十", is_reversed=True)])
        assert "把这张逆位牌设为壁纸" in b


# ---------------------------------------------------------------------------
# Layer 4 — red line (10 rules)
# ---------------------------------------------------------------------------


class TestRedLineTenRules:
    def test_all_ten_rules_present(self):
        for phrase in (
            "一定会",          # 1 no prediction
            "时间点",          # 2 no time commitment
            "再不行动就来不及了",  # 3 no threat
            "你就是这种命",    # 4 no fate verdict
            "你身体里有个坎",  # 5 no health diagnosis
            "投资",            # 6 no finance/investment/legal advice
            "感觉到你被",      # 7 no pseudo-reading
            "解锁",            # 8 no paywall bait
            "人格",            # 9 no humiliation / personality verdict
            "有塔罗就够了",    # 10 no replacing professional help
        ):
            assert phrase in _OUTPUT_RED_LINE, f"red line missing: {phrase}"
        for i in range(1, 11):
            assert f"{i}. " in _OUTPUT_RED_LINE, f"rule {i} missing"

    def test_keeps_perception_rule(self):
        assert "你感觉到了" in _OUTPUT_RED_LINE
        assert "你看到了" in _OUTPUT_RED_LINE

    def test_red_line_always_in_system_prompt(self, monkeypatch):
        sys_p, user_p = _capture_prompts(monkeypatch, "最近运势如何", user_context="")
        assert "【输出红线】" in sys_p, "red line must be unconditional in the system layer"
        assert "10条铁律" in sys_p


# ---------------------------------------------------------------------------
# Layer 5 — crisis detection
# ---------------------------------------------------------------------------


class TestCrisisDetection:
    def test_keywords_in_question(self):
        for q in ("我不想活了", "有时会想结束自己", "有没有办法不伤害自己",
                  "活着没意思", "想死的心都有了"):
            assert _detect_crisis(q) is True, q

    def test_normal_questions_not_crisis(self):
        assert _detect_crisis("最近工作压力好大怎么办") is False
        assert _detect_crisis("和他分手了很难过") is False
        assert _detect_crisis(None) is False
        assert _detect_crisis("   ") is False

    def test_diary_keyword_triggers(self):
        diary = "【用户近况】\n· 用户近期情绪倾向：低落\n· 用户近期关注点：健康\n自杀"
        assert _detect_crisis(None, diary_state=diary) is True

    def test_low_mood_diary_alone_does_not_trigger(self):
        diary = "【用户近况】\n· 用户近期情绪倾向：低落"
        assert _detect_crisis(None, diary_state=diary) is False
        assert _detect_crisis("最近状态不太好", diary_state=diary) is False

    def test_low_mood_plus_keyword_in_question_triggers(self):
        diary = "【用户近况】\n· 用户近期情绪倾向：低落"
        assert _detect_crisis("不想活了", diary_state=diary) is True


class TestDiaryStateExtraction:
    def test_extract_diary_block_only(self):
        ctx = "【关于这位占卜者】\n- 累计占卜次数：3 次\n\n" + _DIARY_BLOCK
        ds = _extract_diary_state(ctx)
        assert "【用户近况" in ds
        assert "情绪倾向：低落/焦虑" in ds
        assert "累计占卜次数" not in ds, "history block must not leak into diary state"

    def test_no_diary_returns_empty(self):
        assert _extract_diary_state("【关于这位占卜者】\n- 累计占卜次数：3 次") == ""
        assert _extract_diary_state(None) == ""
        assert _extract_diary_state("") == ""

    def test_mood_labels(self):
        assert _extract_mood_labels(_DIARY_BLOCK) == "低落/焦虑"
        assert _extract_mood_labels("no mood here") == ""
        assert _extract_mood_labels(None) == ""


# ---------------------------------------------------------------------------
# Crisis prompt injection — pure companionship, no card content
# ---------------------------------------------------------------------------


class TestCrisisPromptInjection:
    def test_crisis_referral_in_system_and_no_cards(self, monkeypatch):
        sys_p, user_p = _capture_prompts(monkeypatch, "我不想活了，最近真的好难")

        assert "【危机陪伴模式·强制】" in sys_p
        assert "400-161-9995" in sys_p
        assert "12355" in sys_p
        assert "牌不是医生" in sys_p

        # 无牌面引申: cards never enter the prompt in crisis mode
        assert "抽取的牌" not in user_p
        assert "画面解读指引" not in user_p
        assert "正位" not in user_p and "逆位" not in user_p

        # 纯陪伴: no interpretation machinery at all
        assert "【开场先接住" not in user_p
        assert "【外化重构" not in user_p
        assert "【结尾行动层" not in user_p
        assert "给你两个问题" not in user_p
        assert "【行动建议要求" not in user_p

    def test_crisis_user_prompt_asks_for_companionship(self, monkeypatch):
        sys_p, user_p = _capture_prompts(monkeypatch, "活着没意思")
        assert "危机陪伴模式" in user_p
        assert "纯陪伴" in user_p

    def test_normal_reading_has_no_crisis_block(self, monkeypatch):
        sys_p, user_p = _capture_prompts(monkeypatch, "最近工作怎么样")
        assert "危机陪伴模式" not in sys_p
        assert "抽取的牌" in user_p


# ---------------------------------------------------------------------------
# Assembly order inside generate_reading
# ---------------------------------------------------------------------------


class TestPromptAssemblyOrder:
    def test_five_layer_order(self, monkeypatch):
        ctx = "【关于这位占卜者】\n- 累计占卜次数：3 次\n\n" + _DIARY_BLOCK
        sys_p, user_p = _capture_prompts(
            monkeypatch,
            "好担心这次跳槽能不能成",
            user_context=ctx,
            theme="career",
            cards=[_make_card("高塔", is_reversed=True)],
        )
        # 认领层 → 牌面教学 → 情感语气 → 外化重构 → 用户上下文 → 红线 →
        # 行动层 → 收尾金句
        assert user_p.index("【开场先接住】") < user_p.index("抽取的牌")
        assert user_p.index("抽取的牌") < user_p.index("【语气指引】")
        assert user_p.index("【语气指引】") < user_p.index("【外化重构")
        assert user_p.index("【外化重构") < user_p.index("累计占卜次数")
        assert user_p.index("累计占卜次数") < user_p.index("【输出红线】")
        assert user_p.index("【输出红线】") < user_p.index("【结尾行动层")
        assert user_p.index("【结尾行动层") < user_p.index("【收尾指引】")

    def test_ack_echoes_diary_mood_in_prompt(self, monkeypatch):
        ctx = "【关于这位占卜者】\n- 累计占卜次数：3 次\n\n" + _DIARY_BLOCK
        sys_p, user_p = _capture_prompts(monkeypatch, None, user_context=ctx)
        assert "低落/焦虑" in user_p, "acknowledgment should echo the mood tendency"
        assert "绝不能引用" in user_p

    def test_no_question_fresh_user_gets_universal_ack(self, monkeypatch):
        sys_p, user_p = _capture_prompts(monkeypatch, None, user_context="")
        assert "深夜问牌的人，心里都藏着一句没说完的话" in user_p
        assert "【用户未提问且无历史】" in user_p
