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
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.database import async_session
from app.models.checkin import CheckIn
from app.models.diary import DiaryEntry
from app.models.horoscope import HoroscopeHistory
from app.models.star_resonance import StarResonance
from app.models.card import TarotCard
from app.models.user import User
from app.schemas.resonance import today_active_criteria
from app.services.compliance import (
    AI_OUTPUT_BLACKLIST,
    MEET_BLACKLIST,
    find_forbidden,
)
from app.services.daily_card import pick_daily_card
from app.services.energy_engine import ZODIAC_NAMES_ZH, build_today_guidance
from app.services.resonance import ALIAS_POOL, generate_alias, get_or_create_alias
from app.services.star_words import beijing_today
from app.utils.auth import create_token

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ── helpers ─────────────────────────────────────────────────────────────


def _new_user(openid: str, **attrs) -> tuple[str, dict[str, str]]:
    """创建隔离测试用户，返回 (user_id, auth_headers)。

    attrs 透传给 User 模型（zodiac/star_alias/resonance_visible/stardust_total…）。
    """

    async def _go() -> tuple[str, str]:
        async with async_session() as session:
            user = User(openid=openid, nickname="星友圈测试", **attrs)
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return user.id, token

    uid, token = asyncio.run(_go())
    return uid, {"Authorization": f"Bearer {token}"}


def _mark_active_today(user_id: str, *, day: date | None = None) -> None:
    """今日行为信号（今日活跃口径：horoscope 为主信号，默认今日）。"""

    async def _go() -> None:
        async with async_session() as session:
            target = day or beijing_today()
            session.add(
                HoroscopeHistory(
                    user_id=user_id,
                    date=target,
                    energy={"love": 50, "career": 50, "social": 50, "health": 50},
                )
            )
            await session.commit()

    asyncio.run(_go())


def _resonate(from_user_id: str, to_user_id: str) -> None:
    """今日共鸣记录（防刷唯一约束同款表级约束）。"""

    async def _go() -> None:
        async with async_session() as session:
            session.add(
                StarResonance(
                    from_user_id=from_user_id,
                    to_user_id=to_user_id,
                    resonate_date=beijing_today(),
                )
            )
            await session.commit()

    asyncio.run(_go())


def _wall(client: TestClient, *, xff: str) -> dict:
    """公开请求共鸣墙（XFF 假 IP 隔离限流键）。"""
    resp = client.get("/resonance/wall", headers={"X-Forwarded-For": xff})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _find_group(groups: list[dict], gtype: str) -> dict | None:
    for g in groups:
        if g["type"] == gtype:
            return g
    return None


def _find_member(groups: list[dict], uid: str) -> dict | None:
    for g in groups:
        for m in g["members"]:
            if m["uid"] == uid:
                return m
    return None


def _collect_keys(obj, keys: set[str]) -> set[str]:
    """递归收集响应中所有 JSON 键（脱敏断言用）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            _collect_keys(v, keys)
    elif isinstance(obj, list):
        for item in obj:
            _collect_keys(item, keys)
    return keys


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


# ═══════════════════════════════════════════════════════════════════════
# 共鸣墙（SDD P2 · T8-2）：今日活跃聚合 + 三分组 + 兜底 + 脱敏 + 限流
# ═══════════════════════════════════════════════════════════════════════


# ── today_active_criteria：今日活跃口径纯函数 ───────────────────────────


def test_today_active_criteria():
    """今日活跃 = 隐身即不活跃；任一今日信号（horoscope/diary/checkin/resonance）即活跃。"""
    assert not today_active_criteria(resonance_visible=False, has_horoscope=True), (
        "隐身用户不应出现在墙"
    )
    assert not today_active_criteria(resonance_visible=True), "无任何今日行为 → 不活跃"
    assert today_active_criteria(resonance_visible=True, has_horoscope=True)
    assert today_active_criteria(resonance_visible=True, has_diary=True)
    assert today_active_criteria(resonance_visible=True, has_checkin=True)
    assert today_active_criteria(resonance_visible=True, has_resonance=True)


# ── 公开免登录 + 脱敏键集 ───────────────────────────────────────────────


def test_wall_public_no_auth_200(client: TestClient):
    """公开页免登录 200；响应顶层键恰为 active_count/groups/my_card。"""
    resp = client.get("/resonance/wall", headers={"X-Forwarded-For": "203.0.113.11"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"active_count", "groups", "my_card"}
    assert body["my_card"] is None


def test_wall_desensitized_keyset(client: TestClient):
    """脱敏断言：响应键集不含任何可联系字段（nickname/avatar/openid/出生/邀请码）。"""
    uid, _ = _new_user("openid_wall_des1", zodiac="pisces", star_alias="星星·晚风")
    _mark_active_today(uid)
    body = _wall(client, xff="203.0.113.12")
    keys = _collect_keys(body, set())
    for secret in ("nickname", "avatar", "openid", "birth_date", "birth_time", "invite_code"):
        assert secret not in keys, f"共鸣墙响应泄漏敏感字段: {secret}"


# ── 隐身过滤 ────────────────────────────────────────────────────────────


def test_wall_hidden_users_filtered(client: TestClient):
    """隐身过滤：resonance_visible=false 的用户即使今日活跃也不出现在墙。"""
    vis = []
    for i in range(3):
        uid, _ = _new_user(f"openid_wall_hid{i}", zodiac="pisces", star_alias=f"星星·明{i}")
        _mark_active_today(uid)
        vis.append(uid)
    hid, _ = _new_user("openid_wall_hid3", zodiac="pisces", star_alias="星星·隐", resonance_visible=False)
    _mark_active_today(hid)

    body = _wall(client, xff="203.0.113.13")
    assert body["active_count"] >= 3
    uids = {m["uid"] for g in body["groups"] for m in g["members"]}
    assert set(vis) <= uids, "可见活跃用户应出现在墙"
    assert hid not in uids, "隐身用户不应出现在墙"
    aliases = {m["alias"] for g in body["groups"] for m in g["members"]}
    assert "星星·隐" not in aliases


# ── 分组：同星座 / 同星光数 / 同今日牌 ──────────────────────────────────


def test_wall_zodiac_grouping_and_label(client: TestClient):
    """分组正确：3 用户同 zodiac → 同组且 label 含星座中文名；星光数组亦存在。"""
    uids = []
    for i in range(3):
        uid, _ = _new_user(f"openid_wall_zod{i}", zodiac="taurus", star_alias=f"星星·牛{i}")
        _mark_active_today(uid)
        uids.append(uid)

    body = _wall(client, xff="203.0.113.14")
    # 墙上可能同时存在多个星座组，按 label 定位金牛座组（双鱼座组来自其他测试）
    group = next(
        (g for g in body["groups"]
         if g["type"] == "zodiac" and ZODIAC_NAMES_ZH["taurus"] in g["label"]),
        None,
    )
    assert group is not None, "应有金牛座 zodiac 组"
    assert {m["uid"] for m in group["members"]} == set(uids), "同星座 3 人应同组"
    assert all(m["zodiac"] == "taurus" for m in group["members"])

    num = _find_group(body["groups"], "number")
    assert num is not None, "应有星光数（number）组"
    star_number = build_today_guidance(beijing_today(), "taurus")["star_number"]
    assert f"· {star_number}" in num["label"], (
        f"星光数组 label 应含当日星光数，实际 {num['label']}"
    )
    assert all(m["star_number"] == star_number for m in num["members"])


# ── 兜底组：组内 <3 人合并进「同星光的星」 ──────────────────────────────


def test_wall_small_group_merges_to_fallback(client: TestClient):
    """兜底组：组内 2 人 → 合并进「同星光的星」（不显零、不显小星座组）。"""
    u1, _ = _new_user("openid_wall_fb1", zodiac="leo", star_alias="星星·狮一")
    u2, _ = _new_user("openid_wall_fb2", zodiac="leo", star_alias="星星·狮二")
    for u in (u1, u2):
        _mark_active_today(u)

    body = _wall(client, xff="203.0.113.15")
    fb = _find_group(body["groups"], "fallback")
    assert fb is not None, "不足 3 人的组成员应并入兜底组"
    assert fb["label"] == "同星光的星"
    fb_uids = {m["uid"] for m in fb["members"]}
    assert {u1, u2} <= fb_uids, "2 人同星座组应整体并入兜底组"
    # 不足 3 人的星座不单独出组（任何 zodiac 组都不含这两颗星）
    for g in body["groups"]:
        if g["type"] == "zodiac":
            assert {u1, u2}.isdisjoint({m["uid"] for m in g["members"]}), (
                "不足 3 人的星座组不应单独展示"
            )


# ── 今日活跃口径：今日信号 vs 仅昨日 ────────────────────────────────────


def test_wall_today_active_criteria_behavior(client: TestClient):
    """今日活跃口径：今日有 horoscope 无日记 → 活跃；仅昨日有 → 不活跃。"""
    today_active, _ = _new_user("openid_wall_act1", zodiac="gemini", star_alias="星星·今")
    yesterday_only, _ = _new_user("openid_wall_act2", zodiac="gemini", star_alias="星星·昨")
    _mark_active_today(today_active)
    _mark_active_today(yesterday_only, day=beijing_today() - timedelta(days=1))

    body = _wall(client, xff="203.0.113.16")
    uids = {m["uid"] for g in body["groups"] for m in g["members"]}
    assert today_active in uids, "今日有 horoscope 记录 → 活跃"
    assert yesterday_only not in uids, "仅昨日有记录 → 不活跃"


def test_wall_diary_counts_as_today_active(client: TestClient):
    """今日活跃口径：无 horoscope 但今日有日记 → 仍活跃。"""
    uid, _ = _new_user("openid_wall_diary1", zodiac="libra", star_alias="星星·记")

    async def _go() -> None:
        async with async_session() as session:
            session.add(DiaryEntry(user_id=uid, entry_date=beijing_today(), mood="平静"))
            await session.commit()

    asyncio.run(_go())

    body = _wall(client, xff="203.0.113.19")
    uids = {m["uid"] for g in body["groups"] for m in g["members"]}
    assert uid in uids, "今日有日记（无 horoscope）→ 仍活跃"


# ── resonated_by_me 标记 ───────────────────────────────────────────────


def test_wall_resonated_by_me_flag(client: TestClient):
    """resonated_by_me：登录时按今日给出记录标记；未登录全 false。"""
    me, me_headers = _new_user("openid_wall_me1", zodiac="cancer", star_alias="星星·我")
    u1, _ = _new_user("openid_wall_m1", zodiac="cancer", star_alias="星星·甲")
    u2, _ = _new_user("openid_wall_m2", zodiac="cancer", star_alias="星星·乙")
    for u in (me, u1, u2):
        _mark_active_today(u)
    _resonate(me, u1)

    # 未登录：resonated_by_me 全 false
    anon = _wall(client, xff="203.0.113.17")
    assert _find_member(anon["groups"], u1)["resonated_by_me"] is False
    assert _find_member(anon["groups"], u1)["resonate_count"] == 1, (
        "resonate_count = 今日收到共鸣数"
    )

    # 登录：仅给过共鸣的 u1 为 true
    resp = client.get("/resonance/wall", headers=me_headers)
    assert resp.status_code == 200
    me_body = resp.json()
    assert _find_member(me_body["groups"], u1)["resonated_by_me"] is True
    assert _find_member(me_body["groups"], u2)["resonated_by_me"] is False


# ── my_card ────────────────────────────────────────────────────────────


def test_wall_my_card_when_logged_in(client: TestClient):
    """登录：my_card 含星名/星座/星光数/今日牌/星阶名/今日收到共鸣数。"""
    me, me_headers = _new_user(
        "openid_wall_mc1", zodiac="capricorn", star_alias="星星·摩羯",
        stardust_total=35, star_tier=2,  # 星阶索引 2 = 星辉（阈值 30；与 share.py 同口径）
    )
    u1, _ = _new_user("openid_wall_mc2", zodiac="capricorn", star_alias="星星·伴")
    _mark_active_today(me)
    _mark_active_today(u1)
    _resonate(u1, me)

    body = client.get("/resonance/wall", headers=me_headers).json()
    mc = body["my_card"]
    assert mc is not None, "登录后 my_card 不应为 null"
    assert mc["alias"] == "星星·摩羯"
    assert mc["zodiac"] == "capricorn"
    assert mc["star_number"] == build_today_guidance(beijing_today(), "capricorn")["star_number"]
    assert mc["tier_name"] == "星辉", "stardust 35 → 星辉档（阈值 30）"
    assert mc["visible"] is True, "my_card 应回读本人隐身状态（默认参与展示）"

    async def _cards() -> TarotCard:
        async with async_session() as session:
            result = await session.execute(select(TarotCard).order_by(TarotCard.id))
            return list(result.scalars().all())

    cards = asyncio.run(_cards())
    expected = pick_daily_card(cards, me, beijing_today())
    assert mc["card"] == {"card_id": expected.id, "name_zh": expected.name_zh}
    assert mc["received_today"] == 1, "今日收到共鸣数 = 1"


# ── 公开限流：30 次/分/IP ───────────────────────────────────────────────


def test_wall_rate_limited_429(client: TestClient):
    """公开限流：同 IP 连续第 31 次请求 → 429（30 次/分）。"""
    last = None
    for _ in range(31):
        last = client.get("/resonance/wall", headers={"X-Forwarded-For": "198.51.100.77"})
    assert last.status_code == 429, "连续第 31 次请求应被限流 429"


# ═══════════════════════════════════════════════════════════════════════
# 共鸣送出/统计/隐身/海报（SDD P2 · T8-3）
# ═══════════════════════════════════════════════════════════════════════

# 海报固定文案与兜底句（T8-3 简报；兜底句静态无变量，恒过禁词扫描）
_CAPTION = "两颗星在同一片夜空相遇 ✦"
_CAPTION_FALLBACK = "两颗星在这一刻同频 ✦"
_DISCLAIMER = "仅供娱乐 · 星光映照"


def _resonate_on(from_user_id: str, to_user_id: str, day: date) -> None:
    """指定日期共鸣记录（跨日统计测试用）。"""

    async def _go() -> None:
        async with async_session() as session:
            session.add(
                StarResonance(
                    from_user_id=from_user_id,
                    to_user_id=to_user_id,
                    resonate_date=day,
                )
            )
            await session.commit()

    asyncio.run(_go())


def _give(client: TestClient, headers: dict[str, str], to_uid: str):
    return client.post("/resonance/give", json={"to_user_id": to_uid}, headers=headers)


# ── give：首次 / 幂等 / 每日上限 / 自给 / 目标校验 / 不产星尘 ─────────────


def test_give_first_ok_count_today_1_persisted(client: TestClient):
    """give 首次成功：200 {ok, count_today:1, limit:10} 且共鸣记录落库。"""
    me, me_h = _new_user("openid_give_first1", zodiac="taurus", star_alias="星星·我")
    target, _ = _new_user("openid_give_first2", zodiac="taurus", star_alias="星星·你")
    r = _give(client, me_h, target)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "count_today": 1, "limit": 10}

    async def _count() -> int:
        async with async_session() as session:
            result = await session.execute(
                select(func.count(StarResonance.id)).where(
                    StarResonance.from_user_id == me,
                    StarResonance.to_user_id == target,
                )
            )
            return result.scalar_one()

    assert asyncio.run(_count()) == 1, "give 成功应落库一条共鸣记录"


def test_give_same_pair_same_day_409(client: TestClient):
    """同日同人二次 give → 409 且 detail 含「已共鸣过」（唯一约束幂等）。"""
    me, me_h = _new_user("openid_give_dup1", star_alias="星星·重")
    target, _ = _new_user("openid_give_dup2", star_alias="星星·的")
    assert _give(client, me_h, target).status_code == 200
    second = _give(client, me_h, target)
    assert second.status_code == 409, second.text
    assert "已共鸣过" in second.json()["detail"]


def test_give_daily_limit_10_eleventh_400(client: TestClient):
    """每日上限：第 11 次 give → 400 且 detail 含「明天再来」（count_today 1→10）。"""
    me, me_h = _new_user("openid_give_limit1", star_alias="星星·满")
    count_today = None
    for i in range(10):
        target, _ = _new_user(f"openid_give_limit_t{i}", star_alias=f"星星·t{i}")
        r = _give(client, me_h, target)
        assert r.status_code == 200, r.text
        count_today = r.json()["count_today"]
    assert count_today == 10, "前 10 次 count_today 应递增到 10"
    extra, _ = _new_user("openid_give_limit_x", star_alias="星星·x")
    blocked = _give(client, me_h, extra)
    assert blocked.status_code == 400, blocked.text
    assert "明天再来" in blocked.json()["detail"]


def test_give_self_400(client: TestClient):
    """不能给自己共鸣 → 400。"""
    me, me_h = _new_user("openid_give_self", star_alias="星星·己")
    r = _give(client, me_h, me)
    assert r.status_code == 400, r.text


def test_give_target_missing_404(client: TestClient):
    """to_user_id 不存在 → 404。"""
    me, me_h = _new_user("openid_give_miss", star_alias="星星·缺")
    r = _give(client, me_h, "no-such-uid")
    assert r.status_code == 404, r.text


def test_give_target_hidden_404(client: TestClient):
    """to_user_id 已隐身 → 404（隐身即从夜空消失）。"""
    me, me_h = _new_user("openid_give_hid1", star_alias="星星·给")
    hidden, _ = _new_user("openid_give_hid2", star_alias="星星·隐", resonance_visible=False)
    r = _give(client, me_h, hidden)
    assert r.status_code == 404, r.text


def test_give_produces_no_stardust(client: TestClient):
    """三重防刷之三：共鸣不产星尘（given 后 stardust_total 不变）。"""
    me, me_h = _new_user("openid_give_dust", star_alias="星星·尘", stardust_total=5)
    target, _ = _new_user("openid_give_dust2", star_alias="星星·土")
    assert _give(client, me_h, target).status_code == 200

    async def _read() -> int:
        async with async_session() as session:
            u = await session.get(User, me)
            return u.stardust_total

    assert asyncio.run(_read()) == 5, "共鸣不应产生任何星尘"


def test_give_requires_auth(client: TestClient):
    """未登录 give → 401。"""
    assert client.post("/resonance/give", json={"to_user_id": "x"}).status_code == 401


# ── stats：累计口径（跨日 given_total 累加、received_today 复位）─────────


def test_stats_accumulates_across_days(client: TestClient):
    """stats：跨日 given_total 累加；received_total 累计；received_today 仅今日。"""
    me, me_h = _new_user("openid_stats_me", star_alias="星星·统")
    u1, _ = _new_user("openid_stats_u1", star_alias="星星·一")
    u2, _ = _new_user("openid_stats_u2", star_alias="星星·二")
    u3, _ = _new_user("openid_stats_u3", star_alias="星星·三")
    u4, _ = _new_user("openid_stats_u4", star_alias="星星·四")
    yesterday = beijing_today() - timedelta(days=1)
    # 给出：昨日给 u1（直接落库）+ 今日给 u2（API）→ given_total=2
    _resonate_on(me, u1, yesterday)
    assert _give(client, me_h, u2).status_code == 200
    # 收到：昨日 u3 + 今日 u4 → received_total=2、received_today=1
    _resonate_on(u3, me, yesterday)
    _resonate_on(u4, me, beijing_today())

    r = client.get("/resonance/stats", headers=me_h)
    assert r.status_code == 200, r.text
    assert r.json() == {"given_total": 2, "received_total": 2, "received_today": 1}


def test_stats_requires_auth(client: TestClient):
    """未登录 stats → 401。"""
    assert client.get("/resonance/stats").status_code == 401


# ── visibility：隐身开关即时生效 ─────────────────────────────────────────


def test_visibility_off_immediate_effect_on_wall(client: TestClient):
    """visibility=false 即时生效：墙不再含该用户；本人仍可看墙（own 可见）。

    用独占星座「virgo」3 人组钉住墙成员资格：3 人组为独立星座组（不入
    兜底合并），组内 3 ≤ Top20 上限 → 成员展示确定性强；不含此星座的
    共鸣记录用户不影响该组。隐身关闭/开启后该组在 2 人/3 人间切换，
    可见性断言不再依赖兜底组的 Top20 轮换（uid 随机序，避免偶发）。
    """
    me, me_h = _new_user("openid_vis_me", zodiac="virgo", star_alias="星星·显")
    for i in range(2):
        uid, _ = _new_user(f"openid_vis_c{i}", zodiac="virgo", star_alias=f"星星·伴{i}")
        _mark_active_today(uid)
    _mark_active_today(me)

    # 默认参与 → 独立 virgo 星座组（3 人）必含本人
    before = _wall(client, xff="203.0.113.31")
    assert me in {m["uid"] for g in before["groups"] for m in g["members"]}, (
        "默认 resonance_visible=true 应在墙上"
    )

    r = client.post("/resonance/visibility", json={"visible": False}, headers=me_h)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "visible": False}
    assert _read_user(me)["resonance_visible"] is False, "users.resonance_visible 应落库 false"

    after = _wall(client, xff="203.0.113.32")
    assert me not in {m["uid"] for g in after["groups"] for m in g["members"]}, (
        "隐身应立即从墙上消失"
    )
    # 本人仍可看墙（own 可看，my_card 返回 + 回读隐身状态）
    own = client.get("/resonance/wall", headers=me_h)
    assert own.status_code == 200
    own_mc = own.json()["my_card"]
    assert own_mc is not None
    assert own_mc["visible"] is False, "隐身中进页，my_card.visible 应回读 false（开关初值依据）"

    # 重新开启 → 回到墙上
    r2 = client.post("/resonance/visibility", json={"visible": True}, headers=me_h)
    assert r2.status_code == 200
    assert r2.json() == {"ok": True, "visible": True}
    reopened = _wall(client, xff="203.0.113.33")
    assert me in {m["uid"] for g in reopened["groups"] for m in g["members"]}


def test_visibility_requires_auth(client: TestClient):
    """未登录 visibility → 401。"""
    assert client.post("/resonance/visibility", json={"visible": False}).status_code == 401


# ── poster：脱敏键集 + 固定文案 + 维度 + 内容安全接线 ─────────────────────


def test_poster_keyset_and_fixed_caption(client: TestClient):
    """poster：键集脱敏断言 + caption/disclaimer 固定句 + 维度与派生字段钉住。"""
    me, me_h = _new_user(
        "openid_post_a", zodiac="taurus", star_alias="星星·甲",
        stardust_total=35, star_tier=2,  # 星阶索引 2 = 星辉（与墙测试同口径）
    )
    target, _ = _new_user("openid_post_b", zodiac="taurus", star_alias="星星·乙")

    r = client.get("/resonance/poster", params={"to_user_id": target}, headers=me_h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "alias_a", "alias_b", "zodiac_a", "zodiac_b",
        "star_number_a", "star_number_b",
        "card_a", "card_b", "tier_name_a", "tier_name_b",
        "dimension", "caption", "disclaimer",
    }
    assert set(body["card_a"]) == {"card_id", "name_zh"}
    assert set(body["card_b"]) == {"card_id", "name_zh"}
    # 固定文案
    assert body["caption"] == _CAPTION
    assert body["disclaimer"] == _DISCLAIMER
    # 脱敏：零可联系字段、零 uid
    keys = _collect_keys(body, set())
    for secret in ("nickname", "avatar", "openid", "birth_date", "birth_time",
                   "invite_code", "uid", "openid"):
        assert secret not in keys, f"共鸣海报泄漏敏感字段: {secret}"
    # 派生字段与确定性来源同源
    assert body["alias_a"] == "星星·甲" and body["alias_b"] == "星星·乙"
    assert body["zodiac_a"] == body["zodiac_b"] == "taurus"
    assert body["star_number_a"] == body["star_number_b"] == (
        build_today_guidance(beijing_today(), "taurus")["star_number"]
    )
    assert body["tier_name_a"] == "星辉", "stardust 35 → 星辉档（阈值 30）"

    async def _cards() -> list[TarotCard]:
        async with async_session() as session:
            result = await session.execute(select(TarotCard).order_by(TarotCard.id))
            return list(result.scalars().all())

    cards = asyncio.run(_cards())
    expect_a = pick_daily_card(cards, me, beijing_today())
    expect_b = pick_daily_card(cards, target, beijing_today())
    assert body["card_a"] == {"card_id": expect_a.id, "name_zh": expect_a.name_zh}
    assert body["card_b"] == {"card_id": expect_b.id, "name_zh": expect_b.name_zh}
    assert body["dimension"] == "zodiac", "双方同星座 → zodiac 维"


def test_poster_dimension_number_when_zodiacs_differ(client: TestClient):
    """poster 维度：星座不同 → number 维（同日全站星光数相同，恒真兜底）。"""
    me, me_h = _new_user("openid_post_c", zodiac="aries", star_alias="星星·丙")
    target, _ = _new_user("openid_post_d", zodiac="scorpio", star_alias="星星·丁")
    r = client.get("/resonance/poster", params={"to_user_id": target}, headers=me_h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dimension"] == "number"
    assert body["star_number_a"] == body["star_number_b"], (
        "同日 star_number 应全站相同（date-only 派生）"
    )


def test_poster_target_missing_404(client: TestClient):
    """poster 目标不存在 → 404。"""
    me, me_h = _new_user("openid_post_miss", star_alias="星星·无")
    r = client.get("/resonance/poster", params={"to_user_id": "nope"}, headers=me_h)
    assert r.status_code == 404, r.text


def test_poster_target_hidden_404(client: TestClient):
    """poster 目标已隐身 → 404（隐身即不出现在任何对外展示）。"""
    me, me_h = _new_user("openid_post_h1", star_alias="星星·给")
    hidden, _ = _new_user("openid_post_h2", star_alias="星星·隐", resonance_visible=False)
    r = client.get("/resonance/poster", params={"to_user_id": hidden}, headers=me_h)
    assert r.status_code == 404, r.text


def test_poster_requires_auth(client: TestClient):
    """未登录 poster → 401。"""
    assert client.get("/resonance/poster", params={"to_user_id": "x"}).status_code == 401


def test_poster_msg_check_risky_replaced_with_fallback(client: TestClient, monkeypatch):
    """msg_sec_check 命中风险 → caption 替换为安全兜底句（不 4xx、不阻塞）。"""

    async def _fake_risky(content: str, openid: str | None = None) -> dict:
        return {"safe": False, "skipped": False, "err": "risky content"}

    monkeypatch.setattr("app.api.resonance.msg_sec_check", _fake_risky)
    me, me_h = _new_user("openid_post_risk1", zodiac="leo", star_alias="星星·险")
    target, _ = _new_user("openid_post_risk2", zodiac="leo", star_alias="星星·靶")
    r = client.get("/resonance/poster", params={"to_user_id": target}, headers=me_h)
    assert r.status_code == 200, r.text
    assert r.json()["caption"] == _CAPTION_FALLBACK


def test_poster_msg_check_exception_returns_original(client: TestClient, monkeypatch):
    """msg_sec_check 抛异常 → 不阻塞，caption 返回原文（fail-open）。"""

    async def _fake_boom(content: str, openid: str | None = None) -> dict:
        raise RuntimeError("wechat api down")

    monkeypatch.setattr("app.api.resonance.msg_sec_check", _fake_boom)
    me, me_h = _new_user("openid_post_boom1", zodiac="leo", star_alias="星星·异")
    target, _ = _new_user("openid_post_boom2", zodiac="leo", star_alias="星星·常")
    r = client.get("/resonance/poster", params={"to_user_id": target}, headers=me_h)
    assert r.status_code == 200, r.text
    assert r.json()["caption"] == _CAPTION


def test_poster_local_blacklist_hit_replaced_with_fallback(client: TestClient, monkeypatch):
    """find_forbidden 命中（本地禁词表）→ caption 替换为兜底句。"""
    monkeypatch.setattr("app.api.resonance._RESONANCE_CAPTION", "两颗星注定相遇 ✦")
    me, me_h = _new_user("openid_post_fb1", zodiac="leo", star_alias="星星·词")
    target, _ = _new_user("openid_post_fb2", zodiac="leo", star_alias="星星·禁")
    r = client.get("/resonance/poster", params={"to_user_id": target}, headers=me_h)
    assert r.status_code == 200, r.text
    assert r.json()["caption"] == _CAPTION_FALLBACK


def test_poster_fixed_texts_compliant():
    """固定文案/兜底句/免责行全部过 compliance 双表扫描（无禁词）。"""
    for text in (_CAPTION, _CAPTION_FALLBACK, _DISCLAIMER):
        assert find_forbidden(text, MEET_BLACKLIST) == [], f"MEET_BLACKLIST 命中: {text}"
        assert find_forbidden(text, AI_OUTPUT_BLACKLIST) == [], f"AI_OUTPUT_BLACKLIST 命中: {text}"
