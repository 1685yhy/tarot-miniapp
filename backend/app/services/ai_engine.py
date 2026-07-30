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

    dynamic_system_prompt = (
        f"{opening}\n\n"
        f"{SYSTEM_PROMPT}"
        f"{persona_prompt}"
        f"{zodiac_block}"
        f"{tone_guidance}"
        f"{nudge_instruction}"
    )

    cards_text = _build_cards_text(cards_info, theme=theme, teaching_info=teaching_info)

    # Build user context block — injected so the AI "remembers" the user
    user_context_block = user_context or ""

    user_prompt = (
        f"现在是{datetime.datetime.now().strftime('%H:%M')}，{opening}\n\n"
        f"{user_context_block}"
        f"请为用户进行塔罗解读。\n\n"
        f"牌阵类型: {spread_type}\n"
        f"用户问题: {question or '未指定具体问题'}\n"
        f"解读主题: {theme or '综合运势'}\n\n"
        f"抽取的牌:\n{cards_text}\n\n"
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
        f"   - 不要说“牌面显示/牌面暗示/根据塔罗传统”等套话\n"
        f"   - 不要只写一通用感情鸡汤\n"
        f"   - 不要回避用户问题的核心\n\n"
        f"你的每一句解读，都应该让用户觉得你真的在看着这张牌说话。\n\n"
        f"请提供完整的解读，包括：\n"
        f"1. 牌阵总览（整体能量和主题）\n"
        f"2. 逐牌解读（每张牌在对应位置的含义，请引用画面细节）\n"
        f"3. 综合解读（将所有牌串联成完整故事）\n"
        f"4. 建议与指引（用户可以在现实层面采取的行动）\n\n"
        f"【行动建议要求】\n"
        f"在解读的最后，请根据本次解读的内容给出 3 条具体行动建议。\n"
        f"要求：\n"
        f"- 每条建议必须是用户今天或本周可以执行的具体行动\n"
        f"- 每条建议写成一个完整的句子，语气鼓励，使用第二人称「你」\n"
        f"- 根据建议的内容主题，将每条建议归类为 love、career 或 general 中的一个\n"
        f"- 格式：每行一条，使用 [ACTION]建议内容[/ACTION]\n"
        f"  例如：[ACTION]本周主动约一位朋友喝咖啡，聊聊最近的感受[/ACTION]\n"
        f"- 必须输出 3 条，不要多也不要少"
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
