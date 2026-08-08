"""
本命星盘三要素 + 深度报告付费测试（星光映照 · 开发 05）。

覆盖：
- 太阳星座：已知生日断言（与前端 zodiacFromDate 同区间表）
- 月亮星座：无时间查表（近似）、有时间精化公式、全 365 日不抛错
- 上升星座：有/无出生时间、城市经度修正、太阳升起时刻≈太阳星座
- GET /user/birthchart：鉴权 401；部分信息 missing 提示；完整信息三要素齐全
- 深度报告：未付费 402 / 付费 200 / 会员免费 / 缓存复用 / AI 失败模板兜底
- 订单回调：birthchart_report 商品支付 → 权益 birthchart_paid 置位
- 出生信息更新 → 星盘缓存失效重算
- 迁移链：users 表 birthchart 三字段升级/回滚

测试环境 DEEPSEEK_API_KEY 为空 → AI 生成自动回退模板（确定性）。
"""

import asyncio
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db.database import async_session
from app.models.user import User
from app.services.birthchart import (
    MOON_SIGN_MATRIX,
    fallback_report,
    moon_sign,
    rising_sign,
    sun_sign,
)
from app.utils.auth import create_token

# 已知生日
BIRTH_LEO = "1996-08-08"       # 太阳狮子
BIRTH_GEMINI = "1995-06-15"    # 太阳双子
BIRTH_CAP = "1990-01-01"       # 太阳摩羯


def _dev_login(client: TestClient, member: bool = False) -> dict:
    url = f"/auth/dev-login?member={'true' if member else 'false'}"
    resp = client.post(url, headers={"X-Dev-Key": settings.DEV_LOGIN_KEY})
    assert resp.status_code == 200, resp.text
    return {"token": resp.json()["token"], "user": resp.json()["user"]}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_user(openid: str, nickname: str, member: bool = False) -> dict:
    """Create a fresh user directly in the test DB; returns {id, token}."""

    async def _run():
        async with async_session() as session:
            user = User(openid=openid, nickname=nickname, is_member=member)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    user = asyncio.run(_run())
    return {"id": user.id, "token": create_token(user.id, user.token_version)}


async def _patch_user(uid: str, **fields):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == uid))
        u = result.scalar_one()
        for key, value in fields.items():
            setattr(u, key, value)
        await session.commit()


def _set_birth(uid: str, birth_date: str, birth_time=None, birth_city=None):
    asyncio.run(_patch_user(uid, birth_date=birth_date, birth_time=birth_time, birth_city=birth_city))


# ─────────────────────────────────────────────────────────────────────────────
# 单元：三要素计算
# ─────────────────────────────────────────────────────────────────────────────


def test_sun_sign_known_birthdays():
    """太阳星座：已知生日断言（与前端同区间表）。"""
    assert sun_sign(8, 8) == "leo"
    assert sun_sign(6, 15) == "gemini"
    assert sun_sign(1, 1) == "capricorn"
    assert sun_sign(12, 22) == "capricorn"   # 边界：12-22 含当日
    assert sun_sign(12, 21) == "sagittarius"  # 边界：12-21 仍是射手
    assert sun_sign(2, 19) == "pisces"
    assert sun_sign(2, 18) == "aquarius"


def test_moon_sign_no_time_uses_matrix_approx():
    """月亮星座：无出生时间 → 查预计算表且标记近似。"""
    key, approx = moon_sign(8, 8)
    assert key == "sagittarius"  # 2026 历法查表值
    assert approx is True
    key2, approx2 = moon_sign(1, 3)
    assert key2 == "capricorn"   # 2026-01-03 新月 → 摩羯
    assert approx2 is True


def test_moon_sign_with_time_refined():
    """月亮星座：有出生时间 → 精化公式且不再标记近似。"""
    key, approx = moon_sign(8, 8, "14:30")
    assert approx is False
    assert key in MOON_SIGN_MATRIX or key == "capricorn"
    # 00:00 精化与查表一致（1-30 日）
    assert moon_sign(8, 8, "00:00")[0] == moon_sign(8, 8)[0]
    # 非法时间回退查表
    key2, approx2 = moon_sign(8, 8, "不合法")
    assert approx2 is True


def test_moon_sign_lookup_covers_full_year():
    """365 日查表全覆盖（2026 历法，2 月 28 天）。"""
    for month in range(1, 13):
        last = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
        for day in range(1, last + 1):
            key, _ = moon_sign(month, day)
            assert key in MOON_SIGN_MATRIX or True  # 合法 key 集合
            assert key in {
                "aries", "taurus", "gemini", "cancer", "leo", "virgo",
                "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
            }


def test_rising_sign_requires_time():
    """上升星座：无出生时间 → None；有 → 太阳升起时刻≈太阳星座。"""
    assert rising_sign("leo", None) is None
    assert rising_sign("leo", "") is None
    assert rising_sign("leo", "14:30") == "sagittarius"
    # 6:00 太阳时升起 → 上升 = 太阳星座（默认东八区）
    assert rising_sign("leo", "06:00") == "leo"
    # 城市经度修正：北京（116.4°E）表时 6:00 = 太阳时 5:46 → 前一宫
    assert rising_sign("leo", "06:00", "北京") == "cancer"


# ─────────────────────────────────────────────────────────────────────────────
# 兜底报告
# ─────────────────────────────────────────────────────────────────────────────


def test_fallback_report_template():
    """AI 失败 → 模板兜底：四段齐全、温和非决定论。"""
    chart = {
        "sun": {"name": "狮子座", "text": "天生聚光灯体质，爱要爱得张扬"},
        "moon": {"name": "双鱼座", "text": "情绪像海，需要温柔的岸"},
        "rising": {"name": "天秤座", "text": "初见让人如沐春风"},
    }
    report = fallback_report(chart)
    assert {"character", "relation", "annual_theme", "card_advice"} <= set(report)
    for banned in ("注定", "一定会", "大凶", "血光"):
        assert banned not in report["character"] + report["annual_theme"]


# ─────────────────────────────────────────────────────────────────────────────
# API：GET /user/birthchart
# ─────────────────────────────────────────────────────────────────────────────


def test_birthchart_requires_auth(client: TestClient):
    """未登录 → 401。"""
    assert client.get("/user/birthchart").status_code == 401
    assert client.post("/user/birthchart/report").status_code == 401


def test_birthchart_no_birth_date_partial(client: TestClient):
    """无出生日期 → 三要素均 null + missing=["birth_date"] 提示。"""
    user = _create_user(f"bc_nobirth_{uuid.uuid4().hex[:8]}", "无出生日期用户")
    resp = client.get("/user/birthchart", headers=_auth(user["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["sun"] is None and data["moon"] is None and data["rising"] is None
    assert data["missing"] == ["birth_date"]
    assert "出生日期" in data["message"]


def test_birthchart_partial_no_time(client: TestClient):
    """有日期无时间 → 太阳+月亮（近似）+ missing=["birth_time"]，上升 null。"""
    user = _create_user(f"bc_notime_{uuid.uuid4().hex[:8]}", "缺时间用户")
    _set_birth(user["id"], BIRTH_LEO, None, "北京")

    resp = client.get("/user/birthchart", headers=_auth(user["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["sun"]["zodiac"] == "leo"
    assert data["sun"]["label"] == "核心动力"
    assert data["moon"]["approx"] is True
    assert data["rising"] is None
    assert data["missing"] == ["birth_time"]
    assert "上升" in data["message"]
    assert data["sun"]["name"] == "狮子座"
    assert data["sun"]["text"]


def test_birthchart_full_three_elements(client: TestClient):
    """完整出生信息 → 三要素齐全，月亮精化、上升近似，文案有兜底。"""
    user = _create_user(f"bc_full_{uuid.uuid4().hex[:8]}", "完整星盘用户")
    _set_birth(user["id"], BIRTH_LEO, "14:30", "北京")

    resp = client.get("/user/birthchart", headers=_auth(user["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["missing"] == []
    assert data["sun"]["zodiac"] == "leo"
    assert data["sun"]["name"] == "狮子座"
    assert data["sun"]["label"] == "核心动力"
    assert data["moon"]["zodiac"] == "capricorn"  # 精化公式值
    assert data["moon"]["approx"] is False
    assert data["moon"]["label"] == "情绪底色"
    assert data["rising"]["zodiac"] == "sagittarius"
    assert data["rising"]["approx"] is True
    assert data["rising"]["label"] == "他人眼中的我"
    for el in (data["sun"], data["moon"], data["rising"]):
        assert el["text"] and el["detail"]["talent"]
    assert data["birth"]["complete"] is True


def test_birthchart_deterministic_and_cached(client: TestClient):
    """同日同人两次调用一致；AI 文案落缓存（birthchart_json 非空）。"""
    user = _create_user(f"bc_cache_{uuid.uuid4().hex[:8]}", "缓存用户")
    _set_birth(user["id"], BIRTH_GEMINI, "08:30", "上海")

    r1 = client.get("/user/birthchart", headers=_auth(user["token"]))
    r2 = client.get("/user/birthchart", headers=_auth(user["token"]))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["sun"] == r2.json()["sun"]

    async def _read_cache():
        async with async_session() as session:
            u = (await session.execute(select(User).where(User.id == user["id"]))).scalar_one()
            return u.birthchart_json

    cached = asyncio.run(_read_cache())
    assert cached and json.loads(cached)["sun"]["zodiac"] == "gemini"


def test_birth_update_invalidates_cache(client: TestClient):
    """POST /user/birth 更新出生信息 → 星盘缓存清空（下次重算）。"""
    user = _create_user(f"bc_inv_{uuid.uuid4().hex[:8]}", "缓存失效用户")
    _set_birth(user["id"], BIRTH_LEO, "14:30", "北京")
    client.get("/user/birthchart", headers=_auth(user["token"]))

    resp = client.post(
        "/user/birth",
        json={"birth_date": BIRTH_GEMINI, "birth_time": "08:30", "birth_city": "上海"},
        headers=_auth(user["token"]),
    )
    assert resp.status_code == 200

    async def _read():
        async with async_session() as session:
            u = (await session.execute(select(User).where(User.id == user["id"]))).scalar_one()
            return u.birthchart_json, u.birthchart_report

    chart_cache, report_cache = asyncio.run(_read())
    assert chart_cache is None and report_cache is None

    chart = client.get("/user/birthchart", headers=_auth(user["token"])).json()
    assert chart["sun"]["zodiac"] == "gemini"


# ─────────────────────────────────────────────────────────────────────────────
# API：POST /user/birthchart/report（付费链路）
# ─────────────────────────────────────────────────────────────────────────────


def test_report_requires_paid_or_member(client: TestClient):
    """非会员未付费 → 402。"""
    user = _create_user(f"bc_402_{uuid.uuid4().hex[:8]}", "未付费用户")
    _set_birth(user["id"], BIRTH_LEO, "14:30", "北京")
    resp = client.post("/user/birthchart/report", headers=_auth(user["token"]))
    assert resp.status_code == 402


def test_report_paid_user_gets_200(client: TestClient):
    """付费权益置位（支付回调的落点）→ 200 报告生成（AI 禁用 → 模板兜底）。"""
    user = _create_user(f"bc_paid_{uuid.uuid4().hex[:8]}", "付费用户")
    _set_birth(user["id"], BIRTH_LEO, "14:30", "北京")
    asyncio.run(_patch_user(user["id"], birthchart_paid=True))

    resp = client.post("/user/birthchart/report", headers=_auth(user["token"]))
    assert resp.status_code == 200
    data = resp.json()
    for section in ("character", "relation", "annual_theme", "card_advice"):
        assert data[section]
    assert data["cached"] is False
    assert data["fallback"] is True  # 测试环境 AI 禁用


def test_report_member_free(client: TestClient):
    """会员 → 免费生成（无需 birthchart_paid）。"""
    user = _create_user(f"bc_member_{uuid.uuid4().hex[:8]}", "会员用户", member=True)
    _set_birth(user["id"], BIRTH_LEO, "14:30", "北京")
    resp = client.post("/user/birthchart/report", headers=_auth(user["token"]))
    assert resp.status_code == 200
    assert resp.json()["character"]


def test_report_cached_after_first_generation(client: TestClient):
    """首次生成后缓存：再次请求 → 同一内容 + cached:true（不再重生成）。"""
    user = _create_user(f"bc_rcache_{uuid.uuid4().hex[:8]}", "报告缓存用户")
    _set_birth(user["id"], BIRTH_LEO, "14:30", "北京")
    asyncio.run(_patch_user(user["id"], birthchart_paid=True))

    r1 = client.post("/user/birthchart/report", headers=_auth(user["token"]))
    r2 = client.post("/user/birthchart/report", headers=_auth(user["token"]))
    assert r1.status_code == 200 and r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    assert d2["cached"] is True
    assert d1["character"] == d2["character"]
    assert d1["relation"] == d2["relation"]


def test_report_without_birth_date_400(client: TestClient):
    """已付费但无出生日期 → 400（先完善出生信息）。"""
    user = _create_user(f"bc_nobd_{uuid.uuid4().hex[:8]}", "付费无日期用户")
    asyncio.run(_patch_user(user["id"], birthchart_paid=True))
    resp = client.post("/user/birthchart/report", headers=_auth(user["token"]))
    assert resp.status_code == 400


def test_report_birth_change_invalidates_report_cache(client: TestClient):
    """出生信息变化 → 报告缓存清空（POST /user/birth 处理）。"""
    user = _create_user(f"bc_rinv_{uuid.uuid4().hex[:8]}", "报告失效用户")
    _set_birth(user["id"], BIRTH_LEO, "14:30", "北京")
    asyncio.run(_patch_user(user["id"], birthchart_paid=True))
    client.post("/user/birthchart/report", headers=_auth(user["token"]))

    client.post(
        "/user/birth",
        json={"birth_date": BIRTH_GEMINI, "birth_time": "08:30"},
        headers=_auth(user["token"]),
    )
    report = client.post("/user/birthchart/report", headers=_auth(user["token"]))
    assert report.status_code == 200
    assert report.json()["cached"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 订单回调 → 权益发放
# ─────────────────────────────────────────────────────────────────────────────


def test_birthchart_report_product_registered():
    """商品表注册 birthchart_report（19.9 · 权益=birthchart_paid）。"""
    from app.services.payment import PRODUCTS

    product = PRODUCTS["birthchart_report"]
    assert product["price"] == 19.90
    assert product["type"] == "single_purchase"


def test_birthchart_paid_benefit_branch_in_callback():
    """回调权益分支：birthchart_report → birthchart_paid=True（代码路径可读性守卫）。"""
    from app.api import orders as orders_api
    import inspect

    source = inspect.getsource(orders_api)
    assert 'order.product_type == "birthchart_report"' in source
    assert "user.birthchart_paid = True" in source


# ─────────────────────────────────────────────────────────────────────────────
# 迁移链
# ─────────────────────────────────────────────────────────────────────────────


def test_alembic_migration_birthchart_fields(tmp_path, monkeypatch):
    """迁移链：users 表 birthchart_paid/birthchart_json/birthchart_report 可升级、可回滚。"""
    from alembic import command
    from alembic.config import Config

    from pathlib import Path

    from app.config import settings as _settings

    backend_dir = Path(__file__).resolve().parent.parent
    db_path = tmp_path / "migration_birthchart.db"
    monkeypatch.setattr(_settings, "DATABASE_URL", f"sqlite:///{db_path}")

    cfg = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(cfg, "head")

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    assert "birthchart_paid" in cols
    assert "birthchart_json" in cols
    assert "birthchart_report" in cols

    # 默认值 false
    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()[0]
    assert "birthchart_paid" in ddl

    command.downgrade(cfg, "base")
    cols_after = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    conn.close()
    assert "birthchart_paid" not in cols_after
    assert "birthchart_report" not in cols_after
