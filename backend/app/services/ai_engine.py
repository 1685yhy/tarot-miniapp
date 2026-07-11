"""
Tarot AI interpretation engine.

Uses DeepSeek API (OpenAI-compatible) to generate thoughtful tarot
readings based on the cards drawn and the user's question.
"""

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
    upright_key = f"{keys[0]}" if keys else "meaning_upright"
    reversed_key = f"{keys[1]}" if keys else "meaning_reversed"

    lines: list[str] = []
    for c in cards_info:
        direction = _card_direction_tag(c)
        reversed_flag = c.get("is_reversed", False)

        lines.append(
            f"位置{c['position']} - {c['position_name']}: "
            f"{c['name_zh']}({c['name_en']}) [{direction}]"
        )
        lines.append(f"  牌面: {c['image_description'][:120]}...")
        lines.append(
            f"  含义: {c[reversed_key if reversed_flag else upright_key][:200]}..."
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

    cards_text = _build_cards_text(cards_info, theme=theme)

    user_prompt = (
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
    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=settings.AI_MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            timeout=60.0,
        )
        return response.choices[0].message.content
    except Exception:
        logger.exception("Failed to generate tarot reading via DeepSeek")
        return None
