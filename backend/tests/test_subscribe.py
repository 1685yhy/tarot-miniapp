"""
星光晨讯（Task 5）：订阅额度 + 定时发送测试。

覆盖：
- POST /notify/subscribe-grant：auth 后 quota+1（首次 1、再次 +1）；未登录 401
- 7:37 晨讯发送：有额度且未发过今日 → 发送成功，quota-1、last_sent_date==今天
- 同日重复发送被跳过（批标记 _morning_sent_date + 逐人 last_sent_date 原子认领双重去重）
- 并发/崩溃窗口：已被认领（last_sent_date==今天）的用户即使批标记未置位也不双发
- 发送失败（微信 errcode!=0）：不扣额度、认领回退 NULL，下一轮循环重试成功
- quota==0 不发；未到 7:37 → not_due；模板未配置 → skipped_config
- build_starlight_morning_data 内容含今日星光一句话（能量+星光数）/ 宜忌 / 日期 / 星光色
- admin POST /notify/send-daily：鉴权（401/403）走 HTTP；发送行为走 service 层
  固定时间注入（08:00），不依赖真实系统时间 07:37 门
- 防疲劳：21:00 晚间推送跳过当日已收到星光晨讯的用户（每天最多 1 条）
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.config import settings
from app.db.database import async_session
from app.models.subscribe_quota import SubscribeQuota
from app.models.user import User
from app.services import daily_push
from app.services.energy_engine import build_today_guidance
from app.utils.auth import create_token

# 北京时间（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))
NOW_0737 = datetime(2026, 8, 10, 7, 37, tzinfo=BEIJING_TZ)
NOW_0730 = datetime(2026, 8, 10, 7, 30, tzinfo=BEIJING_TZ)
NOW_0800 = datetime(2026, 8, 10, 8, 0, tzinfo=BEIJING_TZ)  # 已过 7:37 门，固定注入
TODAY = NOW_0737.date()


def _new_user(openid: str) -> tuple[dict[str, str], str]:
    """创建隔离测试用户并返回（鉴权头, user_id）。"""

    async def _go() -> tuple[str, str]:
        async with async_session() as session:
            user = User(openid=openid, nickname="晨讯专用")
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return token, user.id

    token, user_id = asyncio.run(_go())
    return {"Authorization": f"Bearer {token}"}, user_id


def _reset_state(monkeypatch) -> None:
    """隔离模块状态 + 状态文件（与 test_daily_push 同模式）。"""
    monkeypatch.setattr(daily_push, "_morning_sent_date", None)
    monkeypatch.setattr(daily_push, "_last_sent_date", None)
    monkeypatch.setattr(daily_push, "_last_config_error_date", None)
    monkeypatch.setattr(daily_push, "_morning_fail_counts", {})
    monkeypatch.setattr(daily_push, "_night_fail_counts", {})
    monkeypatch.setattr(daily_push, "_load_state", lambda: None)
    monkeypatch.setattr(daily_push, "_save_state", lambda: None)


def _morning_send(now: datetime) -> dict:
    """运行 send_starlight_morning_if_due（测试 loop 上开新会话）。"""

    async def _go():
        async with async_session() as session:
            return await daily_push.send_starlight_morning_if_due(session, now)

    return asyncio.run(_go())


def _evening_send(now: datetime) -> dict:
    """运行 send_daily_push_if_due（测试 loop 上开新会话）。"""

    async def _go():
        async with async_session() as session:
            return await daily_push.send_daily_push_if_due(session, now)

    return asyncio.run(_go())


async def _seed_quota(user_id: str, quota: int) -> None:
    async with async_session() as session:
        session.add(SubscribeQuota(user_id=user_id, quota_available=quota))
        await session.commit()


async def _clean_quotas() -> None:
    """清空 SubscribeQuota（测试共享同一 SQLite，防止前序测试的额度行干扰发送选择）。"""
    async with async_session() as session:
        await session.execute(delete(SubscribeQuota))
        await session.commit()


@pytest.fixture
def clean_quotas():
    """发送类用例前后清空订阅额度表（隔离用例间状态）。"""
    asyncio.run(_clean_quotas())
    yield
    asyncio.run(_clean_quotas())


async def _get_quota(user_id: str) -> SubscribeQuota | None:
    async with async_session() as session:
        result = await session.execute(
            select(SubscribeQuota).where(SubscribeQuota.user_id == user_id)
        )
        return result.scalar_one_or_none()


def _fake_wechat_ok(monkeypatch, calls: list | None = None) -> None:
    """拦截微信订阅消息发送（errcode=0 成功），记录调用参数。"""

    async def _fake_send(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(daily_push, "send_subscribe_message", _fake_send)


# ══════════════════════════════════════════════════════════════
# POST /notify/subscribe-grant
# ══════════════════════════════════════════════════════════════


def test_grant_requires_auth(client: TestClient):
    """未登录 → 401。"""
    resp = client.post("/notify/subscribe-grant")
    assert resp.status_code == 401


def test_grant_increments_quota(client: TestClient):
    """auth 后 quota+1：首次 1，再次授权 +1 → 2。"""
    headers, user_id = _new_user("grant_user_001")

    resp = client.post("/notify/subscribe-grant", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert resp.json()["quota_available"] == 1

    resp2 = client.post("/notify/subscribe-grant", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["quota_available"] == 2

    quota = asyncio.run(_get_quota(user_id))
    assert quota is not None
    assert quota.quota_available == 2


# ══════════════════════════════════════════════════════════════
# 7:37 星光晨讯发送（按额度消费）
# ══════════════════════════════════════════════════════════════


def test_morning_send_consumes_quota_and_marks_date(client: TestClient, monkeypatch, clean_quotas):
    """有额度未发过今日 → 发送成功；quota-1、last_sent_date==今天。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, user_id = _new_user("morning_send_001")
    asyncio.run(_seed_quota(user_id, 1))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _morning_send(NOW_0737)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert len(calls) == 1
    assert calls[0]["openid"] == "morning_send_001"
    assert "thing1" in calls[0]["data"]  # 模板数据按 thing1/thing2/date3/thing4 组装

    quota = asyncio.run(_get_quota(user_id))
    assert quota is not None
    assert quota.quota_available == 0
    assert quota.last_sent_date == TODAY


def test_morning_same_day_skip(client: TestClient, monkeypatch, clean_quotas):
    """同日重复发送被跳过：批标记后 not_due；逐人 last_sent_date 挡住重选。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, user_id = _new_user("morning_skip_001")
    asyncio.run(_seed_quota(user_id, 3))  # 3 条额度 → 当天也只发 1 条

    _fake_wechat_ok(monkeypatch)

    first = _morning_send(NOW_0737)
    assert first["status"] == "sent"
    assert first["sent"] == 1
    quota = asyncio.run(_get_quota(user_id))
    assert quota.quota_available == 2  # 消耗 1 条，剩 2

    # 同一天再跑 → 批量标记生效 → not_due
    second = _morning_send(NOW_0737)
    assert second["status"] == "not_due"

    # 即使绕过批标记，last_sent_date==今天 → 该用户不再被选中（同日最多 1 条）
    monkeypatch.setattr(daily_push, "_morning_sent_date", None)
    third = _morning_send(NOW_0737)
    assert third["status"] == "no_subscribers"
    quota2 = asyncio.run(_get_quota(user_id))
    assert quota2.quota_available == 2


def test_morning_no_send_when_quota_zero(client: TestClient, monkeypatch, clean_quotas):
    """quota==0 → 不发。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, user_id = _new_user("morning_zero_001")
    asyncio.run(_seed_quota(user_id, 0))

    _fake_wechat_ok(monkeypatch)

    result = _morning_send(NOW_0737)
    assert result["status"] == "no_subscribers"


def test_morning_not_due_before_0737(client: TestClient, monkeypatch, clean_quotas):
    """07:30 未到 7:37 → not_due。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, user_id = _new_user("morning_early_001")
    asyncio.run(_seed_quota(user_id, 1))

    result = _morning_send(NOW_0730)
    assert result["status"] == "not_due"


def test_morning_skipped_when_template_unconfigured(client: TestClient, monkeypatch):
    """模板未配置（默认）→ skipped_config，不崩溃不发请求。"""
    _reset_state(monkeypatch)
    result = _morning_send(NOW_0737)
    assert result["status"] == "skipped_config"


def test_morning_send_failure_keeps_quota_and_retries(
    client: TestClient, monkeypatch, clean_quotas
):
    """微信 errcode!=0 → 不扣额度、认领回退 NULL；下一轮循环重试成功。

    钉住设计决策：发送失败不扣额度（微信临时故障不烧用户授权），
    且 last_sent_date 回退为 NULL（允许补发，而非当天永远缺席）。
    """
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, user_id = _new_user("morning_fail_001")
    asyncio.run(_seed_quota(user_id, 1))

    async def _fake_fail(**kwargs):
        return {"errcode": 40003, "errmsg": "invalid openid"}

    monkeypatch.setattr(daily_push, "send_subscribe_message", _fake_fail)

    result = _morning_send(NOW_0737)
    assert result["status"] == "sent"
    assert result["sent"] == 0
    assert result["failed"] == 1

    quota = asyncio.run(_get_quota(user_id))
    assert quota.quota_available == 1     # 失败不扣额度
    assert quota.last_sent_date is None   # 认领已回退 → 允许重试

    # 微信恢复 → 下一轮循环（批标记因有失败未置位）重试成功
    _fake_wechat_ok(monkeypatch)
    retry = _morning_send(NOW_0737)
    assert retry["status"] == "sent"
    assert retry["sent"] == 1
    assert retry["failed"] == 0

    quota2 = asyncio.run(_get_quota(user_id))
    assert quota2.quota_available == 0
    assert quota2.last_sent_date == TODAY


def test_morning_retry_capped_3_per_day(client: TestClient, monkeypatch, clean_quotas):
    """失败退避（最终审查 F-2）：同一用户当日最多尝试 3 次，达上限后本日
    不再尝试该用户；次日日期变化计数自动重置。

    微信持续 errcode!=0 时，认领回退照旧（不扣额度、允许修复后补发），
    但不再每 5 分钟循环全天重试烧配额刷日志。
    """
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, user_id = _new_user("morning_cap_001")
    asyncio.run(_seed_quota(user_id, 1))

    calls: list = []

    async def _fake_fail(**kwargs):
        calls.append(kwargs["openid"])
        return {"errcode": 40003, "errmsg": "invalid openid"}

    monkeypatch.setattr(daily_push, "send_subscribe_message", _fake_fail)

    # ── 前 3 轮：每轮都尝试并失败（认领回退、不扣额度）──
    for _ in range(3):
        result = _morning_send(NOW_0737)
        assert result["status"] == "sent"
        assert result["failed"] == 1
    assert len(calls) == 3

    # ── 第 4 轮：当日已达上限 → 该用户被剔除，不再调用微信 ──
    result = _morning_send(NOW_0737)
    assert result["status"] == "no_subscribers"
    assert len(calls) == 3  # 未再次调用微信

    quota = asyncio.run(_get_quota(user_id))
    assert quota.quota_available == 1    # 失败始终不扣额度
    assert quota.last_sent_date is None  # 认领已回退

    # ── 次日：日期变化 → 计数自然重置，重新允许尝试 ──
    next_day = NOW_0737 + timedelta(days=1)
    result = _morning_send(next_day)
    assert result["status"] == "sent"
    assert result["failed"] == 1
    assert len(calls) == 4


def test_morning_claim_blocks_second_sender(
    client: TestClient, monkeypatch, clean_quotas
):
    """原子认领：用户已被认领（last_sent_date==今天，并发/崩溃后状态）
    即使批标记未置位也不重复发送、不重复扣额度。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, user_id = _new_user("morning_claim_001")
    asyncio.run(_seed_quota(user_id, 1))

    # 模拟并发发送者已完成「认领+发送」并提交（崩溃重启后同态）
    async def _preclaim():
        async with async_session() as session:
            await session.execute(
                update(SubscribeQuota)
                .where(SubscribeQuota.user_id == user_id)
                .values(last_sent_date=TODAY)
            )
            await session.commit()

    asyncio.run(_preclaim())

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _morning_send(NOW_0737)
    assert result["status"] == "no_subscribers"
    assert calls == []                          # 已认领 → 本发送者不再发
    quota = asyncio.run(_get_quota(user_id))
    assert quota.quota_available == 1           # 未重复扣额度
    assert quota.last_sent_date == TODAY        # 认领保持


# ══════════════════════════════════════════════════════════════
# 消息内容构建
# ══════════════════════════════════════════════════════════════


def test_build_starlight_morning_data_content():
    """data 含今日星光一句话（能量+星光数）/ 宜忌 / 日期 / 星光色。"""
    guidance = build_today_guidance(TODAY, "leo")
    energy = {"love": 81, "career": 73, "social": 64, "health": 57}
    data = daily_push.build_starlight_morning_data(TODAY, guidance, energy)

    joined = " ".join(v["value"] for v in data.values())
    assert "今日星光" in data["thing1"]["value"]          # 一句话（含星光数+能量）
    assert str(guidance["star_number"]) in joined          # 星光数
    assert "能量" in joined                                # 能量
    assert guidance["advice_do"] in joined                 # 宜
    assert guidance["advice_dont"] in joined               # 忌
    assert guidance["star_color"] in joined                # 星光色
    assert data["date3"]["value"] == TODAY.strftime("%Y.%m.%d")
    # 微信 thing 字段 20 字符上限
    for field in ("thing1", "thing2", "thing4"):
        assert len(data[field]["value"]) <= 20


# ══════════════════════════════════════════════════════════════
# admin trigger_daily_push（改造为按额度消费发送）
# ══════════════════════════════════════════════════════════════


def test_trigger_daily_push_consumes_quota(client: TestClient, monkeypatch, clean_quotas):
    """POST /notify/send-daily（super-admin）→ 与定时任务同一逻辑按额度发送。

    鉴权（401/403）走 HTTP；发送行为直接调 service 层并注入固定 now
    （08:00），不依赖真实系统时间——07:37 之前跑套件也不会挂。
    """
    _reset_state(monkeypatch)
    _, admin_id = _new_user("admin_send_001")
    monkeypatch.setattr(settings, "SUPER_ADMIN_IDS", admin_id)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, user_id = _new_user("admin_send_002")
    asyncio.run(_seed_quota(user_id, 1))

    _fake_wechat_ok(monkeypatch)

    resp = client.post("/notify/send-daily", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 401  # 非法 token 拒绝

    # 普通用户（非 super-admin）→ 403
    _, normal_id = _new_user("admin_send_003")
    normal_token = asyncio.run(_get_token(normal_id))
    resp1 = client.post("/notify/send-daily", headers={"Authorization": f"Bearer {normal_token}"})
    assert resp1.status_code == 403

    # 发送行为：service 层固定时间（先发送，使额度与批标记就位；
    # 随后 HTTP 调用无论真实系统时间如何都不会再发/重复扣额度）
    result = _morning_send(NOW_0800)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["failed"] == 0

    quota = asyncio.run(_get_quota(user_id))
    assert quota.quota_available == 0
    assert quota.last_sent_date == TODAY

    # super-admin 端点调用：只断言 200 + 响应结构（not_due/no_subscribers/sent 均 200）
    token = asyncio.run(_get_token(admin_id))
    resp2 = client.post("/notify/send-daily", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200, resp2.text
    assert "sent" in resp2.json()
    assert "failed" in resp2.json()


async def _get_token(user_id: str) -> str:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one()
        return create_token(user.id, user.token_version)


# ══════════════════════════════════════════════════════════════
# 防疲劳：21:00 晚间推送跳过当日已收晨讯者（每天最多 1 条）
# ══════════════════════════════════════════════════════════════


def test_daily_push_skips_morning_recipients(
    client: TestClient, monkeypatch, clean_quotas
):
    """用户 A 当日已收到星光晨讯（last_sent_date==今天）→ 21:00 星语不再推送；
    用户 B 未收晨讯且偏好 night → 正常推送。

    双槽位共用 last_sent_date 原子认领：A 的认领已被晨讯占据，21:00 扫描
    即被排除（rowcount=0 语义），两槽位共享每日最多 1 条硬上限。
    """
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, morning_user_id = _new_user("evening_morning_001")
    _, fresh_user_id = _new_user("evening_fresh_001")

    async def _seed():
        async with async_session() as session:
            # A：今日已收晨讯（last_sent_date==今天，另有额度但认领已被占据）
            session.add(
                SubscribeQuota(
                    user_id=morning_user_id,
                    quota_available=1,
                    last_sent_date=TODAY,
                    slot_preference="morning",
                )
            )
            # B：未收晨讯、偏好 night、有额度 → 21:00 星语正常推送
            session.add(
                SubscribeQuota(
                    user_id=fresh_user_id,
                    quota_available=1,
                    last_sent_date=None,
                    slot_preference="night",
                )
            )
            await session.commit()

    asyncio.run(_seed())

    calls: list[str] = []

    async def _fake_ok(**kwargs):
        calls.append(kwargs["openid"])
        return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(daily_push, "send_subscribe_message", _fake_ok)

    NOW_2130 = datetime(2026, 8, 10, 21, 30, tzinfo=BEIJING_TZ)
    result = _evening_send(NOW_2130)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert "evening_morning_001" not in calls  # 已收晨讯 → 晚间跳过
    assert "evening_fresh_001" in calls        # 未收晨讯 → 正常推送
    assert result["failed"] == 0

    # B 额度被消费、认领=今天；A 未被消费
    b_quota = asyncio.run(_get_quota(fresh_user_id))
    assert b_quota.quota_available == 0
    assert b_quota.last_sent_date == NOW_2130.date()


# ══════════════════════════════════════════════════════════════
# 推送槽位偏好（T4-1）：GET/POST /notify/preference
# ══════════════════════════════════════════════════════════════


def test_preference_get_requires_auth(client: TestClient):
    """未登录 GET → 401。"""
    resp = client.get("/notify/preference")
    assert resp.status_code == 401


def test_preference_post_requires_auth(client: TestClient):
    """未登录 POST → 401。"""
    resp = client.post("/notify/preference", json={"slot": "night"})
    assert resp.status_code == 401


def test_preference_defaults_to_morning(client: TestClient):
    """无行 → GET 回显默认 morning（设置页首次进入）。"""
    headers, _ = _new_user("pref_default_001")

    resp = client.get("/notify/preference", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot_preference"] == "morning"


def test_preference_set_night_persists(client: TestClient):
    """POST night → 持久化（无行则建行，quota_available=0 仅记偏好）；GET 回显 night。"""
    headers, user_id = _new_user("pref_night_001")

    resp = client.post("/notify/preference", json={"slot": "night"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert resp.json()["slot_preference"] == "night"

    # 持久化：行存在、quota 保持 0（仅记偏好，不发放额度）、偏好为 night
    quota = asyncio.run(_get_quota(user_id))
    assert quota is not None
    assert quota.quota_available == 0
    assert quota.slot_preference == "night"

    # GET 回显（新请求会话）
    resp2 = client.get("/notify/preference", headers=headers)
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["slot_preference"] == "night"


def test_preference_update_overwrites(client: TestClient):
    """已有行 POST 覆盖偏好；不影响既有 quota_available。"""
    headers, user_id = _new_user("pref_switch_001")
    asyncio.run(_seed_quota(user_id, 2))

    resp = client.post("/notify/preference", json={"slot": "night"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["slot_preference"] == "night"

    resp2 = client.post("/notify/preference", json={"slot": "morning"}, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["slot_preference"] == "morning"

    quota = asyncio.run(_get_quota(user_id))
    assert quota.quota_available == 2           # 额度不受偏好设置影响
    assert quota.slot_preference == "morning"


def test_preference_invalid_slot_400(client: TestClient):
    """非法 slot 值 → 400（仅接受 morning/night，严格匹配）。"""
    headers, _ = _new_user("pref_invalid_001")

    for bad in ("noon", "MORNING", "", "morning-night"):
        resp = client.post("/notify/preference", json={"slot": bad}, headers=headers)
        assert resp.status_code == 400, resp.text
