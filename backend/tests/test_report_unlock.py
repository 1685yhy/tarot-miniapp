"""
星象月报权益（SDD P2 · T7-3 解锁权益 + T7-4 月报海报脱敏端点）测试。

T7-3 覆盖：
- PRODUCTS 注册 weekly_report(4.9) / monthly_report(19.9)（type=single_purchase）
- is_member_active：会员有效期实时判定（过期 → False；expires_at=None 永续）
- can_read_full：会员 或 对应解锁列（会员到期后旧解锁仍有效）
- /report/week|month：非会员未解锁 → locked 预览；解锁列置位 → 全文
- POST /report/{type}/unlock：非会员下单（复用 orders 管线，订单 product_type
  正确、支付参数非空）；会员/已解锁 → 400「你已拥有这份星光 ✦」；非法 type → 404
- 支付回调：weekly_report/monthly_report 商品 → 对应 BOOL 列置位；重复回调幂等
- POST /report/{type}/regenerate：仅会员；周/月各 1 次/周期（内存限流）；
  AI 失败 → 回退原缓存不覆盖（source 不变）；非法 type → 404

T7-4 覆盖：
- GET /report/month/poster：有缓存 → 脱敏字段完整（报告期+3 核心数字+AI 寄语
  一句+星阶名+固定分享文案）；键集断言无昵称/无原文统计明细/无手账内容
- 无缓存 → 404「先看报告，再分享星光 ✦」；非会员未解锁 → 403；
  已解锁非会员 → 200；未登录 401
- 迁移链：users 表 weekly_report_unlocked/monthly_report_unlocked 可升级、可回滚

测试环境 DEEPSEEK_API_KEY 为空 → AI 生成自动回退模板（确定性）；
AI 相关用例显式 monkeypatch _get_ai_client。
"""

import asyncio
import inspect
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db.database import async_session
from app.models.order import Order
from app.models.star_report import StarReport
from app.models.user import User
from app.utils.auth import create_token

# 固定测试周期（与 test_star_report.py 一致）
PERIOD = "2026-W33"
MONTH_PERIOD = "2026-08"

AI_WEEK_NOTE_JSON = '{"note": "这一周星象在缓慢转向，你抽到最多的牌，是一盏总在提醒你慢下来的灯。"}'
AI_WEEK_NOTE_JSON_B = '{"note": "重新生成的一周寄语，星光继续陪你。"}'
AI_MONTH_NOTE_JSON = '{"note": "这一个月，你在月光下走了很远：新月许愿，满月复盘，慢下来的日子里也给自己留了温柔。"}'
AI_MONTH_NOTE_JSON_B = '{"note": "重新生成的月度总评，星光依旧。"}'


# ── helpers ─────────────────────────────────────────────────────────────

def _seed_readings(uid: str, card_ids: list[int]) -> None:
    """周内 N 次占卜（created_at 依次落在周内）+ 周外 1 次（必须排除）。"""
    from app.models.astral_activity_log import AstralActivityLog
    from app.models.checkin import CheckIn
    from app.models.diary import DiaryEntry
    from app.models.horoscope import HoroscopeHistory
    from app.models.reading import DrawnCard, Reading
    from app.models.star_monthly_review import StarMonthlyReview

    async def _go() -> None:
        async with async_session() as session:
            for i, card_id in enumerate(card_ids):
                reading = Reading(
                    id=f"rlu-r-{uid[:6]}-{i}",
                    user_id=uid,
                    spread_type="daily",
                    theme="general",
                    created_at=datetime(2026, 8, 10, 10, 0, 0) + timedelta(days=i),
                )
                session.add(reading)
                session.add(DrawnCard(
                    reading_id=reading.id, card_id=card_id, position=0,
                    position_name="主牌", is_reversed=False,
                ))
            old = Reading(
                id=f"rlu-rold-{uid[:6]}",
                user_id=uid,
                spread_type="daily",
                theme="general",
                created_at=datetime(2026, 8, 1, 12, 0, 0),
            )
            session.add(old)
            session.add(DrawnCard(
                reading_id=old.id, card_id=5, position=0,
                position_name="主牌", is_reversed=False,
            ))
            await session.commit()

    asyncio.run(_go())


def _seed_stardust(uid: str) -> None:
    """周内 2 次签到 + 1 次节点活动 + 周外 1 次（必须排除）。"""
    from app.models.astral_activity_log import AstralActivityLog
    from app.models.checkin import CheckIn

    async def _go() -> None:
        async with async_session() as session:
            for d in (date(2026, 8, 11), date(2026, 8, 15)):
                session.add(CheckIn(user_id=uid, checkin_date=d))
            session.add(AstralActivityLog(
                user_id=uid, event_key="new_moon-2026-08-12", event_date=date(2026, 8, 12),
            ))
            session.add(CheckIn(user_id=uid, checkin_date=date(2026, 8, 2)))
            await session.commit()

    asyncio.run(_go())


def _seed_month_readings(uid: str, card_ids: list[int]) -> None:
    """月内 N 次占卜 + 月外 1 次（必须排除）。"""
    from app.models.reading import DrawnCard, Reading

    async def _go() -> None:
        async with async_session() as session:
            for i, card_id in enumerate(card_ids):
                reading = Reading(
                    id=f"rlu-m-{uid[:6]}-{i}",
                    user_id=uid,
                    spread_type="daily",
                    theme="general",
                    created_at=datetime(2026, 8, 1, 10, 0, 0) + timedelta(days=i),
                )
                session.add(reading)
                session.add(DrawnCard(
                    reading_id=reading.id, card_id=card_id, position=0,
                    position_name="主牌", is_reversed=False,
                ))
            old = Reading(
                id=f"rlu-mold-{uid[:6]}",
                user_id=uid,
                spread_type="daily",
                theme="general",
                created_at=datetime(2026, 7, 31, 12, 0, 0),
            )
            session.add(old)
            session.add(DrawnCard(
                reading_id=old.id, card_id=9, position=0,
                position_name="主牌", is_reversed=False,
            ))
            await session.commit()

    asyncio.run(_go())


def _seed_month_stardust(uid: str) -> None:
    """月内 2 次签到 + 1 次节点活动 + 月外 1 次（必须排除）。"""
    from app.models.astral_activity_log import AstralActivityLog
    from app.models.checkin import CheckIn

    async def _go() -> None:
        async with async_session() as session:
            for d in (date(2026, 8, 5), date(2026, 8, 20)):
                session.add(CheckIn(user_id=uid, checkin_date=d))
            session.add(AstralActivityLog(
                user_id=uid, event_key="full_moon-2026-08-26", event_date=date(2026, 8, 12),
            ))
            session.add(CheckIn(user_id=uid, checkin_date=date(2026, 7, 15)))
            await session.commit()

    asyncio.run(_go())


def _seed_star_monthly_review(
    uid: str, month: str, trend: str = "本月星光偏亮，情绪以平静为主。"
) -> None:
    """预置 star_monthly_reviews 缓存（手账段数据源）。"""
    from app.models.star_monthly_review import StarMonthlyReview

    async def _go() -> None:
        async with async_session() as session:
            session.add(StarMonthlyReview(
                user_id=uid,
                month=month,
                data=json.dumps({
                    "month": month,
                    "stats": {
                        "days_recorded": 12,
                        "bright_count": 8,
                        "dim_count": 1,
                        "bright_ratio": 0.6667,
                    },
                    "mood_series": [],
                    "star_color_counts": [],
                    "top_cards": [],
                    "trend_summary": trend,
                    "insight": None,
                    "next_guide": None,
                    "source": "ai",
                }, ensure_ascii=False),
            ))
            await session.commit()

    asyncio.run(_go())


def _new_user(openid: str, member: bool = False) -> tuple[str, dict[str, str]]:
    """创建隔离测试用户，返回 (user_id, auth_headers)。"""

    async def _go() -> tuple[str, str]:
        async with async_session() as session:
            user = User(openid=openid, nickname="解锁测试", is_member=member)
            session.add(user)
            await session.flush()
            token = create_token(user.id)
            await session.commit()
            return user.id, token

    uid, token = asyncio.run(_go())
    return uid, {"Authorization": f"Bearer {token}"}


def _patch_user(uid: str, **fields) -> None:
    """直接改用户列（模拟回调置位 / 到期等场景）。"""

    async def _go() -> None:
        async with async_session() as session:
            user = await session.get(User, uid)
            for k, v in fields.items():
                setattr(user, k, v)
            await session.commit()

    asyncio.run(_go())


def _get_user(uid: str) -> User:
    async def _go() -> User:
        async with async_session() as session:
            user = await session.get(User, uid)
            session.expunge(user)
            return user

    return asyncio.run(_go())


def _seed_cache(uid: str, report_type: str, period: str, data: dict, source: str) -> None:
    """直接写入 star_reports 缓存（poster / regenerate 回退用例用）。"""

    async def _go() -> None:
        async with async_session() as session:
            session.add(StarReport(
                user_id=uid,
                report_type=report_type,
                period_key=period,
                data=json.dumps(data, ensure_ascii=False),
                source=source,
            ))
            await session.commit()

    asyncio.run(_go())


def _cache_data(uid: str, report_type: str, period: str) -> dict | None:
    """读缓存 data JSON。"""

    async def _go() -> dict | None:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(StarReport).where(
                        StarReport.user_id == uid,
                        StarReport.report_type == report_type,
                        StarReport.period_key == period,
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return None
            session.expunge(row)
            return json.loads(row.data)

    return asyncio.run(_go())


def _cache_source(uid: str, report_type: str, period: str) -> str | None:
    async def _go() -> str | None:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(StarReport).where(
                        StarReport.user_id == uid,
                        StarReport.report_type == report_type,
                        StarReport.period_key == period,
                    )
                )
            ).scalar_one_or_none()
            return row.source if row else None

    return asyncio.run(_go())


def _seed_order(user_id: str, product_type: str, amount: float) -> str:
    """直插 pending 订单（回调测试用），返回 order_no。"""

    async def _go() -> str:
        async with async_session() as session:
            order = Order(
                user_id=user_id,
                order_no=f"TAROT{uuid.uuid4().hex[:10].upper()}",
                product_type=product_type,
                amount=amount,
                status="pending",
            )
            session.add(order)
            await session.flush()
            no = order.order_no
            await session.commit()
            return no

    return asyncio.run(_go())


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content

    async def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


class _FakeAIClient:
    def __init__(self, content: str):
        self.chat = SimpleNamespace(completions=_FakeCompletions(content))


def _boom():
    async def _raise(*a, **k):
        raise RuntimeError("ai down")

    return SimpleNamespace(chat=SimpleNamespace(completions=_raise))


# ═══════════════════════════════════════════════════════════════════════
# T7-3：商品注册 + 权益语义
# ═══════════════════════════════════════════════════════════════════════


class TestEntitlementSemantics:
    def test_report_products_registered(self):
        """PRODUCTS 注册 weekly_report 4.9 / monthly_report 19.9（单次购买）。"""
        from app.services.payment import PRODUCTS

        weekly = PRODUCTS["weekly_report"]
        assert weekly["price"] == 4.90
        assert weekly["type"] == "single_purchase"

        monthly = PRODUCTS["monthly_report"]
        assert monthly["price"] == 19.90
        assert monthly["type"] == "single_purchase"

    def test_is_member_active(self):
        """会员实时判定：有效期内 True；过期 False；expires_at=None（永续）True。"""
        from app.api.star_report import is_member_active

        uid, _ = _new_user("ent_member")
        _patch_user(uid, is_member=True)  # member_expires_at=None → 永续
        assert is_member_active(_get_user(uid)) is True

        uid_exp, _ = _new_user("ent_expired")
        _patch_user(uid_exp, is_member=True,
                    member_expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        assert is_member_active(_get_user(uid_exp)) is False

        uid_free, _ = _new_user("ent_free")
        assert is_member_active(_get_user(uid_free)) is False

    def test_can_read_full(self):
        """会员 或 对应解锁列；会员到期后旧解锁仍有效（单次购买是资产）。"""
        from app.api.star_report import can_read_full

        # 会员（永续）→ 周/月都全文
        uid_m, _ = _new_user("ent_member2")
        _patch_user(uid_m, is_member=True)
        assert can_read_full(_get_user(uid_m), "week") is True
        assert can_read_full(_get_user(uid_m), "month") is True

        # 非会员未解锁 → False
        uid_f, _ = _new_user("ent_free2")
        assert can_read_full(_get_user(uid_f), "week") is False
        assert can_read_full(_get_user(uid_f), "month") is False

        # 非会员解锁周报 → 仅周全文
        uid_w, _ = _new_user("ent_week")
        _patch_user(uid_w, weekly_report_unlocked=True)
        assert can_read_full(_get_user(uid_w), "week") is True
        assert can_read_full(_get_user(uid_w), "month") is False

        # 会员到期 + 已解锁月报 → 月仍全文
        uid_e, _ = _new_user("ent_exp_unlocked")
        _patch_user(uid_e, is_member=True, monthly_report_unlocked=True,
                    member_expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        assert can_read_full(_get_user(uid_e), "month") is True
        assert can_read_full(_get_user(uid_e), "week") is False, "到期会员未解锁周报应锁"

    def test_week_report_unlocked_nonmember_full(self, client: TestClient, monkeypatch):
        """非会员 + weekly_report_unlocked → /report/week 全文 locked=False。"""

        uid, headers = _new_user(f"unl_week_{uuid.uuid4().hex[:6]}")
        _patch_user(uid, weekly_report_unlocked=True)
        _seed_readings(uid, [1, 2])
        _seed_stardust(uid)
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)

        resp = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["locked"] is False
        assert d["preview"] is False
        assert set(d["report"].keys()) == {"curve", "stardust", "cards", "color_band", "note"}
        assert d["report"]["stardust"]["total"] == 3

    def test_week_report_unlocked_no_member_flag(self, client: TestClient, monkeypatch):
        """解锁但 is_member=False：靠解锁列放行，不依赖会员位。"""

        uid, headers = _new_user(f"unl_week2_{uuid.uuid4().hex[:6]}")
        _patch_user(uid, weekly_report_unlocked=True)
        _seed_readings(uid, [1])
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)

        resp = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["locked"] is False

    def test_week_report_expired_member_locked(self, client: TestClient, monkeypatch):
        """会员到期未解锁 → 回到 locked 预览（实时判定）。"""

        uid, headers = _new_user(f"exp_{uuid.uuid4().hex[:6]}", member=True)
        _patch_user(uid, member_expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        _seed_readings(uid, [1])
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)

        resp = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp.status_code == 200
        d = resp.json()
        assert d["locked"] is True
        assert set(d["report"].keys()) == {"curve", "note"}, "到期未解锁应预览"

    def test_month_report_unlocked_nonmember_full(self, client: TestClient, monkeypatch):
        """非会员 + monthly_report_unlocked → /report/month 全文 locked=False。"""
        uid, headers = _new_user(f"unl_month_{uuid.uuid4().hex[:6]}")
        _patch_user(uid, monthly_report_unlocked=True)
        _seed_month_readings(uid, [1, 2])
        _seed_month_stardust(uid)
        _seed_star_monthly_review(uid, "2026-08")
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)

        resp = client.get(f"/report/month?period={MONTH_PERIOD}", headers=headers)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["locked"] is False
        assert set(d["report"].keys()) == {
            "astral_events", "journal", "cards", "stardust", "outlook", "note",
        }
        assert d["report"]["journal"]["active_days"] == 12


# ═══════════════════════════════════════════════════════════════════════
# T7-3：unlock 下单
# ═══════════════════════════════════════════════════════════════════════


class TestUnlockOrder:
    def test_unlock_requires_auth(self, client: TestClient):
        assert client.post("/report/week/unlock").status_code == 401

    def test_unlock_invalid_type_404(self, client: TestClient):
        uid, headers = _new_user(f"unl_bad_{uuid.uuid4().hex[:6]}")
        assert client.post("/report/year/unlock", headers=headers).status_code == 404

    def test_unlock_week_creates_order(self, client: TestClient, monkeypatch):
        """非会员 unlock → 复用 orders 管线：订单 product_type=weekly_report、4.9 元。"""
        monkeypatch.setattr(settings, "PAY_CHANNEL", "jsapi")
        monkeypatch.setattr(
            "app.api.orders.create_order_params",
            lambda *a, **k: {"timeStamp": "1", "nonceStr": "n", "package": "prepay_id=x",
                             "signType": "RSA", "paySign": "sig"},
        )
        uid, headers = _new_user(f"unl_ord_{uuid.uuid4().hex[:6]}")
        # 未解锁 → 下单成功
        resp = client.post("/report/week/unlock", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["order_no"]
        assert data["product_name"] == "星光一周周报"
        assert float(data["amount"]) == 4.9
        assert data["payment_params"]["paySign"] == "sig"
        assert data["xpay_params"] is None

        # 订单落库：product_type / 金额 / pending
        async def _check() -> Order | None:
            async with async_session() as session:
                row = (
                    await session.execute(
                        select(Order).where(Order.order_no == data["order_no"])
                    )
                ).scalar_one_or_none()
                if row:
                    session.expunge(row)
                return row

        order = asyncio.run(_check())
        assert order is not None
        assert order.user_id == uid
        assert order.product_type == "weekly_report"
        assert float(order.amount) == 4.9
        assert order.status == "pending"

    def test_unlock_month_creates_order(self, client: TestClient, monkeypatch):
        """月报 unlock → product_type=monthly_report、19.9 元。"""
        monkeypatch.setattr(settings, "PAY_CHANNEL", "jsapi")
        monkeypatch.setattr(
            "app.api.orders.create_order_params",
            lambda *a, **k: {"paySign": "sig"},
        )
        uid, headers = _new_user(f"unl_mord_{uuid.uuid4().hex[:6]}")
        resp = client.post("/report/month/unlock", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["product_name"] == "星光月度卷轴"
        assert float(data["amount"]) == 19.9

        async def _check() -> Order | None:
            async with async_session() as session:
                row = (
                    await session.execute(
                        select(Order).where(Order.order_no == data["order_no"])
                    )
                ).scalar_one_or_none()
                if row:
                    session.expunge(row)
                return row

        order = asyncio.run(_check())
        assert order.product_type == "monthly_report"
        assert float(order.amount) == 19.9

    def test_unlock_member_400(self, client: TestClient, monkeypatch):
        """会员 → 无需下单，400「你已拥有这份星光 ✦」。"""
        monkeypatch.setattr(settings, "PAY_CHANNEL", "jsapi")
        uid, headers = _new_user(f"unl_mem_{uuid.uuid4().hex[:6]}", member=True)
        resp = client.post("/report/week/unlock", headers=headers)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "你已拥有这份星光 ✦"

    def test_unlock_already_unlocked_400(self, client: TestClient, monkeypatch):
        """已解锁重复 unlock → 400（幂等防重复扣费）。"""
        monkeypatch.setattr(settings, "PAY_CHANNEL", "jsapi")
        monkeypatch.setattr(
            "app.api.orders.create_order_params",
            lambda *a, **k: {"paySign": "sig"},
        )
        uid, headers = _new_user(f"unl_done_{uuid.uuid4().hex[:6]}")
        _patch_user(uid, weekly_report_unlocked=True)
        resp = client.post("/report/week/unlock", headers=headers)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "你已拥有这份星光 ✦"

        # 月报解锁不受影响
        resp_month = client.post("/report/month/unlock", headers=headers)
        assert resp_month.status_code == 200, "周已解锁不应阻塞月报下单"

    def test_unlock_xpay_missing_mapping_400_then_mapped_ok(
        self, client: TestClient, monkeypatch
    ):
        """xpay 通道两态：道具未映射 → 400「该商品即将上线」；映射后下单成功且 signData 含正确 productId。"""
        from app.services.session_key import encrypt_session_key

        monkeypatch.setattr(settings, "PAY_CHANNEL", "xpay")
        monkeypatch.setattr(settings, "WX_XPAY_ENV", 0)
        uid, headers = _new_user(f"xpay_unl_{uuid.uuid4().hex[:6]}")

        # 状态一：XPAY_PRODUCT_MAP 无 weekly_report（部署前缺映射）→ 400 降级提示
        monkeypatch.setattr(
            settings, "XPAY_PRODUCT_MAP",
            json.dumps({"single_reading": "single_reading"}),
        )
        resp = client.post("/report/week/unlock", headers=headers)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "该商品即将上线,敬请期待"

        # 状态二：补齐映射 + 落库加密 session_key（模拟真实登录）→ 下单成功
        monkeypatch.setattr(
            settings, "XPAY_PRODUCT_MAP",
            json.dumps({"weekly_report": "weekly_report"}),
        )

        async def _set_session_key() -> None:
            async with async_session() as session:
                user = await session.get(User, uid)
                user.session_key_encrypted = encrypt_session_key("xpay-test-session-key")
                await session.commit()

        asyncio.run(_set_session_key())

        resp2 = client.post("/report/week/unlock", headers=headers)
        assert resp2.status_code == 200, resp2.text
        data = resp2.json()
        assert data["payment_params"] is None, "xpay 通道不应返回 jsapi payment_params"
        assert data["xpay_params"] is not None
        payload = json.loads(data["xpay_params"]["signData"])
        assert payload["productId"] == "weekly_report"
        assert payload["attach"] == "weekly_report"
        assert data["product_name"] == "星光一周周报"
        assert float(data["amount"]) == 4.9


# ═══════════════════════════════════════════════════════════════════════
# T7-3：支付回调 → 权益置位（幂等）
# ═══════════════════════════════════════════════════════════════════════


def _post_callback(client: TestClient, order_no: str, openid: str, total_fen: int,
                   monkeypatch) -> None:
    """模拟微信 V3 回调（签名/解密 monkeypatch 放行），断言 200。"""
    monkeypatch.setattr(settings, "WECHAT_PLATFORM_CERT_SERIAL", "SER1")
    monkeypatch.setattr(settings, "WECHAT_PLATFORM_CERT", "cert")
    monkeypatch.setattr(
        "app.services.payment.verify_wechat_v3_signature", lambda *a, **k: True
    )
    txn = json.dumps({
        "trade_state": "SUCCESS",
        "out_trade_no": order_no,
        "amount": {"total": total_fen, "currency": "CNY"},
        "payer": {"openid": openid},
    })
    monkeypatch.setattr(
        "app.services.payment.decrypt_wechat_v3_resource",
        lambda *a, **k: txn,
    )
    resp = client.post(
        "/orders/callback",
        json={"resource": {"ciphertext": "x", "associated_data": "", "nonce": ""}},
        headers={
            "Wechatpay-Signature": "sig",
            "Wechatpay-Timestamp": "1",
            "Wechatpay-Nonce": "nonce",
            "Wechatpay-Serial": "SER1",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"code": "SUCCESS"}


class TestPaymentCallbackEntitlement:
    def test_callback_weekly_report_sets_flag_idempotent(
        self, client: TestClient, monkeypatch
    ):
        """weekly_report 支付回调 → weekly_report_unlocked=True；重复回调幂等。"""
        uid, headers = _new_user(f"cb_w_{uuid.uuid4().hex[:6]}")
        openid = _get_user(uid).openid
        order_no = _seed_order(uid, "weekly_report", 4.90)
        assert _get_user(uid).weekly_report_unlocked is False

        _post_callback(client, order_no, openid, 490, monkeypatch)
        assert _get_user(uid).weekly_report_unlocked is True

        # 重复回调（微信可能重发）→ 幂等，不重复置位不报错
        _post_callback(client, order_no, openid, 490, monkeypatch)
        assert _get_user(uid).weekly_report_unlocked is True

        # 解锁后 /report/week 全文

        _seed_readings(uid, [1])
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)
        resp = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["locked"] is False

    def test_callback_monthly_report_sets_flag(self, client: TestClient, monkeypatch):
        """monthly_report 支付回调 → monthly_report_unlocked=True。"""
        uid, _ = _new_user(f"cb_m_{uuid.uuid4().hex[:6]}")
        openid = _get_user(uid).openid
        order_no = _seed_order(uid, "monthly_report", 19.90)

        _post_callback(client, order_no, openid, 1990, monkeypatch)
        assert _get_user(uid).monthly_report_unlocked is True

    def test_callback_benefit_branch_guard(self):
        """回调权益分支守卫：两商品分支存在（代码路径可读性）。"""
        from app.api import orders as orders_api

        source = inspect.getsource(orders_api)
        assert 'order.product_type == "weekly_report"' in source
        assert "user.weekly_report_unlocked = True" in source
        assert 'order.product_type == "monthly_report"' in source
        assert "user.monthly_report_unlocked = True" in source


# ═══════════════════════════════════════════════════════════════════════
# T7-3：regenerate（仅会员 · 周/月各 1 次/周期 · AI 失败回退原缓存）
# ═══════════════════════════════════════════════════════════════════════


class TestRegenerate:
    def test_regenerate_requires_auth(self, client: TestClient):
        assert client.post("/report/week/regenerate").status_code == 401

    def test_regenerate_invalid_type_404(self, client: TestClient):
        uid, headers = _new_user(f"rg_bad_{uuid.uuid4().hex[:6]}", member=True)
        assert client.post("/report/year/regenerate", headers=headers).status_code == 404

    def test_regenerate_nonmember_403(self, client: TestClient):
        uid, headers = _new_user(f"rg_free_{uuid.uuid4().hex[:6]}")
        resp = client.post(f"/report/week/regenerate?period={PERIOD}", headers=headers)
        assert resp.status_code == 403

    def test_regenerate_member_ok_overwrites_and_rate_limit(
        self, client: TestClient, monkeypatch
    ):
        """会员 regenerate：首次覆盖缓存（内容变化）；同周期二次 → 429。"""

        uid, headers = _new_user(f"rg_ok_{uuid.uuid4().hex[:6]}", member=True)
        _seed_readings(uid, [1, 2])

        # 首次 GET：AI 寄语 A
        fake_a = _FakeAIClient(AI_WEEK_NOTE_JSON)
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: fake_a)
        r1 = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert r1.status_code == 200
        assert r1.json()["source"] == "ai"
        note_a = r1.json()["report"]["note"]

        # regenerate：AI 寄语 B → 覆盖缓存
        fake_b = _FakeAIClient(AI_WEEK_NOTE_JSON_B)
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: fake_b)
        r2 = client.post(f"/report/week/regenerate?period={PERIOD}", headers=headers)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["locked"] is False
        assert d2["cached"] is False
        assert d2["source"] == "ai"
        assert d2["report"]["note"] != note_a, "regenerate 应重新生成内容"
        assert _cache_data(uid, "week", PERIOD)["note"] == d2["report"]["note"]

        # 同周期二次 → 429
        r3 = client.post(f"/report/week/regenerate?period={PERIOD}", headers=headers)
        assert r3.status_code == 429
        assert r3.json()["detail"] == "这份星光已是最新 ✦"

    def test_regenerate_week_and_month_independent_rate_limits(
        self, client: TestClient, monkeypatch
    ):
        """周/月限流独立：周已用不阻塞月。"""

        uid, headers = _new_user(f"rg_ind_{uuid.uuid4().hex[:6]}", member=True)
        _seed_readings(uid, [1])
        _seed_month_readings(uid, [1])

        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)
        rw = client.post(f"/report/week/regenerate?period={PERIOD}", headers=headers)
        assert rw.status_code == 200, rw.text
        rm = client.post(
            f"/report/month/regenerate?period={MONTH_PERIOD}", headers=headers
        )
        assert rm.status_code == 200, rm.text
        # 月内占卜 = 周种子(08-10) + 月种子(08-01) + 周种子的"周外"占卜(08-01) = 3；
        # 07-31 真月外占卜被排除
        assert rm.json()["report"]["cards"]["readings_count"] == 3
        # 各自第二次 → 429
        assert client.post(
            f"/report/week/regenerate?period={PERIOD}", headers=headers
        ).status_code == 429
        assert client.post(
            f"/report/month/regenerate?period={MONTH_PERIOD}", headers=headers
        ).status_code == 429

    def test_regenerate_ai_fails_keeps_original_cache(
        self, client: TestClient, monkeypatch
    ):
        """AI 抛异常 → 回退原缓存不覆盖（返回原报告，source 不变）。"""

        uid, headers = _new_user(f"rg_boom_{uuid.uuid4().hex[:6]}", member=True)
        _seed_readings(uid, [1, 2])

        # 预置 ai 源缓存（模拟此前 AI 成功生成的全文）
        original = {
            "curve": [{"date": "2026-08-10", "total": None} for _ in range(7)],
            "stardust": {"checkin_days": 0, "activity_events": 0, "total": 0},
            "cards": {"readings_count": 2, "most_card": None, "card_list": []},
            "color_band": [{"date": "2026-08-10", "star_color": "#FFD700"}] * 7,
            "note": "原版 AI 寄语：星光一直陪着你。",
        }
        _seed_cache(uid, "week", PERIOD, original, "ai")

        # regenerate：AI 抛异常 → 走降级 → 回退原缓存
        monkeypatch.setattr("app.services.star_reports._get_ai_client", _boom)
        resp = client.post(f"/report/week/regenerate?period={PERIOD}", headers=headers)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["source"] == "ai", "AI 失败应保留原 source"
        assert d["report"]["note"] == original["note"], "应返回原报告"
        assert _cache_data(uid, "week", PERIOD)["note"] == original["note"], \
            "原缓存不应被降级内容覆盖"
        assert _cache_source(uid, "week", PERIOD) == "ai"

    def test_regenerate_month_ai_fails_keeps_original_cache(
        self, client: TestClient, monkeypatch
    ):
        """月 regenerate：AI 失败同样回退原缓存。"""

        uid, headers = _new_user(f"rg_mboom_{uuid.uuid4().hex[:6]}", member=True)
        _seed_month_readings(uid, [1])

        original = {
            "astral_events": [],
            "journal": None,
            "cards": {"readings_count": 1, "top3": []},
            "stardust": {"estimated": 0, "tier_name": "微光"},
            "outlook": {"first_new_moon": None, "first_full_moon": None,
                        "first_retrograde": None, "tips": []},
            "note": "原版月总评：这一个月星光温柔。",
        }
        _seed_cache(uid, "month", MONTH_PERIOD, original, "ai")

        monkeypatch.setattr("app.services.star_reports._get_ai_client", _boom)
        resp = client.post(
            f"/report/month/regenerate?period={MONTH_PERIOD}", headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["source"] == "ai"
        assert resp.json()["report"]["note"] == original["note"]
        assert _cache_data(uid, "month", MONTH_PERIOD)["note"] == original["note"]


# ═══════════════════════════════════════════════════════════════════════
# T7-4：月报海报数据端点（脱敏）
# ═══════════════════════════════════════════════════════════════════════


class TestMonthPoster:
    def test_poster_requires_auth(self, client: TestClient):
        assert client.get("/report/month/poster").status_code == 401

    def test_poster_invalid_period_422(self, client: TestClient):
        uid, headers = _new_user(f"ps_bad_{uuid.uuid4().hex[:6]}")
        assert client.get(
            "/report/month/poster?period=abc", headers=headers
        ).status_code == 422

    def test_poster_no_cache_404(self, client: TestClient):
        uid, headers = _new_user(f"ps_noc_{uuid.uuid4().hex[:6]}", member=True)
        resp = client.get(f"/report/month/poster?period={MONTH_PERIOD}", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "先看报告，再分享星光 ✦"

    def test_poster_nonmember_without_unlock_403(self, client: TestClient, monkeypatch):
        """非会员未解锁 → 403（前端已拦，后端兜底）。"""
        uid, headers = _new_user(f"ps_free_{uuid.uuid4().hex[:6]}")
        _seed_month_readings(uid, [1])
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)
        # 先生成缓存（预览态同样落全文缓存）
        r = client.get(f"/report/month?period={MONTH_PERIOD}", headers=headers)
        assert r.status_code == 200
        resp = client.get(f"/report/month/poster?period={MONTH_PERIOD}", headers=headers)
        assert resp.status_code == 403

    def test_poster_member_full_desensitized(self, client: TestClient, monkeypatch):
        """会员：字段完整 + 键集脱敏（无昵称/无原文统计明细/无手账内容）。"""
        uid, headers = _new_user(f"ps_mem_{uuid.uuid4().hex[:6]}", member=True)
        _seed_month_readings(uid, [1, 1, 2])
        _seed_month_stardust(uid)
        _seed_star_monthly_review(uid, "2026-08", trend="本月星光偏亮，情绪以平静为主。")

        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)
        r = client.get(f"/report/month?period={MONTH_PERIOD}", headers=headers)
        assert r.status_code == 200, r.text

        resp = client.get(f"/report/month/poster?period={MONTH_PERIOD}", headers=headers)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        # 键集精确断言（脱敏契约）
        assert set(d.keys()) == {
            "period", "tier_name", "core_numbers", "ai_sentence", "share_text", "disclaimer",
        }
        assert d["period"] == MONTH_PERIOD
        assert d["tier_name"], "应有星阶名"
        assert d["core_numbers"] == {
            "active_days": 12,
            "readings_count": 3,
            "stardust_estimated": 3,
        }
        assert d["ai_sentence"], "应有 AI 寄语一句"
        assert len(d["ai_sentence"]) <= 40, "AI 寄语应截断 40 字"
        assert d["share_text"] == "我的2026年八月星象月报 · 本月点亮 12 颗星 ✦"
        assert d["disclaimer"] == "仅供娱乐 · 星光映照"

        # 脱敏断言：响应序列化后不含昵称/手账原文/统计明细字段
        blob = json.dumps(d, ensure_ascii=False)
        assert "nickname" not in blob
        assert "trend" not in blob
        assert "bright_ratio" not in blob
        assert "top3" not in blob
        assert "card" not in blob
        assert "日记" not in blob

    def test_poster_unlocked_nonmember_200(self, client: TestClient, monkeypatch):
        """非会员已解锁月报 → 海报 200。"""
        uid, headers = _new_user(f"ps_unl_{uuid.uuid4().hex[:6]}")
        _patch_user(uid, monthly_report_unlocked=True)
        _seed_month_readings(uid, [1])
        _seed_star_monthly_review(uid, "2026-08")
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)
        r = client.get(f"/report/month?period={MONTH_PERIOD}", headers=headers)
        assert r.status_code == 200
        resp = client.get(f"/report/month/poster?period={MONTH_PERIOD}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["core_numbers"]["active_days"] == 12


# ═══════════════════════════════════════════════════════════════════════
# 迁移链：users 两 BOOL 解锁列
# ═══════════════════════════════════════════════════════════════════════


def test_alembic_migration_report_unlock_flags(tmp_path, monkeypatch):
    """迁移链：users 表 weekly/monthly_report_unlocked 可升级、可回滚。"""
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent
    db_path = tmp_path / "migration_unlock.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    cfg = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(cfg, "head")

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    assert "weekly_report_unlocked" in cols
    assert "monthly_report_unlocked" in cols

    command.downgrade(cfg, "base")
    cols_after = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    conn.close()
    assert "weekly_report_unlocked" not in cols_after
    assert "monthly_report_unlocked" not in cols_after
