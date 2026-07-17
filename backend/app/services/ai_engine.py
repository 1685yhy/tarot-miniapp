"""
Tarot AI interpretation engine.

Uses DeepSeek API (OpenAI-compatible) to generate thoughtful tarot
readings based on the cards drawn and the user's question.
"""

import datetime
import logging

from openai import AsyncOpenAI

from app.config import settings

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


def _build_cards_text(cards_info: list[dict], theme: str | None = None) -> str:
    """Build a formatted block describing all drawn cards for the prompt.

    Args:
        cards_info:  Enriched card data from the DB.
        theme:       Optional theme (love / career / finance / general).
                     When set, uses theme-specific meaning fields
                     (e.g. "love_upright") instead of the generic "meaning_upright".
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
            f"位置{c['position']} - {c['position_name']}: "
            f"{c['name_zh']}({c['name_en']}) [{direction}]"
        )
        lines.append(f"  牌面: {c['image_description'][:120]}...")
        lines.append(
            f"  含义: {c[meaning_key][:200]}..."
        )
        lines.append("")  # blank line between cards for readability
    return "\n".join(lines)


async def generate_reading(
    spread_type: str,
    question: str | None,
    theme: str | None,
    cards_info: list[dict],
) -> str | None:
    """
    Call the DeepSeek API to produce a full tarot reading.

    Args:
        spread_type:  Spread key (e.g. 'three_card', 'celtic_cross').
        question:     Optional free-text question from the user.
        theme:        Optional theme (love / career / finance / general).
        cards_info:   Enriched card data from the DB (card + meaning fields).

    Returns:
        The interpretation text, or ``None`` if the API call fails
        (the caller should still save the reading).
    """
    if not settings.DEEPSEEK_API_KEY:
        return None

    # --- Build dynamic system prompt with personalization ---
    time_greeting = _get_time_greeting()
    tone_guidance = _analyze_sentiment(question)
    nudge_instruction = _get_nudge_instruction(theme)

    dynamic_system_prompt = (
        f"{time_greeting}\n\n"
        f"{SYSTEM_PROMPT}"
        f"{tone_guidance}"
        f"{nudge_instruction}"
    )

    cards_text = _build_cards_text(cards_info, theme=theme)

    user_prompt = (
        f"现在是{datetime.datetime.now().strftime('%H:%M')}，{time_greeting}\n\n"
        f"请为用户进行塔罗解读。\n\n"
        f"牌阵类型: {spread_type}\n"
        f"用户问题: {question or '未指定具体问题'}\n"
        f"解读主题: {theme or '综合运势'}\n\n"
        f"抽取的牌:\n{cards_text}\n\n"
        f"请提供完整的解读，包括：\n"
        f"1. 牌阵总览（整体能量和主题）\n"
        f"2. 逐牌解读（每张牌在对应位置的含义）\n"
        f"3. 综合解读（将所有牌串联成完整故事）\n"
        f"4. 建议与指引（用户可以在现实层面采取的行动）"
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
