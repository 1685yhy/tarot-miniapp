"""
星友圈（SDD P2 · T8-1）测试：star_resonances 共鸣表 + 星名脱敏 + 隐身开关 + /resonance/alias

覆盖（task-1-brief）：
- ALIAS_POOL：长度 == 40、词条互不相同、词长 ≤8 字、全部自然意象
  （compliance 双表扫描零命中：MEET_BLACKLIST + AI_OUTPUT_BLACKLIST）
- generate_alias：确定性（同 user 同日两次恒同）；不同 user 同日抽样非全同
- get_or_create_alias：首次生成并落库 users.star_alias；已有值则原样返回
  （不重复生成，幂等）
- GET /resonance/alias：未登录 401；首次调用生成落库、二次调用同值不重复生成
- 迁移链：临时 SQLite upgrade head → star_resonances 表存在且
  uq_from_to_date 唯一约束生效（同对同日期重复插入报错）→ users 含
  resonance_visible（server_default '1'）/star_alias 列；downgrade base 干净
"""

import asyncio
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import async_session
from app.models.user import User
from app.services.compliance import (
    AI_OUTPUT_BLACKLIST,
    MEET_BLACKLIST,
    find_forbidden,
)
from app.services.resonance import ALIAS_POOL, generate_alias, get_or_create_alias
from app.services.star_words import beijing_today
from app.utils.auth import create_token

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ── helpers ─────────────────────────────────────────────────────────────


def _new_user(openid: str) -> tuple[str, dict[str, str]]:
    """创建隔离测试用户，返回 (user_id, auth_headers)。"""

    async def _go() -> tuple[str, str]:
        async with async_session() as session:
            user = User(openid=openid, nickname="星友圈测试")
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return user.id, token

    uid, token = asyncio.run(_go())
    return uid, {"Authorization": f"Bearer {token}"}


def _read_user(user_id: str) -> dict:
    """独立会话读用户（避开 API 会话 identity map）。"""

    async def _go() -> dict:
        async with async_session() as session:
            user = await session.get(User, user_id)
            return {"star_alias": user.star_alias, "resonance_visible": user.resonance_visible}

    return asyncio.run(_go())


# ── ALIAS_POOL：40 词定稿 + 合规扫描 ────────────────────────────────────


def test_alias_pool_length_and_compliance():
    """ALIAS_POOL：40 个自然意象词，全部过 compliance 双表扫描、词长 ≤8 字。"""
    assert len(ALIAS_POOL) == 40, f"星名词库应恰 40 词，实际 {len(ALIAS_POOL)}"
    assert len(set(ALIAS_POOL)) == 40, "星名词库不应有重复词"
    for word in ALIAS_POOL:
        assert len(word) >= 1 and len(word) <= 8, f"词长应 1~8 字: {word}"
        assert find_forbidden(word, MEET_BLACKLIST) == [], f"MEET_BLACKLIST 命中: {word}"
        assert find_forbidden(word, AI_OUTPUT_BLACKLIST) == [], f"AI_OUTPUT_BLACKLIST 命中: {word}"


# ── generate_alias：确定性 ──────────────────────────────────────────────


def test_generate_alias_deterministic_same_user_same_day():
    """同 user 同日两次生成恒同（确定性公式）。"""
    uid = "u-" + "a" * 36
    day = date(2026, 8, 11)
    assert generate_alias(uid, day) == generate_alias(uid, day)
    alias = generate_alias(uid, day)
    assert alias.startswith("星星·")
    assert alias == f"星星·{ALIAS_POOL[(sum(ord(c) for c in uid) + day.toordinal()) % 40]}"


def test_generate_alias_varied_across_users():
    """不同 user 同日抽样非全同（40 词池轮换可测）。"""
    day = date(2026, 8, 11)
    aliases = {generate_alias(f"user-sample-{i:02d}", day) for i in range(30)}
    assert len(aliases) > 1, "30 个不同用户同日不应全部同词（词库应产生差异）"
    assert all(a.startswith("星星·") for a in aliases)


# ── get_or_create_alias：幂等落库 ───────────────────────────────────────


def test_get_or_create_alias_generates_and_persists():
    """首次调用：生成并落库 users.star_alias；二次调用同值不重复生成。"""

    async def _go() -> None:
        async with async_session() as session:
            user = User(openid="openid_resonance_svc1", nickname="服务测试")
            session.add(user)
            await session.flush()

            first = await get_or_create_alias(session, user)
            assert first == generate_alias(user.id, beijing_today())
            assert first.startswith("星星·")

            second = await get_or_create_alias(session, user)
            assert second == first, "幂等：二次调用应返回同一星名"

            await session.commit()
            # 落库验证（独立会话读）
            async with async_session() as fresh:
                stored = await fresh.get(User, user.id)
                assert stored.star_alias == first
                # 隐身开关默认 false = 参与展示（默认值不落库也行，此处断言模型默认）
                assert stored.resonance_visible is True

    asyncio.run(_go())


def test_get_or_create_alias_keeps_existing():
    """已有 star_alias → 原值返回，不重新生成（幂等）。"""

    async def _go() -> None:
        async with async_session() as session:
            user = User(openid="openid_resonance_svc2", nickname="服务测试2")
            session.add(user)
            await session.flush()
            user.star_alias = "星星·山茶"
            await session.commit()

            got = await get_or_create_alias(session, user)
            assert got == "星星·山茶"

    asyncio.run(_go())


# ── GET /resonance/alias ────────────────────────────────────────────────


def test_api_alias_requires_auth(client: TestClient):
    """未登录 401。"""
    assert client.get("/resonance/alias").status_code == 401


def test_api_alias_first_call_generates_and_persists(client: TestClient):
    """首次调用：200 返回星名并落库 users.star_alias（与确定性公式一致）。"""
    uid, headers = _new_user("openid_resonance_api1")
    resp = client.get("/resonance/alias", headers=headers)
    assert resp.status_code == 200
    alias = resp.json()["alias"]
    assert alias.startswith("星星·")
    # 落库验证（独立会话读）
    assert _read_user(uid)["star_alias"] == alias
    # 与确定性公式一致（同日同人恒定）
    assert alias == generate_alias(uid, beijing_today())


def test_api_alias_second_call_same_value_no_regen(client: TestClient):
    """二次调用：同值返回，不重复生成（落库值保持一份且不变）。"""
    uid, headers = _new_user("openid_resonance_api2")
    first = client.get("/resonance/alias", headers=headers).json()["alias"]
    second = client.get("/resonance/alias", headers=headers).json()["alias"]
    assert first == second
    assert _read_user(uid)["star_alias"] == first


# ── 迁移链：star_resonances 表 + users 两列 ─────────────────────────────


def test_alembic_migration_star_resonances_and_alias(tmp_path, monkeypatch):
    """迁移 77aa88bb99cc：star_resonances 表 + users 两列，可升级、可回滚。

    - star_resonances 列严格按设计 3.3 SQL：id/from_user_id/to_user_id/
      resonate_date/created_at；uq_from_to_date 唯一约束真实生效
      （同对同日期重复插入 → sqlite3.IntegrityError）
    - users.resonance_visible 默认 '1'（参与展示）；users.star_alias 可空 String(16)
    """
    from alembic import command
    from alembic.config import Config

    from app.config import settings

    db_path = tmp_path / "migration_resonance.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))

    # ── upgrade 到 head ──
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "star_resonances" in tables, "star_resonances 表应已创建"

    cols = {r[1] for r in conn.execute("PRAGMA table_info(star_resonances)")}
    assert {"id", "from_user_id", "to_user_id", "resonate_date", "created_at"} <= cols, (
        f"star_resonances 缺列: {sorted({'id','from_user_id','to_user_id','resonate_date','created_at'} - cols)}"
    )
    # 唯一约束存在（SQLite 以表 DDL 内联命名约束呈现）
    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='star_resonances'"
    ).fetchone()[0]
    assert "uq_from_to_date" in ddl, "应有命名唯一约束 uq_from_to_date"
    assert "UNIQUE" in ddl.upper()

    # 唯一约束真实生效：插入真实用户 + 同对同日期重复共鸣 → 第二次报错
    user_info = conn.execute("PRAGMA table_info(users)").fetchall()
    not_null_cols = [r[1] for r in user_info if r[3] == 1]

    def _insert_value(name: str) -> str:
        if name == "id":
            return "'u-res-a'"
        if name == "openid":
            return "'openid_res_a'"
        if name == "star_alias":
            return "NULL"
        return "0"

    _cols = ", ".join(not_null_cols)
    _vals = ", ".join(_insert_value(c) for c in not_null_cols)
    conn.execute(f"INSERT INTO users ({_cols}) VALUES ({_vals})")
    conn.execute(
        "INSERT INTO star_resonances (id, from_user_id, to_user_id, resonate_date, created_at) "
        "VALUES ('r1', 'u-res-a', 'u-res-b', '2026-08-11', '2026-08-11 10:00:00')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO star_resonances (id, from_user_id, to_user_id, resonate_date, created_at) "
            "VALUES ('r2', 'u-res-a', 'u-res-b', '2026-08-11', '2026-08-11 11:00:00')"
        )
    # 不同日期不受限（同对跨日允许）
    conn.execute(
        "INSERT INTO star_resonances (id, from_user_id, to_user_id, resonate_date, created_at) "
        "VALUES ('r3', 'u-res-a', 'u-res-b', '2026-08-12', '2026-08-12 10:00:00')"
    )
    # 提交写入事务，释放写锁（否则 downgrade 的 DDL 会撞 database is locked）
    conn.commit()

    # users 两列：resonance_visible 带默认 '1'（默认参与），star_alias 可空
    user_cols = {r[1]: (r[4], r[3]) for r in conn.execute("PRAGMA table_info(users)")}
    # r[4]=dflt_value, r[3]=notnull
    assert "resonance_visible" in user_cols, "users 应含 resonance_visible 列"
    assert "star_alias" in user_cols, "users 应含 star_alias 列"
    # SQLite dflt_value 为字面 SQL 文本：'1' 或带引号 "'1'" 均视为默认 '1'
    assert user_cols["resonance_visible"][1] == 1, "resonance_visible 应 NOT NULL"
    assert user_cols["resonance_visible"][0] in ("1", "'1'"), (
        f"resonance_visible 默认应为 '1'（默认参与展示），实际 {user_cols['resonance_visible']}"
    )
    assert user_cols["star_alias"][1] == 0, "star_alias 应可空"

    # ── downgrade 回 base：新表被删除、两列被删 ──
    command.downgrade(cfg, "base")
    tables_after = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "star_resonances" not in tables_after
    user_cols_after = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    conn.close()
    assert "resonance_visible" not in user_cols_after
    assert "star_alias" not in user_cols_after
