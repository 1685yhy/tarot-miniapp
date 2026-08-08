"""
Tarot AI interpretation engine.

Uses DeepSeek API (OpenAI-compatible) to generate thoughtful tarot
readings based on the cards drawn and the user's question.

Supports multiple reader personas and user-history context injection
so the AI remembers who it's talking to.
"""

import datetime
import logging
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.config import settings
from app.services.ai_personas import get_persona, get_persona_prompt_suffix

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Client – lazily initialised at module level; if DEEPSEEK_API_KEY is
# empty the first call returns None, which is handled by the endpoint.
# -------------------------------------------------------------------
_ai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _ai_client
    if _ai_client is None:
        _ai_client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    return _ai_client


SYSTEM_PROMPT = """你是一位经验丰富的塔罗占卜师，拥有20年解读经验。你温柔、智慧且富有洞察力。

解读规则：
1. 先说明牌阵中每张牌在对应位置的含义
2. 将牌意与用户的问题/情况紧密联系起来
3. 把多张牌串联成一个完整的故事
4. 既指出积极的方面，也温和地提醒需要注意的问题
5. 最后给出具体的建议和行动指引
6. 使用温暖、神秘但不过分夸张的语气
7. 不要声称能100%预测未来，而是引导用户反思和觉察

禁忌：
- 不预测死亡、严重疾病或法律问题
- 不对用户的重大决定（离婚、辞职等）给出绝对化的建议
- 始终强调用户自己有选择的自由和能力"""


ZODIAC_CN = {
    "aries": "白羊座", "taurus": "金牛座", "gemini": "双子座",
    "cancer": "巨蟹座", "leo": "狮子座", "virgo": "处女座",
    "libra": "天秤座", "scorpio": "天蝎座", "sagittarius": "射手座",
    "capricorn": "摩羯座", "aquarius": "水瓶座", "pisces": "双鱼座",
}

_THEME_MEANING_KEY_MAP = {
    "love": ("love_upright", "love_reversed"),
    "career": ("career_upright", "career_reversed"),
    "finance": ("finance_upright", "finance_reversed"),
}


def _get_time_greeting() -> str:
    """Return a time-of-day contextual greeting based on the current hour."""
    hour = datetime.datetime.now().hour
    if 6 <= hour < 12:
        return "早安，新的一天，星光与你同在..."
    elif 12 <= hour < 18:
        return "午后的阳光里，让我们看看命运的指引..."
    elif 18 <= hour < 22:
        return "夜幕降临，星光渐亮..."
    else:
        return "夜深人静，是最适合与自己对话的时刻..."


_SPREAD_TYPE_NAMES = {
    "three_card": "三牌占卜",
    "triangle": "恋人三角",
    "decision": "二择一",
    "celtic_cross": "凯尔特十字",
    "career": "事业牌阵",
    "finance": "财运牌阵",
    "life_cross": "人生十字",
    "horseshoe": "马蹄牌阵",
    "relationship": "关系牌阵",
    "year_ahead": "年度运势",
    "daily": "每日占卜",
}

_THEME_LABELS = {
    "love": "爱情",
    "career": "事业",
    "finance": "财运",
    "general": "综合",
}


def _build_user_context(
    total_count: int = 0,
    common_spread: str | None = None,
    common_theme: str | None = None,
    streak: int = 0,
    last_3_summaries: list[str] | None = None,
) -> str:
    """Build a context block about the user's reading history.

    This is injected into the AI prompt so the tarot reader "remembers"
    the user and can personalise the reading.

    Args:
        total_count:   Total number of readings the user has ever done.
        common_spread: Most frequent spread type key, or None.
        common_theme:  Most frequent theme key (love/career/finance/general), or None.
        streak:        Consecutive-day reading streak length.
        last_3_summaries: Short summaries (question or spread name) of the
                          last 3 readings, most recent first.

    Returns:
        A formatted Chinese-language context block, or empty string if
        there is no history.
    """
    if total_count <= 0:
        return ""
    spread_name = _SPREAD_TYPE_NAMES.get(common_spread or "", common_spread or "")
    theme_label = _THEME_LABELS.get(common_theme or "", common_theme or "")

    lines = ["\n【关于这位占卜者】"]
    lines.append(f"- 累计占卜次数：{total_count} 次")
    if spread_name:
        lines.append(f"- 常用牌阵：{spread_name}")
    if theme_label and common_theme != "general":
        lines.append(f"- 常问主题：{theme_label}")
    if streak > 1:
        lines.append(f"- 已连续占卜 {streak} 天")

    if last_3_summaries:
        lines.append("- 最近占卜记录：")
        labels = ["上次", "再上次", "之前"]
        for i, summary in enumerate(last_3_summaries):
            if i >= len(labels):
                break
            if summary.strip():
                lines.append(f"  · {labels[i]}问的是：「{summary.strip()[:60]}」")

    lines.append("")
    return "\n".join(lines)


def _analyze_sentiment(question: str | None) -> str:
    """Analyze the user's question for emotional keywords and return tone guidance."""
    if not question:
        return ""

    anxious_words = ["担心", "焦虑", "害怕", "怎么办", "紧张", "不安", "惶恐", "忧虑", "纠结"]
    exciting_words = ["机会", "希望", "新", "机遇", "开始", "突破", "挑战", "成长"]
    sad_words = ["分手", "失去", "难过", "伤心", "痛苦", "离别", "结束", "失望", "孤独", "受伤"]

    anxiety_count = sum(1 for w in anxious_words if w in question)
    exciting_count = sum(1 for w in exciting_words if w in question)
    sad_count = sum(1 for w in sad_words if w in question)

    if anxiety_count > 0 and anxiety_count >= exciting_count and anxiety_count >= sad_count:
        return "【语气指引】用户此刻可能带着焦虑或不安。请用温柔、安抚的语气回应，像老朋友一样给予安全感，先缓解紧张情绪再做解读。"
    if sad_count > 0 and sad_count >= anxiety_count and sad_count >= exciting_count:
        return "【语气指引】用户此刻情绪可能比较低落。请用富有同理心的语气回应，传递温暖和关怀，让对方感到被理解和支持。"
    if exciting_count > 0:
        return "【语气指引】用户似乎对未来充满期待和希望。请用积极、充满能量的语气回应，鼓励用户勇敢抓住机遇。"
    return ""


# ── Empty-question state guidance ────────────────────────────────────────
# When the user writes no question, the AI reads the cards against the
# user's current life stage instead — using whatever context exists
# (reading history + recent diary state awareness).

_NO_QUESTION_GUIDANCE_HAS_CONTEXT = (
    "\n\n【用户未提问】用户没有写下具体问题。请结合上述用户近况（历史解读+日记），"
    "解读这组牌「对用户此刻人生阶段」的整体意义——像一位懂他的老朋友，"
    "指出他当前最可能在意的事情，并给出温柔的提示。不要直接说「你没有提问」，要自然地解读。"
)

_NO_QUESTION_GUIDANCE_FRESH_USER = (
    "\n\n【用户未提问且无历史】这是用户第一次使用。请以温柔欢迎的语气解读牌意，"
    "并在结尾邀请他写下问题获得更专属的解读。"
)

# ── Output red lines (Layer 4): 10 hard safety rules ────────────────────
# Derived from the psychology research. Always injected at the top of the
# SYSTEM prompt (unconditional), plus re-injected into the user prompt when
# user context (history + diary) exists.
#
# Rule 7 also covers the "never expose context sources" boundary: the AI may
# sense the user's recent state (history + diary awareness) and adjust
# tone/angle, but must never mention, quote, or imply the diary or history
# content — the user must feel "understood", never "read".

_OUTPUT_RED_LINE = (
    "\n\n【输出红线】以下10条铁律，解读时必须无条件遵守：\n"
    "1. 禁止预测具体事件、时间或结果：不说「一定会」「注定」「月底」「几月几号」等确定性断言；即使复述用户原话或概括其担忧，也不要对具体时间窗口（如「月底前」「这个月内」）做任何判断，哪怕只是「可能」级别的模糊判断。\n"
    "2. 禁止时间点承诺：不承诺任何事情会在某个具体时间点发生，也不对「某段时间内会不会有结果」下判断。\n"
    "3. 禁止恐吓或威胁式表达：不说「再不行动就来不及了」之类制造恐慌的话。\n"
    "4. 禁止命运定性：不说「你就是这种命」「命中注定」之类的话。\n"
    "5. 禁止健康诊断：不评判用户的身体或精神状况，不说「你身体里有个坎」之类的话。\n"
    "6. 禁止财务、投资、法律建议：不给具体的理财、投资、诉讼或法律建议。\n"
    "7. 禁止伪读取：不声称「我感觉到你被背叛过」之类基于臆测的断言；表达共情时用「听起来…」「似乎…」等推测式措辞，绝对禁止「我能感觉到你…」「我感受到你…」这类断言句式——哪怕说的是情绪，也只能用「听起来，这份急迫感沉甸甸的」这样的推测式说法。\n"
    "8. 禁止诱导消费：不暗示「关键信息需要解锁」或「付费才能看到」。\n"
    "9. 禁止羞辱或人格定性：软性提醒止步于行为模式，不上升到人格评判。\n"
    "10. 禁止替代专业帮助：不暗示「有塔罗就够了」；涉及心理、健康等专业问题时，应建议咨询专业人士。\n"
    "另外，你可以在解读中体现对用户处境的温柔理解（语气、角度），但绝不能在回复中提及、引用、"
    "暗示用户日记或历史记录的具体内容。用户没有主动告诉你的信息，就是「你感觉到了」而不是「你看到了」。"
    "自然地共情，不暴露信息来源。"
)


# ── Layer 5: crisis detection & referral (self-harm / suicidal ideation) ─
# When triggered, the AI switches to pure companionship: no card
# interpretation at all, and the professional-help referral is mandatory.

_CRISIS_KEYWORDS = (
    "不想活", "想死", "自杀", "轻生", "活不下去", "结束自己",
    "结束生命", "伤害自己", "自残", "了结自己", "活着没意思",
)

_CRISIS_REFERRAL_BLOCK = (
    "\n\n【危机陪伴模式·强制】用户可能正经历难以承受的时刻。你此刻的唯一任务是陪伴，不是解读：\n"
    "1. 禁止任何牌面引申、牌意分析或建议——本次不解读牌。\n"
    "2. 开头必须传达（可近义改写，但信息完整）：「牌不是医生。如果你正经历难以承受的时刻，"
    "请先联系专业支持：心理援助热线 400-161-9995 或 12355。今天最重要的事是照顾自己，解读可以改天。」\n"
    "3. 全篇语气为纯陪伴：让对方感到「被看见、被在乎」；告诉他寻求帮助是勇敢的，不是软弱。\n"
    "4. 输出红线10条依然全部生效。"
)


def _detect_crisis(question: str | None, diary_state: str | None = None) -> bool:
    """Detect self-harm / suicidal-ideation signals (Layer 5).

    Triggers when a crisis keyword appears in the question, or in the diary
    state block. Diary state only ever carries distilled labels (mood
    tendency + focus topics — raw content is never injected), so the
    intended diary path is "low mood + explicit keyword", which the keyword
    check covers; the defensive keyword scan also catches any raw text that
    slips through.

    Args:
        question:    The user's question text, or None.
        diary_state: The diary state-awareness block (distilled), or None.

    Returns:
        True when the reading must switch to crisis companionship mode.
    """
    if question and any(kw in question for kw in _CRISIS_KEYWORDS):
        return True
    if diary_state and any(kw in diary_state for kw in _CRISIS_KEYWORDS):
        return True
    return False


# ── Layer 1: acknowledgment ("先接住，再引导") ───────────────────────────
# Self-verification theory (Swann): mirror the self the user already knows
# before offering a new perspective — reversing the order triggers
# resistance. The opener references the question's intent (never verbatim),
# or gently echoes the diary mood state (never the content), or falls back
# to a universal human opener when there is no context at all.

_THEME_ACK_REFS = {
    "love": "感情上的事",
    "career": "工作上的事",
    "finance": "金钱上的事",
}

_UNIVERSAL_ACK_OPENER = "深夜问牌的人，心里都藏着一句没说完的话。"

_ACK_ORDER_RULE = (
    "\n【顺序强制】解读顺序必须是：先接住对方的情绪与自我（共情、确认、不评判），"
    "再给新视角（牌面信息）。顺序反了会触发抗拒，务必遵守。"
)

_DIARY_BLOCK_HEADER = "【用户近况"


def _extract_diary_state(user_context: str | None) -> str:
    """Pull the diary state-awareness block out of a combined user context.

    The combined context (built by ``_build_user_context_block`` in the
    readings API) is the reading-history block plus the diary block; only
    the diary part feeds crisis detection and the acknowledgment layer.

    Returns the diary block (from 【用户近况 to the end), or "".
    """
    if not user_context:
        return ""
    idx = user_context.find(_DIARY_BLOCK_HEADER)
    if idx < 0:
        return ""
    return user_context[idx:]


def _extract_mood_labels(diary_state: str | None) -> str:
    """Extract the distilled mood labels (e.g. '低落/焦虑') from a diary block."""
    if not diary_state:
        return ""
    marker = "情绪倾向："
    idx = diary_state.find(marker)
    if idx < 0:
        return ""
    rest = diary_state[idx + len(marker):]
    line = rest.splitlines()[0] if rest else ""
    return line.strip()


def _build_acknowledgment_layer(
    question: str | None,
    theme: str | None,
    persona: str | None = None,
    diary_state: str | None = None,
) -> str:
    """Layer 1 — build the personalized acknowledgment opener instruction.

    - Question present  → reference the question's intent by theme
      (「你问的是工作上的事——先接住这份在意，再解读」), never verbatim.
    - No question, diary mood state present → gently echo the mood without
      quoting any content (「最近似乎有些疲惫」, not 「你周三写了很累」 —
      consistent with the output red line).
    - No context at all → universal human opener (「深夜问牌的人，心里都
      藏着一句没说完的话」).
    - Always appends the forced order rule: acknowledge first, then the new
      perspective (self-verification theory).

    ``persona`` is accepted for signature compatibility; voice is already
    handled by the persona prompt suffix in the system prompt.

    Returns an instruction block, or "" when there is nothing to inject.
    """
    parts: list[str] = []
    if question and question.strip():
        ref = _THEME_ACK_REFS.get(theme or "", "心里挂念的这件事")
        parts.append(
            f"【开场先接住】用户问的是{ref}——开头必须先接住这份在意"
            f"（例如：「你问的是{ref}——先接住这份在意，再解读」），"
            f"让对方感到被听懂，然后再开始解读。"
        )
    else:
        moods = _extract_mood_labels(diary_state)
        if moods:
            parts.append(
                f"【开场先接住】用户近况显示近期情绪倾向「{moods}」——"
                f"开头可温和呼应这份状态（例如「最近似乎有些疲惫」），"
                f"但绝不能引用或提及任何具体内容（这是输出红线）。"
                f"先接住情绪，再开始解读。"
            )
        else:
            parts.append(
                f"【开场先接住】对方深夜问牌，心里多半藏着一句没说完的话——"
                f"用一句普遍人性的开场先接住这份心情"
                f"（例如：「{_UNIVERSAL_ACK_OPENER}」），再开始解读。"
            )
    parts.append(_ACK_ORDER_RULE)
    parts.append(
        "【措辞红线】接住情绪时用「听起来…」「似乎…」等推测式措辞，"
        "绝对禁止「我能感觉到你…」「我感受到你…」这类断言句式"
        "（哪怕说的是情绪也不行，那也是一种伪读取）。"
    )
    return "\n".join(parts)


# ── Layer 2: externalization reframing (difficulty / reversed cards) ─────
# Narrative-therapy externalization (White & Epston): "the person is not
# the problem; the problem is the problem." Difficulty cards (高塔 / 死神 /
# 宝剑十 / 恶魔) and any reversed card get a reframing template injected as
# few-shot guidance. Fatalistic phrasing ("你的命/你的错/你完了") is
# forbidden; the "这不是…而是…" sentence shape is enforced.

_DIFFICULT_CARD_TEMPLATES = {
    "高塔": "有些结构本来就是用来拆掉的。塔倒了不是惩罚，是地基再也撑不住旧剧本——它在给你腾地方。",
    "死神": "结束不是死亡，是「转化」的另一种写法。死神牌的礼物是：你终于可以放下「再撑一下」了。",
    "宝剑十": "十把剑插在背上——你已经背了很久了。这张牌不是说你还会被扎十下，是说「可以放下了」。",
    "恶魔": "恶魔牌上的枷锁，大多是自己扣上的——看见锁链的那一刻，钥匙已经在你手里。",
}

_REVERSED_GENERIC_TEMPLATE = (
    "逆位不是凶。是能量从「向外冲」转向「向内收」——这股力气此刻该用在自己身上。"
)


def _build_reframing_block(cards: list[dict]) -> str:
    """Layer 2 — build the externalization reframing block for the prompt.

    Detects reversed cards and difficulty cards (高塔 / 死神 / 宝剑十 /
    恶魔 + any reversed card) in the drawn cards, and injects a reframing
    template block (few-shot). Returns "" when no card needs reframing.
    """
    if not cards:
        return ""
    templates: list[str] = []
    reversed_present = False
    for c in cards:
        if c.get("is_reversed"):
            reversed_present = True
        name = c.get("name_zh") or ""
        for key, template in _DIFFICULT_CARD_TEMPLATES.items():
            if key in name and template not in templates:
                templates.append(template)
    if reversed_present and _REVERSED_GENERIC_TEMPLATE not in templates:
        templates.append(_REVERSED_GENERIC_TEMPLATE)
    if not templates:
        return ""
    lines = [
        "\n【外化重构 · 困境牌处理】本次牌面涉及困境牌或逆位牌，解读时必须遵守：",
        "- 禁止把牌意写成「你的命」「你的错」「你完了」；统一使用「这不是…而是…」句式。",
        "- 牌面呈现的是处境，不是审判——人不是问题，问题才是问题（叙事疗法的外化原则）。",
        "- 可参考以下重构角度（化用，不必逐字照搬）：",
    ]
    lines += [f"  · {t}" for t in templates]
    lines.append("")
    return "\n".join(lines)


# ── Layer 3: meaning completion — reflection question + 30-second action ──
# Expressive-writing mechanism (Pennebaker's insight words) + the
# Tarot-GO "one sentence + one small thing" formula. The ending uses the
# fixed structure 「给你两个问题，不用现在回答：① … ② 今晚睡前做一件
# 30 秒的小事：…」. 1–2 reflection questions, theme-picked, never
# self-blaming.

_COMMON_REFLECTION_QUESTIONS = (
    "这件事对你来说，重要的到底是什么？",
    "如果一年后的你回头看今天，会觉得今天需要什么？",
)

_THEME_REFLECTION_QUESTIONS = {
    "love": ("如果这段关系继续，你希望它是什么形状？",),
    "career": ("上一次你成功走过类似情况时，你用了自己的哪部分力量？",),
    "finance": ("你真正担心的，是钱本身，还是钱背后那份安全感？",),
}

_THIRTY_SECOND_ACTIONS = (
    "今晚睡前，把牌里最戳你的那个词写进今天的日记。",
    "把这张牌设为壁纸，当作「提醒自己」的暗号。",
    "给那个让你累的人或事写一句话，不用发出去。",
)


def _build_action_layer(theme: str | None, cards: list[dict]) -> str:
    """Layer 3 — build the ending action layer for the prompt.

    Injects the fixed ending structure with the theme-picked reflection
    question pool (1–2 questions, no self-blame questions) and the
    30-second small-action pool. When a reversed card is present, the
    wallpaper action becomes the reversed-card variant.
    """
    lines = [
        "\n【结尾行动层 · 意义完成】解读结尾使用固定结构：",
        "「给你两个问题，不用现在回答：① <反思问题> ② 今晚睡前做一件 30 秒的小事：<小事>」",
        "必须原样保留「给你两个问题，不用现在回答：」这句引导语作为结尾的固定开头。",
        "规则：",
        "- 反思问题从下方候选池中按主题挑选 1~2 个；问题只用于反思，不用于审判，"
        "禁止自责型问题（如「是不是你不够好」）。",
    ]
    questions = list(_COMMON_REFLECTION_QUESTIONS)
    if theme in _THEME_REFLECTION_QUESTIONS:
        questions += list(_THEME_REFLECTION_QUESTIONS[theme])
    for q in questions:
        lines.append(f"  · {q}")
    lines.append("- 30 秒小事从下方候选池选一个最贴合的：")
    actions = list(_THIRTY_SECOND_ACTIONS)
    if any(c.get("is_reversed") for c in cards or []):
        actions[1] = "把这张逆位牌设为壁纸，当作「提醒自己」的暗号。"
    for a in actions:
        lines.append(f"  · {a}")
    lines.append("- 该结尾结构应放在解读的最后（收尾金句之前）。")
    lines.append("")
    return "\n".join(lines)


def _build_no_question_guidance(question: str | None, user_context: str | None = None) -> str:
    """Return a state-guidance block for readings started without a question.

    - No question + user context exists → read the cards against the user's
      current life stage (history + diary), like an understanding old friend.
    - No question + no context (brand-new user) → warm welcome + invite the
      user to write a question next time.
    - A question was written → empty string (no guidance injected).

    Emotion detection (``_analyze_sentiment``) is skipped for empty
    questions — the state guidance replaces it.
    """
    if question and question.strip():
        return ""
    if user_context and user_context.strip():
        return _NO_QUESTION_GUIDANCE_HAS_CONTEXT
    return _NO_QUESTION_GUIDANCE_FRESH_USER


def _get_nudge_instruction(theme: str | None) -> str:
    """Return an instruction for the AI to end the reading with a personalized nudge."""
    if theme == "love":
        return "\n\n【收尾指引】在解读的最后，请以一句温暖的话收尾，主题围绕「爱自己，是终身浪漫的开始」，让用户感受到爱的力量。"
    elif theme == "career":
        return "\n\n【收尾指引】在解读的最后，请以一句鼓励的话收尾，主题围绕「每一个选择都是新的开始」，给用户前进的勇气。"
    elif theme == "finance":
        return "\n\n【收尾指引】在解读的最后，请以一句有智慧的话收尾，主题围绕「财富是内心丰盈的倒影」，帮助用户建立健康的财富观。"
    return "\n\n【收尾指引】在解读的最后，请以一句温暖的话收尾，告诉用户「今天也要好好照顾自己」，让用户感受到被关心。"


def _card_direction_tag(card: dict) -> str:
    return "逆位" if card.get("is_reversed") else "正位"


def _build_teaching_text(card: dict, teaching: dict | None) -> str:
    """Build a teaching-data block for one card (symbols + element)."""
    if not teaching:
        return ""
    lines: list[str] = []
    symbols = teaching.get("symbols", [])
    if symbols:
        lines.append("  牌面象征符号：")
        for s in symbols[:5]:  # cap at 5 symbols per card
            lines.append(f"    {s['symbol']}（{s['meaning']}）")
    element = teaching.get("element_association", "")
    if element:
        lines.append(f"  元素关联：{element}")
    story = teaching.get("story", "")
    if story:
        # Shorten story to ~120 chars for the prompt
        short_story = story[:120].rsplit("。", 1)[0] + "。" if "。" in story[:120] else story[:120]
        lines.append(f"  典故：{short_story}")
    if lines:
        lines.append("")  # blank line separator
    return "\n".join(lines)


def _build_cards_text(
    cards_info: list[dict],
    theme: str | None = None,
    teaching_info: dict[int, dict] | None = None,
) -> str:
    """Build a formatted block describing all drawn cards for the prompt.

    Args:
        cards_info:  Enriched card data from the DB.
        theme:       Optional theme (love / career / finance / general).
                     When set, uses theme-specific meaning fields
                     (e.g. "love_upright") instead of the generic "meaning_upright".
        teaching_info: Optional dict keyed by card_id with teaching data
                       (symbols, story, element_association, etc.).
    """
    keys = _THEME_MEANING_KEY_MAP.get(theme) if theme else None
    theme_upright = keys[0] if keys else None
    theme_reversed = keys[1] if keys else None

    lines: list[str] = []
    for c in cards_info:
        direction = _card_direction_tag(c)
        reversed_flag = c.get("is_reversed", False)

        # Prefer theme-specific meaning, fall back to generic
        if reversed_flag:
            meaning_key = theme_reversed if theme_reversed and theme_reversed in c else "meaning_reversed"
        else:
            meaning_key = theme_upright if theme_upright and theme_upright in c else "meaning_upright"

        lines.append(
            f"- {c['position_name']}：{c['name_zh']}（{direction}）"
        )
        lines.append(f"  画面描述：{c['image_description']}")
        lines.append(
            f"  含义：{c[meaning_key]}"
        )

        # Append teaching data if available
        if teaching_info:
            card_id = c.get("card_id")
            if card_id is not None:
                teaching = teaching_info.get(card_id)
                if teaching:
                    teaching_text = _build_teaching_text(c, teaching)
                    if teaching_text:
                        lines.append(teaching_text.strip())
        lines.append("")  # blank line between cards
    return "\n".join(lines)


async def generate_reading(
    spread_type: str,
    question: str | None,
    theme: str | None,
    cards_info: list[dict],
    teaching_info: dict[int, dict] | None = None,
    persona: str | None = None,
    user_context: str | None = None,
    zodiac_sign: str | None = None,
) -> str | None:
    """
    Call the DeepSeek API to produce a full tarot reading.

    Args:
        spread_type:  Spread key (e.g. 'three_card', 'celtic_cross').
        question:     Optional free-text question from the user.
        theme:        Optional theme (love / career / finance / general).
        cards_info:   Enriched card data from the DB (card + meaning fields).
        teaching_info: Optional dict keyed by card_id with teaching data
                       (symbols, story, element_association, etc.).
        persona:      Optional persona key (gentle_star / wise_moon / frank_sun).
                      When set, the AI adopts the persona's voice and style.
        user_context: Optional pre-built context block about the user's reading
                      history, built by ``_build_user_context()``.

    Returns:
        The interpretation text, or ``None`` if the API call fails
        (the caller should still save the reading).
    """
    if not settings.DEEPSEEK_API_KEY:
        return None

    # --- Resolve persona ---
    persona_key = persona or None
    persona_name = get_persona(persona_key)["name"]
    persona_prompt = get_persona_prompt_suffix(persona_key)

    # --- Build dynamic system prompt with personalization ---
    time_greeting = _get_time_greeting()
    tone_guidance = _analyze_sentiment(question)
    nudge_instruction = _get_nudge_instruction(theme)

    # Persona-aware greeting replaces the generic time greeting when persona is set
    if persona_key:
        from app.services.ai_personas import get_persona_greeting
        persona_greeting = get_persona_greeting(persona_key)
        opening = f"{time_greeting} 我是{persona_name}。{persona_greeting}"
    else:
        opening = time_greeting

    # --- Build zodiac context block ---
    zodiac_block = ""
    if zodiac_sign:
        zodiac_cn = ZODIAC_CN.get(zodiac_sign.lower(), zodiac_sign)
        zodiac_block = (
            f"\n\n【占卜者星座】{zodiac_cn}\n"
            f"请自然地结合{zodiac_cn}的性格特质进行解读——"
            f"不是星座决定论，而是作为理解用户视角的参考。"
        )

    # ── Layer 5: crisis detection (question + diary state) ──────────────
    diary_state = _extract_diary_state(user_context or "")
    crisis = _detect_crisis(question, diary_state)

    # ── Layer 4: safety red lines — always at the top of the system layer ─
    # Assembly order (system): 红线 → 危机陪伴模式
    system_blocks: list[str] = [
        opening,
        SYSTEM_PROMPT,
        persona_prompt,
        zodiac_block,
        _OUTPUT_RED_LINE,
    ]
    if crisis:
        system_blocks.append(_CRISIS_REFERRAL_BLOCK)
    dynamic_system_prompt = "\n".join(b for b in system_blocks if b and b.strip())

    # ── Layer 1: acknowledgment — skipped in crisis mode (the crisis block
    #    mandates the referral opener instead) ───────────────────────────
    acknowledgment_block = _build_acknowledgment_layer(
        question, theme, persona_key, diary_state
    ) if not crisis else ""

    # ── Layer 2: externalization reframing (difficulty / reversed cards) ─
    reframing_block = _build_reframing_block(cards_info) if not crisis else ""

    # ── Layer 3: meaning completion (reflection question + 30s action) ───
    action_block = _build_action_layer(theme, cards_info) if not crisis else ""

    # ── Cards + teaching (Layer "牌面教学") — crisis mode: cards are NOT
    #    read at all (pure companionship, no card interpretation) ─────────
    cards_text = ""
    if not crisis:
        cards_text = _build_cards_text(
            cards_info, theme=theme, teaching_info=teaching_info
        )

    # Build user context block — injected so the AI "remembers" the user
    user_context_block = user_context or ""

    # Empty-question state injection: personalise the reading even when the
    # user wrote no question (uses history + diary awareness above). When
    # context exists, the output red line additionally forbids the AI from
    # quoting/implying diary or history content in its reply.
    no_question_guidance = _build_no_question_guidance(question, user_context_block)
    output_red_line = _OUTPUT_RED_LINE if user_context_block.strip() else ""

    now_str = datetime.datetime.now().strftime("%H:%M")
    if crisis:
        # Crisis mode: minimal prompt — companionship only, no cards, no
        # teaching, no reframing, no action layer, no [ACTION] requirement.
        user_prompt = "\n".join(
            p for p in (
                f"现在是{now_str}，{opening}",
                user_context_block,
                output_red_line,
                f"用户问题：{question or '未指定具体问题'}",
                "\n请遵循系统提示中的【危机陪伴模式·强制】要求："
                "先表达关怀与转介信息，全程纯陪伴，不解读牌面。",
            ) if p and p.strip()
        )
    else:
        # ── Assembly order (per five-layer spec) ────────────────────────
        # 认领层 → 牌面教学(抽取的牌) → 情感语气 → 外化重构 →
        # 用户上下文(历史+日记) → 无问题引导 → (输出红线) →
        # 行动层 → 收尾金句 → [ACTION]结构化要求(应用解析用)
        user_prompt = "\n".join(
            p for p in (
                f"现在是{now_str}，{opening}",
                acknowledgment_block,
                f"请为用户进行塔罗解读。\n\n"
                f"牌阵类型: {spread_type}\n"
                f"用户问题: {question or '未指定具体问题'}\n"
                f"解读主题: {theme or '综合运势'}\n\n"
                f"抽取的牌:\n{cards_text}\n\n",
                tone_guidance,
                reframing_block,
                user_context_block,
                no_question_guidance,
                output_red_line,
                f"【画面解读指引 - 增强版】\n"
                f"你的解读必须做到以下几点，这是你与普通AI塔罗的核心区别：\n\n"
                f"1. **每张牌至少引用2个具体的画面元素**：\n"
                f"   - 不只是说“画面中有个小孩”，而是“圣杯六的画面中，一个年幼的孩子踮起脚尖，将装满白色百合的圣杯递给另一个更小的孩子——注意他们身后，远处的石阶上站着一个成人的身影。”\n"
                f"   - 引用颜色：“女皇身后金黄麦田的暖色调”而非“麦田”二字\n"
                f"   - 引用动作：“他踮起脚尖递出圣杯”而非简单说“一个小孩”\n\n"
                f"2. **将画面元素与用户的具体问题关联**：\n"
                f"   - 用户问感情复合 → “他踮起脚尖的姿态，像你在这段关系中的付出——总是你在努力够到什么”\n"
                f"   - 用户问事业 → “远处石阶上的成人身影代表着你看不到的成长路径”\n\n"
                f"3. **正位与逆位的视觉差异必须反映在解读中**：\n"
                f"   - 逆位时：“当宝剑五倒过来，画面中原本落在地上的剑变成了悬在头顶的威胁”\n\n"
                f"4. **禁止的行为**：\n"
                f"   - 不要说“牌面显示/牌面暗示/牌面告诉我/根据塔罗传统”等套话\n"
                f"   - 不要只写一通用感情鸡汤\n"
                f"   - 不要回避用户问题的核心\n\n"
                f"你的每一句解读，都应该让用户觉得你真的在看着这张牌说话。\n\n"
                f"请提供完整的解读，包括：\n"
                f"1. 牌阵总览（整体能量和主题）\n"
                f"2. 逐牌解读（每张牌在对应位置的含义，请引用画面细节）\n"
                f"3. 综合解读（将所有牌串联成完整故事）\n"
                f"4. 建议与指引（用户可以在现实层面采取的行动）\n\n",
                action_block,
                nudge_instruction,
                f"【行动建议要求】\n"
                f"在结尾行动层（两个问题与30秒小事）和收尾金句之后，另起一段，给出 3 条具体行动建议。\n"
                f"要求：\n"
                f"- 每条建议必须是用户今天或本周可以执行的具体行动\n"
                f"- 每条建议写成一个完整的句子，语气鼓励，使用第二人称「你」\n"
                f"- 根据建议的内容主题，将每条建议归类为 love、career 或 general 中的一个\n"
                f"- 格式：每行一条，使用 [ACTION]建议内容[/ACTION]\n"
                f"  例如：[ACTION]本周主动约一位朋友喝咖啡，聊聊最近的感受[/ACTION]\n"
                f"- 必须输出 3 条，不要多也不要少",
            ) if p and p.strip()
        )

    client = _get_client()

    max_attempts = 3
    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = await client.chat.completions.create(
                model=settings.DEEPSEEK_MODEL,
                max_tokens=settings.AI_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": dynamic_system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=120.0,
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content
            logger.warning("generate_reading attempt %d returned empty content", attempt)
        except Exception as exc:
            last_exception = exc
            logger.warning(
                "generate_reading attempt %d/%d failed: %s",
                attempt, max_attempts, exc,
            )
        if attempt < max_attempts:
            import asyncio
            await asyncio.sleep(1.0 * attempt)  # linear backoff

    logger.exception("All %d attempts to generate tarot reading failed", max_attempts)
    return None


async def stream_chat_response(
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    """Stream AI response tokens for follow-up chat.

    Args:
        messages: List of message dicts with 'role' and 'content' keys,
                 including the system prompt and full conversation history.

    Yields:
        Content tokens from the AI response, one at a time.
    """
    if not settings.DEEPSEEK_API_KEY:
        return

    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=settings.AI_MAX_TOKENS,
            messages=messages,
            stream=True,
            timeout=60.0,
        )
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as exc:
        logger.exception("stream_chat_response failed: %s", exc)
        raise


async def generate_reflection_question(
    question: str | None,
    first_card_name: str,
    interpretation: str | None,
) -> str:
    """Generate a reflection question to guide the user to journaling.

    Uses the first card drawn and a summary of the interpretation to
    produce a warm, concise reflection prompt (60 chars max).

    Args:
        question:        The user's original question, or None.
        first_card_name: Chinese name of the first drawn card (e.g. "星星").
        interpretation:  The full AI interpretation text, or None.

    Returns:
        A reflection question string, or a fallback message on failure.
    """
    if not settings.DEEPSEEK_API_KEY:
        return f"「{first_card_name}」在今天的生活中想告诉你什么？"

    client = _get_client()
    try:
        resp = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=120,
            messages=[{
                "role": "system",
                "content": (
                    "你是一位温暖的塔罗伙伴。用户刚完成了一次塔罗解读，"
                    "请生成一个引人深思的反思问题，引导用户将解读智慧应用到生活中。"
                    "60字以内，温暖而具体，像朋友在轻声提醒。只返回问题本身，不要加引号或前缀。"
                ),
            }, {
                "role": "user",
                "content": (
                    f"用户问题: {question or '未指定'}\n"
                    f"关键卡牌: {first_card_name}\n"
                    f"解读摘要: {(interpretation or '')[:300]}"
                ),
            }],
            timeout=20.0,
        )
        raw = resp.choices[0].message.content.strip()
        # Clean up quotes if the AI wrapped the question
        raw = raw.strip('"').strip("'").strip('「').strip('」').strip()
        if len(raw) > 60:
            raw = raw[:57] + "..."
        return raw or f"「{first_card_name}」的启示对你意味着什么？"
    except Exception:
        logger.exception("generate_reflection_question failed")
        return f"「{first_card_name}」的启示对你意味着什么？"


async def generate_zodiac_match(sign1: str, sign2: str, card_name: str | None = None) -> str | None:
    """
    Generate a brief, fun "relationship tarot card" blurb for a zodiac pairing.

    Tone rules (strict):
    - Playful, warm, chat-like — the card is a fun lens on the pairing,
      never a verdict on two people.
    - Forbidden: "命运 / 天生一对 / 灵魂伴侣 / 命中注定" style language.
    - No anxiety, no judgment of either sign.
    - Output is one short paragraph (about 60–100 Chinese chars).

    Args:
        sign1:      Zodiac key of the first sign (e.g. "aries").
        sign2:      Zodiac key of the second sign (e.g. "taurus").
        card_name:  Chinese name of the randomly drawn "relationship card".

    Returns:
        The blurb text, or ``None`` if the API call fails
        (caller falls back to a local template).
    """
    if not settings.DEEPSEEK_API_KEY:
        return None

    cn1 = ZODIAC_CN.get(sign1.lower(), sign1)
    cn2 = ZODIAC_CN.get(sign2.lower(), sign2)

    client = _get_client()
    try:
        resp = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=200,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一位轻松的塔罗伙伴。用户选了两个星座，想看看属于这对组合的"
                        "「塔罗关系牌」。请用轻松、有趣、温暖的口吻，写一段 60~100 字的简短解读。\n\n"
                        "风格要求：\n"
                        "- 把这对星座组合比作一段有趣的关系小剧本，比如「一个负责点火，一个负责熄火」\n"
                        "- 提到抽到的塔罗牌，把它形容为这段关系的「主题曲」\n"
                        "- 语气像朋友聊天，带一点幽默，不故弄玄虚\n\n"
                        "禁忌：\n"
                        "- 绝对不要使用「命运」「天生一对」「灵魂伴侣」「命中注定」「完美契合」等绝对化语言\n"
                        "- 不要评判星座优劣，不要制造焦虑\n"
                        "- 不要超过 100 字，不要使用 markdown 格式\n"
                        "- 只返回解读正文，不要加标题、引号或前缀"
                    ),
                },
                {
                    "role": "user",
                    "content": f"星座组合：{cn1} + {cn2}\n抽到的塔罗关系牌：{card_name or '恋人'}",
                },
            ],
            timeout=30.0,
        )
        raw = (resp.choices[0].message.content or "").strip().strip('"').strip("'")
        return raw or None
    except Exception as exc:
        logger.warning("generate_zodiac_match failed for %s+%s: %s", sign1, sign2, exc)
        return None
