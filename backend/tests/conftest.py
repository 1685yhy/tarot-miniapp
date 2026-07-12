"""
Test configuration and fixtures for Tarot mini-program API.

Overrides DATABASE_URL to use an isolated SQLite file so tests don't
pollute the real development database.  Seeds 78 tarot cards so the
card and reading endpoints have data to work with.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

# ── Must set environment variables before any app imports ──────────────
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./.pytest_tarot.db"
os.environ["DEEPSEEK_API_KEY"] = ""  # Disable AI calls in tests

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Remove old test database files ─────────────────────────────────────
for _f in (".pytest_tarot.db", ".pytest_tarot.db-journal"):
    try:
        os.remove(_f)
    except FileNotFoundError:
        pass

# ── App imports (must come after env overrides) ────────────────────────
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db.database import Base, engine, async_session
from app.models.card import TarotCard

# ---------------------------------------------------------------------------
# Test database initialisation
# ---------------------------------------------------------------------------

SUIT_NAMES = ("wands", "cups", "swords", "pentacles")
SUIT_ELEMENTS = {"wands": "火", "cups": "水", "swords": "风", "pentacles": "土"}
MAJOR_COUNT = 22


def _make_card(i: int) -> TarotCard:
    """Create a test TarotCard with the given ID (1-78)."""
    if 1 <= i <= MAJOR_COUNT:
        arcana = "major"
        suit = None
        element = ""
    else:
        arcana = "minor"
        idx = i - MAJOR_COUNT - 1
        suit = SUIT_NAMES[idx // 14] if idx // 14 < 4 else "wands"
        element = SUIT_ELEMENTS.get(suit, "")
    return TarotCard(
        id=i,
        name_zh=f"卡牌{i}",
        name_en=f"Card {i}",
        card_number=i - 1,
        arcana=arcana,
        suit=suit,
        element=element,
        image_description=f"测试描述{i}",
        keywords_upright=f"关键词{i}",
        keywords_reversed=f"逆位关键词{i}",
        meaning_upright=f"正位含义{i}",
        meaning_reversed=f"逆位含义{i}",
        love_upright=f"感情正位{i}",
        love_reversed=f"感情逆位{i}",
        career_upright=f"事业正位{i}",
        career_reversed=f"事业逆位{i}",
        finance_upright=f"财运正位{i}",
        finance_reversed=f"财运逆位{i}",
        health_upright=f"健康正位{i}",
        health_reversed=f"健康逆位{i}",
    )


async def _init_db() -> None:
    """Create all tables and seed 78 tarot cards."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        result = await session.execute(select(TarotCard).limit(1))
        if result.scalar_one_or_none():
            return  # already seeded
        cards = [_make_card(i) for i in range(1, 79)]
        session.add_all(cards)
        await session.commit()


# Use a fresh event loop so we don't conflict with pytest-asyncio's loop
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)
try:
    _loop.run_until_complete(_init_db())
finally:
    _loop.close()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """TestClient with the real lifespan (tables are already created)."""
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_db() -> TestClient:
    """TestClient *without* database — lifespan is replaced with a no-op."""
    app.dependency_overrides.clear()

    @asynccontextmanager
    async def noop(_app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop
    with TestClient(app) as c:
        yield c
    app.router.lifespan_context = original_lifespan
