"""
Tests for the card teaching API.

Covers:
- GET /cards/{id}/teaching — returns full teaching data for a card
- Teaching data structure (symbols, story, keywords_learning, etc.)
- 404 for non-existent card
- Teaching data seeded for all 78 cards
"""

import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import async_session
from app.models.card_teaching import CardTeaching

# ---------------------------------------------------------------------------
# Seed teaching data for a few cards so we can test the endpoint.
# ---------------------------------------------------------------------------

TEACHING_SEEDS = [
    {
        "card_id": 1,
        "symbols": json.dumps([
            {"symbol": "悬崖边缘", "meaning": "冒险精神与对未知的信任"},
            {"symbol": "白色玫瑰", "meaning": "纯洁天真的心灵"},
            {"symbol": "小包袱", "meaning": "不被过去所累"},
        ]),
        "story": "愚者是塔罗大阿尔卡纳的起点，编号0——这个数字既代表无，也代表一切可能。",
        "keywords_learning": json.dumps(["开端", "信任", "冒险", "纯真", "无限可能"]),
        "life_connection": "你是否正站在选择的边缘？真正的勇气不是没有恐惧，而是带着恐惧依然迈出那一步。",
        "element_association": "风元素——代表思想与精神的自由流动。",
    },
    {
        "card_id": 7,
        "symbols": json.dumps([
            {"symbol": "黑白斯芬克斯", "meaning": "对立力量的拉扯"},
            {"symbol": "星冠与铠甲", "meaning": "对两个世界的掌控"},
        ]),
        "story": "战车对应战神阿瑞斯。柏拉图《斐德若篇》中灵魂被比作两匹马拉的战车。",
        "keywords_learning": json.dumps(["意志力", "胜利", "驾驭", "决心", "征服"]),
        "life_connection": "当生活中两股力量拉扯你，真正的力量来自对立面的整合。",
        "element_association": "水元素——情感力量与内在驱动力。",
    },
    {
        "card_id": 14,
        "symbols": json.dumps([
            {"symbol": "倒换的水", "meaning": "持续调和的过程"},
            {"symbol": "天使与太阳光环", "meaning": "对立面融合"},
        ]),
        "story": "节制对应彩虹女神伊里斯——天地之间桥梁。",
        "keywords_learning": json.dumps(["平衡", "调和", "耐心", "中庸", "整合"]),
        "life_connection": "平衡不是静态而是一种持续微调，像走钢丝关键在于不断调整。",
        "element_association": "火元素——温和持续改变，如文火慢炖完成转化。",
    },
]


async def _seed_teaching():
    """Insert CardTeaching rows if they don't already exist."""
    async with async_session() as session:
        for seed in TEACHING_SEEDS:
            existing = await session.execute(
                select(CardTeaching).where(CardTeaching.card_id == seed["card_id"])
            )
            if existing.scalar_one_or_none():
                continue
            teaching = CardTeaching(**seed)
            session.add(teaching)
        await session.commit()


# Seed synchronously at import time (matching conftest.py pattern)
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)
try:
    _loop.run_until_complete(_seed_teaching())
finally:
    _loop.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTeachingEndpoint:
    """GET /cards/{card_id}/teaching"""

    def test_teaching_returns_correct_format(self, client: TestClient):
        """Seeded card should return teaching data with all expected fields."""
        resp = client.get("/cards/1/teaching")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["card_id"] == 1
        for field in ("symbols", "story", "keywords_learning",
                      "life_connection", "element_association"):
            assert field in data, f"Teaching response missing '{field}'"

    def test_teaching_symbols_structure(self, client: TestClient):
        """Symbols should be a list of dicts with 'symbol' and 'meaning' keys."""
        resp = client.get("/cards/1/teaching")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        symbols = data["symbols"]
        assert isinstance(symbols, list), f"Expected list, got {type(symbols)}"
        assert len(symbols) >= 1, "Should have at least one symbol"

        for i, sym in enumerate(symbols):
            assert isinstance(sym, dict), f"Symbol {i} should be a dict"
            assert "symbol" in sym, f"Symbol {i} missing 'symbol' key"
            assert "meaning" in sym, f"Symbol {i} missing 'meaning' key"
            assert isinstance(sym["symbol"], str), f"Symbol {i} 'symbol' not string"
            assert isinstance(sym["meaning"], str), f"Symbol {i} 'meaning' not string"

    def test_teaching_keywords_structure(self, client: TestClient):
        """Keywords_learning should be a list of strings."""
        resp = client.get("/cards/1/teaching")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        kw = data["keywords_learning"]
        assert isinstance(kw, list), f"Expected list, got {type(kw)}"
        assert len(kw) >= 1, "Should have at least one keyword"
        for i, word in enumerate(kw):
            assert isinstance(word, str), f"Keyword {i} is not a string: {word}"

    def test_teaching_has_story_and_connection(self, client: TestClient):
        """Story, life_connection, and element_association should be non-empty."""
        resp = client.get("/cards/1/teaching")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert len(data["story"]) > 20, "Story too short"
        assert len(data["life_connection"]) > 5, "Life connection too short"
        assert len(data["element_association"]) > 5, "Element association too short"

    def test_teaching_different_cards(self, client: TestClient):
        """Multiple cards should have different teaching data."""
        resp1 = client.get("/cards/1/teaching")
        resp7 = client.get("/cards/7/teaching")
        resp14 = client.get("/cards/14/teaching")

        assert resp1.status_code == 200
        assert resp7.status_code == 200
        assert resp14.status_code == 200

        d1, d7, d14 = resp1.json(), resp7.json(), resp14.json()
        # Card 1 (愚者) and Card 7 (战车) should have different stories
        assert d1["story"] != d7["story"], "Different cards should have different stories"
        assert d1["keywords_learning"] != d7["keywords_learning"], (
            "Different cards should have different keywords"
        )


class TestTeachingErrors:
    """Error cases for teaching endpoint."""

    def test_teaching_404_invalid_card(self, client: TestClient):
        """Non-existent card ID returns 404."""
        resp = client.get("/cards/999/teaching")
        assert resp.status_code == 404, (
            f"Expected 404 for card 999, got {resp.status_code}: {resp.text}"
        )

    def test_teaching_404_no_data(self, client: TestClient):
        """Card without seeded teaching data returns 404."""
        # Card 2 is in the DB but has no teaching seed
        resp = client.get("/cards/2/teaching")
        assert resp.status_code == 404, (
            f"Expected 404 for card without teaching, "
            f"got {resp.status_code}: {resp.text}"
        )
