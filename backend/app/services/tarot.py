"""
Tarot card drawing service.

Provides draw_cards() which randomly selects cards for any of 11 spread types.
Each card has a 30% chance of being reversed.
"""

import random
from typing import Optional


SPREAD_CONFIGS: dict[str, dict] = {
    "daily": {"count": 1, "positions": ["今日运势"]},
    "three_card": {"count": 3, "positions": ["过去", "现在", "未来"]},
    "triangle": {
        "count": 4,
        "positions": ["你的状态", "对方状态", "关系现状", "未来发展"],
    },
    "career": {
        "count": 5,
        "positions": ["当前位置", "挑战", "建议", "机遇", "可能结果"],
    },
    "finance": {
        "count": 4,
        "positions": ["财务现状", "收入来源", "支出模式", "财务建议"],
    },
    "decision": {
        "count": 5,
        "positions": ["现状", "选择A", "选择A结果", "选择B", "选择B结果"],
    },
    "celtic_cross": {
        "count": 10,
        "positions": [
            "核心问题",
            "阻碍",
            "过去基础",
            "近期未来",
            "显意识目标",
            "潜意识",
            "建议",
            "环境影响",
            "希望与恐惧",
            "最终结果",
        ],
    },
    "life_cross": {
        "count": 5,
        "positions": ["你(现在)", "过去", "未来", "助力", "阻力"],
    },
    "horseshoe": {
        "count": 7,
        "positions": [
            "过去",
            "现在",
            "隐藏影响",
            "障碍",
            "环境",
            "建议",
            "结果",
        ],
    },
    "year_ahead": {
        "count": 13,
        "positions": [
            "年度主题",
            "一月",
            "二月",
            "三月",
            "四月",
            "五月",
            "六月",
            "七月",
            "八月",
            "九月",
            "十月",
            "十一月",
            "十二月",
        ],
    },
    "relationship": {
        "count": 7,
        "positions": [
            "你",
            "对方",
            "你们的连接",
            "优势",
            "挑战",
            "对方视角",
            "建议",
        ],
    },
}

# Tarot deck has 78 cards (IDs 1-78)
TOTAL_CARDS = 78
REVERSED_PROBABILITY = 0.3


def draw_cards(
    spread_type: str,
    exclude_card_ids: Optional[list[int]] = None,
) -> list[dict]:
    """
    Draw cards for the given spread type.

    Args:
        spread_type: Name of the spread (e.g. 'daily', 'three_card', 'celtic_cross').
        exclude_card_ids: Optional list of card IDs to exclude from drawing
                           (used if a reading is re-drawn).

    Returns:
        List of dicts, each with keys:
            card_id (int)
            position (int)           — 1-based position in the spread
            position_name (str)      — human-readable position label
            is_reversed (bool)       — 30% chance True
    """
    config = SPREAD_CONFIGS.get(
        spread_type, SPREAD_CONFIGS["three_card"]
    )
    count = config["count"]
    positions = config["positions"]

    # Build pool of available card IDs (1..78 minus exclusions)
    available = [
        i for i in range(1, TOTAL_CARDS + 1)
        if i not in (exclude_card_ids or [])
    ]

    # If we somehow need more cards than available, use what's left
    actual_count = min(count, len(available))
    if actual_count < count:
        # Pad with random re-draws if we're extremely short
        # (practically impossible with 78 cards, but be defensive)
        extra_needed = count - actual_count
        extra = random.choices(
            [i for i in range(1, TOTAL_CARDS + 1)],
            k=extra_needed,
        )
        selected = available + extra
    else:
        selected = random.sample(available, actual_count)

    return [
        {
            "card_id": card_id,
            "position": i + 1,
            "position_name": positions[i] if i < len(positions) else f"位置{i + 1}",
            "is_reversed": random.random() < REVERSED_PROBABILITY,
        }
        for i, card_id in enumerate(selected)
    ]


def get_available_spread_types() -> list[str]:
    """Return the list of all supported spread type keys."""
    return list(SPREAD_CONFIGS.keys())
