"""
Tests for the 21:00 daily push scheduler (留存功能第一批 · 功能 3).

Covers:
- template not configured → skipped_config + no crash
- before 21:00 → not_due
- already sent today → not_due (dedup)
- due + subscribers → send attempted (status sent, failures counted when
  the WeChat token fetch is impossible in tests)
- run_daily_push_loop exits immediately when template is unconfigured
- deterministic card pick matches /cards/daily for the same user
"""

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db.database import async_session
from app.models.card import TarotCard
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services import daily_push
from app.services.daily_card import pick_daily_card

# 北京时间 21:30 / 20:00（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))
NOW_2130 = datetime(2026, 8, 8, 21, 30, tzinfo=BEIJING_TZ)
NOW_2000 = datetime(2026, 8, 8, 20, 0, tzinfo=BEIJING_TZ)


def _auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/auth/dev-login?member=true",
        headers={"X-Dev-Key": settings.DEV_LOGIN_KEY},
    )
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _reset_state(monkeypatch) -> None:
    """Isolate the module state + state file from the dev machine."""
    monkeypatch.setattr(daily_push, "_last_sent_date", None)
    monkeypatch.setattr(daily_push, "_last_config_error_date", None)
    monkeypatch.setattr(daily_push, "_load_state", lambda: None)
    monkeypatch.setattr(daily_push, "_save_state", lambda: None)


def _send_if_due(now: datetime) -> dict:
    """Run send_daily_push_if_due with a fresh session on the test loop."""

    async def _go():
        async with async_session() as session:
            return await daily_push.send_daily_push_if_due(session, now)

    return asyncio.run(_go())


async def _insert_subscription(user_id: str, openid: str) -> None:
    async with async_session() as session:
        session.add(
            PushSubscription(
                user_id=user_id,
                openid=openid,
                template_id="TEMPLATE_DAILY_CARD",
                subscribed=True,
            )
        )
        await session.commit()


def test_push_skipped_when_template_unconfigured(client: TestClient, monkeypatch):
    """WX_TEMPLATE_DAILY_CARD 为空（默认）→ skipped_config，不崩溃不发请求."""
    _reset_state(monkeypatch)
    result = _send_if_due(NOW_2130)
    assert result["status"] == "skipped_config"


def test_push_not_due_before_21(client: TestClient, monkeypatch):
    """20:00 未到推送时间 → not_due."""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    result = _send_if_due(NOW_2000)
    assert result["status"] == "not_due"


def test_push_dedup_after_send(client: TestClient, monkeypatch):
    """当天已发送 → not_due（去重，不重复推送）."""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    monkeypatch.setattr(daily_push, "_last_sent_date", "2026-08-08")
    result = _send_if_due(NOW_2130)
    assert result["status"] == "not_due"


def test_push_sends_to_subscribers(client: TestClient, monkeypatch):
    """
    21:30 + 模板已配置 + 有订阅用户 → 尝试逐人发送。

    Tests have no WECHAT_APP_ID/SECRET, so the access-token fetch raises —
    each send counts as failed, but the loop completes without crashing and
    marks the day as sent (no re-send on the next check).
    """
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")

    user_id = "00000000-0000-0000-0000-0000000000d1"
    asyncio.run(_insert_subscription(user_id, "o_test_openid_001"))
    asyncio.run(_insert_subscription(user_id, "o_test_openid_002"))

    result = _send_if_due(NOW_2130)
    assert result["status"] == "sent"
    assert result["sent"] == 0
    assert result["failed"] == 2  # both failed at token fetch (no crash)
    assert daily_push._last_sent_date == "2026-08-08"

    # ── 已标记发送 → 再次调用 not_due（去重生效）──
    result2 = _send_if_due(NOW_2130)
    assert result2["status"] == "not_due"


def test_push_loop_exits_when_template_unconfigured(client: TestClient, monkeypatch):
    """模板未配置时后台任务立即退出，不空转."""
    result = asyncio.run(daily_push.run_daily_push_loop(interval_seconds=1))
    assert result is None


def test_push_card_matches_daily_card_endpoint(client: TestClient):
    """晚间推送选牌与 /cards/daily 完全一致（同一用户同一天同一张牌）."""
    headers = _auth_headers(client)
    resp = client.get("/cards/daily", headers=headers)
    assert resp.status_code == 200
    api_card_id = resp.json()["id"]

    async def _get_user_id() -> str:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.openid == "dev_test_user_001")
            )
            return result.scalar_one().id

    user_id = asyncio.run(_get_user_id())

    async def _compare() -> None:
        async with async_session() as session:
            result = await session.execute(select(TarotCard).order_by(TarotCard.id))
            cards = list(result.scalars().all())
        picked = pick_daily_card(cards, user_id)
        assert picked.id == api_card_id

    asyncio.run(_compare())
