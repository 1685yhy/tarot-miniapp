"""
Tarot AI interpretation engine.

Uses the Anthropic (Claude) API to generate thoughtful tarot readings
based on the cards drawn and the user's question.
"""

from anthropic import AsyncAnthropic

from app.config import settings

# -------------------------------------------------------------------
# Client – lazily evaluated at module level; if ANTHROPIC_API_KEY is
# empty the first call will raise, which is caught by the endpoint.
# -------------------------------------------------------------------
_anthropic_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


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


def _build_cards_text(cards_info: list[dict]) -> str:
    """Build a formatted block describing all drawn cards for the prompt."""
    lines: list[str] = []
    for c in cards_info:
        direction = _card_direction_tag(c)
        reversed_flag = c.get("is_reversed", False)

        # Pick theme-specific meaning if available, otherwise fall back to general
        upright_key = "meaning_upright"
        reversed_key = "meaning_reversed"

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
    Call the Claude API to produce a full tarot reading.

    Args:
        spread_type:  Spread key (e.g. 'three_card', 'celtic_cross').
        question:     Optional free-text question from the user.
        theme:        Optional theme (love / career / finance / general).
        cards_info:   Enriched card data from the DB (card + meaning fields).

    Returns:
        The interpretation text, or ``None`` if the API call fails
        (the caller should still save the reading).
    """
    if not settings.ANTHROPIC_API_KEY:
        return None

    cards_text = _build_cards_text(cards_info)

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
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    except Exception:
        # Logging would go here in production — for now return None
        # so the reading is still saved without interpretation.
        return None
