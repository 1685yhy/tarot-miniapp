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
os.environ["WECHAT_MSG_CHECK_ENABLED"] = "false"  # No real WeChat msgSecCheck calls
os.environ["REDIS_URL"] = ""  # Force the in-process rate-limit store (deterministic)
# The whole suite shares one dev-login user — raise the per-user limit so
# the in-process rate limiter can't 429 late tests (limits stay 60/min in prod).
os.environ["RATE_LIMIT_MAX_REQUESTS"] = "100000"

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
from sqlalchemy import select, text

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


# ---------------------------------------------------------------------------
# 测试隔离（根因修复 flaky）：每测试前清空全部业务表，保留 tarot_cards 种子
# ---------------------------------------------------------------------------
# 此前全套件共享一个 .pytest_tarot.db 文件，只在 conftest 导入时删一次。
# 于是任何测试写入的数据（readings/diaries/checkins/wishes/共鸣…）都会
# 残留到后续测试，导致「空状态 / 精确计数 / 同日幂等」类断言偶发失败——
# 例如 test_deep_reading 的 API 用例给共享 dev 用户写入 readings 后，
# test_fortune_trend_empty_state 就拿到 total_readings=3（全量运行时）。
# 修复：每个测试开始前 DELETE 全部业务表（78 张 tarot_cards 种子保留），
# 让每个测试都从与「单独跑该文件」一致的干净状态开始。
#
# 实现说明：重置必须走应用自己的 async 连接池（async_session），而不是
# 另开一个同步 sqlite3 连接。项目 DB 位于 WSL /mnt/e（drvfs/9p 文件系统），
# WAL 模式下并存的第二个连接生态会与 aiosqlite 连接池竞态出偶发
# "sqlite3.OperationalError: disk I/O error"（实测：同步重置方案在全量
# 运行中导致 8 处 setup error，全部发生在应用新连接执行 PRAGMA
# journal_mode=WAL 时）。走同一连接池则与套件既有的 asyncio.run() 模式
# （345 处）一致，无额外文件级竞争。
#
# 注意：test_teaching.py / test_academy.py 原本在 import 期播种的教学
# 数据会被本 fixture 清掉，这两处已改为各自的 autouse fixture 每测试重种。
_TABLE_EXCLUDED_FROM_RESET = "tarot_cards"  # 78 张卡牌种子（conftest 导入期播种）


@pytest.fixture(autouse=True)
def _reset_db_before_each_test():
    """每测试前清空除 tarot_cards 外的所有表，实现测试间数据隔离。"""

    async def _reset() -> None:
        async with async_session() as session:
            for name in Base.metadata.tables.keys():
                if name == _TABLE_EXCLUDED_FROM_RESET:
                    continue
                await session.execute(text(f'DELETE FROM "{name}"'))
            await session.commit()

    asyncio.run(_reset())
    yield
