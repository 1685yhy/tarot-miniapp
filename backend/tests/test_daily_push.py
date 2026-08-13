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
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.config import settings
from app.db.database import async_session
from app.models.card_teaching import CardTeaching
from app.models.star_learning_plan import StarLearningPlan
from app.models.star_learning_progress import StarLearningProgress
from app.models.star_word_daily import StarWordDaily
from app.models.subscribe_quota import SubscribeQuota
from app.models.user import User
from app.services import daily_push, star_words

# 北京时间 21:30 / 20:00（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))
NOW_2130 = datetime(2026, 8, 8, 21, 30, tzinfo=BEIJING_TZ)
NOW_2000 = datetime(2026, 8, 8, 20, 0, tzinfo=BEIJING_TZ)
NOW_0737 = datetime(2026, 8, 8, 7, 37, tzinfo=BEIJING_TZ)


def _reset_state(monkeypatch) -> None:
    """Isolate the module state + state file from the dev machine."""
    monkeypatch.setattr(daily_push, "_last_sent_date", None)
    monkeypatch.setattr(daily_push, "_last_config_error_date", None)
    monkeypatch.setattr(daily_push, "_morning_sent_date", None)
    monkeypatch.setattr(daily_push, "_morning_fail_counts", {})
    monkeypatch.setattr(daily_push, "_night_fail_counts", {})
    monkeypatch.setattr(daily_push, "_load_state", lambda: None)
    monkeypatch.setattr(daily_push, "_save_state", lambda: None)


def _send_if_due(now: datetime) -> dict:
    """Run send_daily_push_if_due with a fresh session on the test loop."""

    async def _go():
        async with async_session() as session:
            return await daily_push.send_daily_push_if_due(session, now)

    return asyncio.run(_go())


def _morning_send(now: datetime) -> dict:
    """Run send_starlight_morning_if_due with a fresh session on the test loop."""

    async def _go():
        async with async_session() as session:
            return await daily_push.send_starlight_morning_if_due(session, now)

    return asyncio.run(_go())


async def _new_user(openid: str) -> tuple[str, str]:
    """创建隔离测试用户，返回 (user_id, openid)。"""
    async with async_session() as session:
        user = User(openid=openid, nickname="推送专用")
        session.add(user)
        await session.commit()
        return user.id, user.openid


async def _seed_quota(
    user_id: str,
    quota: int,
    slot: str = "night",
    last_sent_date=None,
) -> None:
    """创建 SubscribeQuota 行（21:00 星语额度制的发送依据）。"""
    async with async_session() as session:
        session.add(
            SubscribeQuota(
                user_id=user_id,
                quota_available=quota,
                slot_preference=slot,
                last_sent_date=last_sent_date,
            )
        )
        await session.commit()


async def _uid_by_openid(openid: str) -> str:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.openid == openid))
        return result.scalar_one().id


async def _get_quota_row(user_id: str) -> SubscribeQuota | None:
    async with async_session() as session:
        result = await session.execute(
            select(SubscribeQuota).where(SubscribeQuota.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def _get_star_word_row(user_id: str, day) -> StarWordDaily | None:
    async with async_session() as session:
        result = await session.execute(
            select(StarWordDaily).where(
                StarWordDaily.user_id == user_id,
                StarWordDaily.word_date == day,
            )
        )
        return result.scalar_one_or_none()


@pytest.fixture
def clean_push_state():
    """发送类用例前后清空额度表 + 星语缓存表（隔离用例间状态）。"""

    async def _clean():
        async with async_session() as session:
            await session.execute(delete(SubscribeQuota))
            await session.execute(delete(StarWordDaily))
            await session.commit()

    asyncio.run(_clean())
    yield
    asyncio.run(_clean())


def _fake_wechat_ok(monkeypatch, calls: list | None = None) -> None:
    """拦截微信订阅消息发送（errcode=0 成功），记录调用参数。"""

    async def _fake_send(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(daily_push, "send_subscribe_message", _fake_send)


class _RaisingCompletions:
    async def create(self, **kwargs):
        raise RuntimeError("DeepSeek 服务不可用")


class _RaisingAIClient:
    """AI 客户端：任何生成调用都抛异常（模拟 AI 全失败 → 短句库兜底）。"""

    class _Chat:
        completions = _RaisingCompletions()

    chat = _Chat()


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


def test_push_sends_to_subscribers(client: TestClient, monkeypatch, clean_push_state):
    """
    21:30 + 模板已配置 + night 用户有额度 → 尝试逐人发送。

    Tests have no WECHAT_APP_ID/SECRET, so the access-token fetch raises —
    each send counts as failed, but the loop completes without crashing,
    quota stays intact and the claim is released (retry allowed next cycle).
    """
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")

    _, openid1 = asyncio.run(_new_user("night_send_001"))
    _, openid2 = asyncio.run(_new_user("night_send_002"))
    uid1 = asyncio.run(_uid_by_openid("night_send_001"))
    uid2 = asyncio.run(_uid_by_openid("night_send_002"))
    asyncio.run(_seed_quota(uid1, 1))
    asyncio.run(_seed_quota(uid2, 1))

    result = _send_if_due(NOW_2130)
    assert result["status"] == "sent"
    assert result["sent"] == 0
    assert result["failed"] == 2  # both failed at token fetch (no crash)
    # 有失败 → 批标记不置位，下一轮 5 分钟循环可补发失败用户
    assert daily_push._last_sent_date is None

    # 失败不扣额度、认领已回退（允许重试）
    for uid in (uid1, uid2):
        quota = asyncio.run(_get_quota_row(uid))
        assert quota.quota_available == 1
        assert quota.last_sent_date is None


def test_push_loop_exits_when_template_unconfigured(client: TestClient, monkeypatch):
    """模板未配置时后台任务立即退出，不空转."""
    result = asyncio.run(daily_push.run_daily_push_loop(interval_seconds=1))
    assert result is None


# ══════════════════════════════════════════════════════════════
# 开发 04 · 月相推送事件
# ══════════════════════════════════════════════════════════════


def test_moon_event_new_moon_eve():
    """新月前一天 → 新月许愿事件（明日新月，准备好愿望了吗 ✦）。"""
    # 方案定义的新月日：2026-08-13 → 前一天 2026-08-12 触发
    event = daily_push.get_moon_push_event(datetime(2026, 8, 12, 21, 30, tzinfo=BEIJING_TZ).date())
    assert event is not None
    assert event["kind"] == "new_moon_eve"
    assert "新月" in event["content"]
    assert event["page"] == "pages/wish/wish"


def test_moon_event_full_moon_day():
    """满月当天 → 满月复盘事件（满月之夜，来复盘你的愿望 ✦）。"""
    # 方案定义/真实月偏食日：2026-08-28 是满月
    event = daily_push.get_moon_push_event(datetime(2026, 8, 28, 21, 30, tzinfo=BEIJING_TZ).date())
    assert event is not None
    assert event["kind"] == "full_moon"
    assert "复盘" in event["content"]
    assert event["page"] == "pages/review/review"


def test_moon_event_none_on_normal_days():
    """普通日子（非新月前夜、非满月）→ 无月相事件。"""
    event = daily_push.get_moon_push_event(datetime(2026, 8, 9, 21, 30, tzinfo=BEIJING_TZ).date())
    assert event is None


def test_moon_push_skipped_when_template_unconfigured(client: TestClient, monkeypatch):
    """月相事件日 + 模板未配置 → skipped_config（与每日一牌一致，不崩溃）。"""
    _reset_state(monkeypatch)
    now = datetime(2026, 8, 28, 21, 30, tzinfo=BEIJING_TZ)  # 满月当天
    result = _send_if_due(now)
    assert result["status"] == "skipped_config"


def test_moon_push_not_due_before_21(client: TestClient, monkeypatch):
    """月相事件日 + 未到 21:00 → not_due。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    now = datetime(2026, 8, 28, 20, 0, tzinfo=BEIJING_TZ)
    result = _send_if_due(now)
    assert result["status"] == "not_due"


def test_moon_push_sends_moon_message_on_full_moon(client: TestClient, monkeypatch, clean_push_state):
    """满月当天 21:30 + 模板已配置 + night 用户有额度 → 发送月相复盘消息（替代星语）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("night_moon_001"))
    uid = asyncio.run(_uid_by_openid("night_moon_001"))
    asyncio.run(_seed_quota(uid, 1))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    # 满月当天（2026-08-28）→ 走 moon 分支：节点内容优先于星语
    result = _send_if_due(datetime(2026, 8, 28, 21, 30, tzinfo=BEIJING_TZ))
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert calls[0]["page"] == "pages/review/review"
    assert "满月" in calls[0]["data"]["thing2"]["value"]
    assert daily_push._last_sent_date == "2026-08-28"

    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 0
    assert quota.last_sent_date == datetime(2026, 8, 28).date()


def test_moon_event_alignment_with_api():
    """推送月相判定与 /moon/phase 同源（确定性一致）。"""
    from app.services.moon import moon_phase_on
    full_day = datetime(2026, 8, 28, 21, 30, tzinfo=BEIJING_TZ).date()
    assert moon_phase_on(full_day)["phase"] == "full_moon"
    assert daily_push.get_moon_push_event(full_day)["kind"] == "full_moon"


# ══════════════════════════════════════════════════════════════
# T4-3: 21:00 槽位额度制改造 — 睡前星语按 slot_preference 分流
# ══════════════════════════════════════════════════════════════


def test_night_push_sends_star_word_and_consumes_quota(
    client: TestClient, monkeypatch, clean_push_state
):
    """night 用户 21:00 收到睡前星语：quota-1、last_sent_date=今天、
    page 指向月光卡页、内容=星语（thing1）+ 星光数/星光色（thing2）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("night_star_001"))
    uid = asyncio.run(_uid_by_openid("night_star_001"))
    asyncio.run(_seed_quota(uid, 1))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _send_if_due(NOW_2130)  # 2026-08-08（普通日，非月相事件）
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["failed"] == 0

    call = calls[0]
    assert call["openid"] == openid
    assert call["template_id"] == "TEST_TMPL"
    assert call["page"] == "pages/moon-card/moon-card"
    assert call["data"]["thing4"]["value"] == "点击收下你的月光卡 ✦"
    assert call["data"]["date3"]["value"] == "2026.08.08"

    # 内容=星语：thing1 与同日缓存短语一致；测试环境无 AI key → 短句库兜底
    cached = asyncio.run(_get_star_word_row(uid, NOW_2130.date()))
    assert cached is not None
    assert cached.source == "fallback"
    import json as _json
    assert _json.loads(cached.data)["phrase"] == call["data"]["thing1"]["value"]
    assert call["data"]["thing2"]["value"].startswith("星光数")

    # 成功：quota-1 与 last_sent_date 同事务落库
    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 0
    assert quota.last_sent_date == NOW_2130.date()
    assert daily_push._last_sent_date == "2026-08-08"

    # 已发送 → 再次调用 not_due（批标记去重）
    result2 = _send_if_due(NOW_2130)
    assert result2["status"] == "not_due"


def test_night_push_skips_morning_pref_users(
    client: TestClient, monkeypatch, clean_push_state
):
    """morning 偏好用户 21:00 跳过（额度保留、不发送）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("morning_skip_night_001"))
    uid = asyncio.run(_uid_by_openid("morning_skip_night_001"))
    asyncio.run(_seed_quota(uid, 2, slot="morning"))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _send_if_due(NOW_2130)
    assert result["status"] == "no_subscribers"
    assert calls == []

    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 2
    assert quota.last_sent_date is None


def test_morning_push_only_morning_pref_users(
    client: TestClient, monkeypatch, clean_push_state
):
    """7:37 晨讯只发 morning 用户；night 用户跳过（额度与认领均不受影响）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, morning_openid = asyncio.run(_new_user("morning_pref_001"))
    _, night_openid = asyncio.run(_new_user("night_pref_001"))
    morning_uid = asyncio.run(_uid_by_openid("morning_pref_001"))
    night_uid = asyncio.run(_uid_by_openid("night_pref_001"))
    asyncio.run(_seed_quota(morning_uid, 1, slot="morning"))
    asyncio.run(_seed_quota(night_uid, 1, slot="night"))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _morning_send(NOW_0737)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert [c["openid"] for c in calls] == [morning_openid]

    # night 用户未被晨讯消费：额度保留、无认领
    quota = asyncio.run(_get_quota_row(night_uid))
    assert quota.quota_available == 1
    assert quota.last_sent_date is None

    # morning 用户已收晨讯：额度-1、last_sent_date=今天
    quota_m = asyncio.run(_get_quota_row(morning_uid))
    assert quota_m.quota_available == 0
    assert quota_m.last_sent_date == NOW_0737.date()


def test_same_day_two_slots_max_one_push(
    client: TestClient, monkeypatch, clean_push_state
):
    """双槽位共享每日 1 条：先发晨讯 → 21:00 认领 rowcount=0 跳过。

    用户先以 morning 偏好收晨讯（last_sent_date=今天），随后切换 night——
    21:00 扫描即被 last_sent_date==今天 排除，绝不双发。
    """
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("both_slots_001"))
    uid = asyncio.run(_uid_by_openid("both_slots_001"))
    asyncio.run(_seed_quota(uid, 2, slot="morning"))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    # 7:37 晨讯：发送 1 条，quota 2→1
    morning = _morning_send(NOW_0737)
    assert morning["status"] == "sent"
    assert morning["sent"] == 1
    assert len(calls) == 1

    # 切换到 night 偏好（模拟用户下午改设置）
    async def _switch_slot():
        async with async_session() as session:
            await session.execute(
                update(SubscribeQuota)
                .where(SubscribeQuota.user_id == uid)
                .values(slot_preference="night")
            )
            await session.commit()

    asyncio.run(_switch_slot())

    # 21:00：last_sent_date==今天 → 扫描排除（原子认领 rowcount=0 语义）
    night = _send_if_due(NOW_2130)
    assert night["status"] == "no_subscribers"
    assert len(calls) == 1  # 未再发送

    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 1
    assert quota.last_sent_date == NOW_2130.date()


def test_full_moon_sends_to_all_quota_users_regardless_of_preference(
    client: TestClient, monkeypatch, clean_push_state
):
    """满月当天 21:00 → 节点内容优先，发全部有额度未发用户（不因槽位偏好丢失）。

    morning 与 night 用户均收到「满月复盘」，quota 各 -1。
    """
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, morning_openid = asyncio.run(_new_user("moon_morning_001"))
    _, night_openid = asyncio.run(_new_user("moon_night_001"))
    morning_uid = asyncio.run(_uid_by_openid("moon_morning_001"))
    night_uid = asyncio.run(_uid_by_openid("moon_night_001"))
    asyncio.run(_seed_quota(morning_uid, 1, slot="morning"))
    asyncio.run(_seed_quota(night_uid, 1, slot="night"))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    full_moon_now = datetime(2026, 8, 28, 21, 30, tzinfo=BEIJING_TZ)
    result = _send_if_due(full_moon_now)
    assert result["status"] == "sent"
    assert result["sent"] == 2
    assert result["failed"] == 0
    assert {c["openid"] for c in calls} == {morning_openid, night_openid}
    for call in calls:
        assert call["page"] == "pages/review/review"
        assert "满月" in call["data"]["thing2"]["value"]

    for uid in (morning_uid, night_uid):
        quota = asyncio.run(_get_quota_row(uid))
        assert quota.quota_available == 0
        assert quota.last_sent_date == full_moon_now.date()


def test_night_push_no_quota_not_sent(client: TestClient, monkeypatch, clean_push_state):
    """无额度 → 不发（quota_available==0 不进入候选）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, _ = asyncio.run(_new_user("night_zero_001"))
    uid = asyncio.run(_uid_by_openid("night_zero_001"))
    asyncio.run(_seed_quota(uid, 0))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _send_if_due(NOW_2130)
    assert result["status"] == "no_subscribers"
    assert calls == []


def test_night_push_ai_failure_fallback_phrase_and_cache(
    client: TestClient, monkeypatch, clean_push_state
):
    """星语 AI 失败 → 发送 fallback 短句库短语，且缓存 source=fallback。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, _ = asyncio.run(_new_user("night_ai_fail_001"))
    uid = asyncio.run(_uid_by_openid("night_ai_fail_001"))
    asyncio.run(_seed_quota(uid, 1))

    # AI 持续抛异常 → 重试上限后落 fallback（与 test_star_words 同款模拟）
    monkeypatch.setattr(
        "app.services.star_words._get_ai_client",
        lambda: _RaisingAIClient(),
    )
    monkeypatch.setattr("app.services.star_words._AI_RETRY_BACKOFF_SECONDS", 0)

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _send_if_due(NOW_2130)
    assert result["status"] == "sent"
    assert result["sent"] == 1

    cached = asyncio.run(_get_star_word_row(uid, NOW_2130.date()))
    assert cached is not None
    assert cached.source == "fallback"
    import json as _json
    phrase = _json.loads(cached.data)["phrase"]
    assert phrase == calls[0]["data"]["thing1"]["value"]
    all_phrases = {p for pool in star_words.STAR_WORD_POOLS.values() for p in pool}
    assert phrase in all_phrases, "降级短语必须来自短句库"


def test_night_push_fail_3_times_then_skip(
    client: TestClient, monkeypatch, clean_push_state
):
    """当日发送失败 3 次后不再尝试该用户；失败不扣额度、认领回退；次日重置。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, _ = asyncio.run(_new_user("night_cap_001"))
    uid = asyncio.run(_uid_by_openid("night_cap_001"))
    asyncio.run(_seed_quota(uid, 1))

    calls: list = []

    async def _fake_fail(**kwargs):
        calls.append(kwargs["openid"])
        return {"errcode": 40003, "errmsg": "invalid openid"}

    monkeypatch.setattr(daily_push, "send_subscribe_message", _fake_fail)

    # ── 前 3 轮：每轮都尝试并失败（认领回退、不扣额度）──
    for _ in range(3):
        result = _send_if_due(NOW_2130)
        assert result["status"] == "sent"
        assert result["failed"] == 1
    assert len(calls) == 3

    # 失败始终不扣额度、认领回退为 NULL
    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 1
    assert quota.last_sent_date is None

    # ── 第 4 轮：当日已达上限 → 该用户被剔除，不再调用微信 ──
    result = _send_if_due(NOW_2130)
    assert result["status"] == "no_subscribers"
    assert len(calls) == 3  # 未再次调用微信

    # ── 次日：日期变化 → 计数自然重置，重新允许尝试 ──
    next_day = NOW_2130 + timedelta(days=1)
    result = _send_if_due(next_day)
    assert result["status"] == "sent"
    assert result["failed"] == 1
    assert len(calls) == 4


def test_night_push_claim_blocks_preclaimed(
    client: TestClient, monkeypatch, clean_push_state
):
    """原子认领：用户已被认领（last_sent_date==今天）→ 不发送、不扣额度。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, _ = asyncio.run(_new_user("night_claim_001"))
    uid = asyncio.run(_uid_by_openid("night_claim_001"))
    asyncio.run(_seed_quota(uid, 1, last_sent_date=NOW_2130.date()))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _send_if_due(NOW_2130)
    assert result["status"] == "no_subscribers"
    assert calls == []

    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 1
    assert quota.last_sent_date == NOW_2130.date()


def test_night_push_star_cache_conflict_does_not_lose_claim(
    client: TestClient, monkeypatch, clean_push_state
):
    """T1-8 认领竞态回归：星语缓存并发冲突（rollback）不得连带撤销认领。

    修复前：night 路径先认领（last_sent_date=today，未提交）再调
    get_today_star_word —— _save_cache 撞 uq_user_word_date 唯一约束时
    db.rollback() 会回滚同事务内的认领；发送成功后 quota-1 但
    last_sent_date 仍 NULL → 下一轮循环同日二次推送（quota≥2 时
    破坏 1 条/天硬上限）。
    修复后（方案 B）：取星语在认领 UPDATE 之前，缓存冲突的 rollback
    只作用于星语缓存事务；认领在其后执行，不受影响。
    T1-8 闭环（Fix round 2）：rollback() 无条件过期会话内**所有** ORM 对象
    （expire_on_commit=False 只影响 commit 不影响 rollback）——本轮 mock
    **不注入 db.refresh**（生产 _save_cache 没有这步），精确模拟生产冲突
    路径：修复前 user.zodiac/_today_energy/user.openid 访问直接
    MissingGreenlet → 整轮失败；修复后循环体零 ORM 属性访问（循环前
    物化的纯值快照），冲突回滚后继续发送不受影响。
    模拟：monkeypatch _save_cache 走并发输家路径（rollback + 返回赢家内容），
    断言发送后 last_sent_date==今天、quota-1，且清掉批标记后再次循环不双发。
    """
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, _ = asyncio.run(_new_user("night_cache_race_001"))
    uid = asyncio.run(_uid_by_openid("night_cache_race_001"))
    asyncio.run(_seed_quota(uid, 2))  # quota>=2 才能暴露旧 bug 的二次推送

    # 模拟并发输家：commit 撞 uq_user_word_date 唯一约束 → IntegrityError
    # 处理器回滚 → 回读赢家已落库缓存返回（与 star_words._save_cache 同款路径）。
    # 只 rollback、不 refresh、不回读 ORM——与生产 _save_cache 完全一致。
    async def _conflicting_save_cache(db, user_id, today, phrase, source):
        await db.rollback()
        return {"phrase": "并发赢家已落库短语", "source": "ai"}

    monkeypatch.setattr(star_words, "_save_cache", _conflicting_save_cache)

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _send_if_due(NOW_2130)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert len(calls) == 1
    # 赢家短语贯通到推送内容（thing1）
    assert calls[0]["data"]["thing1"]["value"] == "并发赢家已落库短语"

    # 认领未被缓存冲突回滚连带撤销：last_sent_date==今天、quota-1
    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 1
    assert quota.last_sent_date == NOW_2130.date()

    # 清掉批标记模拟 5 分钟循环再次扫描（旧 bug：认领被回滚 → 同日再发）
    monkeypatch.setattr(daily_push, "_last_sent_date", None)
    result2 = _send_if_due(NOW_2130)
    assert result2["status"] == "no_subscribers"
    assert len(calls) == 1  # 未双发

    quota2 = asyncio.run(_get_quota_row(uid))
    assert quota2.quota_available == 1
    assert quota2.last_sent_date == NOW_2130.date()


# ══════════════════════════════════════════════════════════════
# T3-2: 晨讯节点主题三态切换（新月许愿 / 满月复盘 / 水逆首日关怀）
# ══════════════════════════════════════════════════════════════


def test_astral_morning_new_moon_day():
    """新月当天（2026-01-03）→ 新月版：许愿之夜，page=wish。"""
    event = daily_push._astral_morning_event(date(2026, 1, 3))
    assert event is not None
    assert event["kind"] == "new_moon"
    assert event["title"] == "今日新月 · 许愿之夜"
    assert len(event["title"]) <= 20
    assert event["page"] == "pages/wish/wish"


def test_astral_morning_full_moon_day():
    """满月当天（2026-01-11）→ 满月版：复盘愿望，page=review。"""
    event = daily_push._astral_morning_event(date(2026, 1, 11))
    assert event is not None
    assert event["kind"] == "full_moon"
    assert event["title"] == "满月之夜 · 来复盘你的愿望"
    assert len(event["title"]) <= 20
    assert event["page"] == "pages/review/review"


def test_astral_morning_mercury_first_day():
    """水逆首日（2026-01-14，ev["start"]==today）→ 水逆版：7 件小事，page=astral-event。"""
    event = daily_push._astral_morning_event(date(2026, 1, 14))
    assert event is not None
    assert event["kind"] == "mercury_retrograde"
    assert event["title"] == "水逆开始 · 7 件慢下来的小事"
    assert len(event["title"]) <= 20
    assert (
        event["page"]
        == "pages/astral-event/astral-event?type=mercury_retrograde"
    )


def test_astral_morning_mercury_mid_range_none():
    """水逆中段（2026-01-20，非首日）→ None：不额外打扰（防疲劳纪律）。"""
    assert daily_push._astral_morning_event(date(2026, 1, 20)) is None


def test_astral_morning_regular_day_none():
    """常规日（2026-01-05，仅节气）→ None：晨讯保持常规今日星光。"""
    assert daily_push._astral_morning_event(date(2026, 1, 5)) is None


def test_astral_morning_node_data_fields_within_20():
    """三态节点版模板数据全部 thing 字段 ≤20 字（微信 thing 上限）。"""
    from app.services.astral_calendar import node_content

    for d in (date(2026, 1, 3), date(2026, 1, 11), date(2026, 1, 14)):
        event = daily_push._astral_morning_event(d)
        assert event is not None
        data = daily_push.build_moon_push_data(event, d)
        for key in ("thing1", "thing2", "thing4"):
            assert len(data[key]["value"]) <= 20, (d, key, data[key]["value"])
        assert data["date3"]["value"] == d.strftime("%Y.%m.%d")

    # 文案复用 node_content（避免重复实现）：新月 thing2=许愿引导语、
    # 水逆 thing2=慢行期每日一句（同日确定性）
    wish_event = daily_push._astral_morning_event(date(2026, 1, 3))
    assert daily_push.build_moon_push_data(wish_event, date(2026, 1, 3))[
        "thing2"
    ]["value"] == node_content("wish", date(2026, 1, 3))["content"]
    mercury_event = daily_push._astral_morning_event(date(2026, 1, 14))
    assert daily_push.build_moon_push_data(mercury_event, date(2026, 1, 14))[
        "thing2"
    ]["value"] == node_content("mercury_guide", date(2026, 1, 14))[
        "daily_sentence"
    ]


def test_morning_push_node_content_on_new_moon_day(
    client: TestClient, monkeypatch, clean_push_state
):
    """新月当天 7:37 晨讯 → 节点版：page=wish、thing1=许愿之夜；额度/认领语义不变。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("morning_node_001"))
    uid = asyncio.run(_uid_by_openid("morning_node_001"))
    asyncio.run(_seed_quota(uid, 1, slot="morning"))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    new_moon_now = datetime(2026, 1, 3, 7, 37, tzinfo=BEIJING_TZ)
    result = _morning_send(new_moon_now)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert calls[0]["openid"] == openid
    assert calls[0]["page"] == "pages/wish/wish"
    assert calls[0]["data"]["thing1"]["value"] == "今日新月 · 许愿之夜"
    assert calls[0]["data"]["thing2"]["value"] == "写给月亮的三行愿望"
    assert calls[0]["data"]["date3"]["value"] == "2026.01.03"

    # 成功语义与常规晨讯一致：quota-1、last_sent_date=今天（1 条/天额度不破）
    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 0
    assert quota.last_sent_date == new_moon_now.date()


def test_morning_push_regular_content_on_mercury_mid_range(
    client: TestClient, monkeypatch, clean_push_state
):
    """水逆中段 7:37 晨讯 → 常规今日星光（page=index，节点不打扰）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("morning_regular_001"))
    uid = asyncio.run(_uid_by_openid("morning_regular_001"))
    asyncio.run(_seed_quota(uid, 1, slot="morning"))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    mid_range_now = datetime(2026, 1, 20, 7, 37, tzinfo=BEIJING_TZ)
    result = _morning_send(mid_range_now)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert calls[0]["page"] == "pages/index/index"
    assert calls[0]["data"]["thing1"]["value"].startswith("今日星光")
    assert calls[0]["data"]["thing4"]["value"].startswith("星光色")

    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 0
    assert quota.last_sent_date == mid_range_now.date()


# ══════════════════════════════════════════════════════════════
# T6-3: 学习提醒主题三态优先级（节点日主题 > 学习提醒主题 > 常规晨讯/星语）
# ══════════════════════════════════════════════════════════════

# 教学种子卡（学习提醒关键词数据源）：只用 4/5 —— 避开 test_teaching 的
# 1/7/14、无教学哨兵 2、test_academy 的 3/6（导入期先到先得，冲突破坏对方断言）。
_LESSON_REMINDER_TEACHING = [
    {
        "card_id": 4,
        "symbols": json.dumps([{"symbol": "王座", "meaning": "稳固与秩序"}]),
        "story": "皇帝是塔罗大阿尔卡纳的第四张牌，象征秩序与掌控的力量。",
        "keywords_learning": json.dumps(["稳固", "秩序", "责任"]),
        "life_connection": "把秩序带回日常，让目标有落点。",
        "element_association": "火元素——行动与权威。",
    },
    {
        "card_id": 5,
        "symbols": json.dumps([{"symbol": "导师", "meaning": "传承与指引"}]),
        "story": "教皇是塔罗大阿尔卡纳的第五张牌，象征传承与内在指引。",
        "keywords_learning": json.dumps(["传承", "指引", "智慧"]),
        "life_connection": "倾听内心的声音，也听听前辈的经验。",
        "element_association": "土元素——传统与经验。",
    },
]


async def _seed_plan(
    user_id: str,
    cards_per_day: int = 1,
    reminder_on: bool = True,
    path: str = "major",
    cursor_pos: int = 0,
) -> None:
    """创建 StarLearningPlan 行（学习提醒触发依据）。"""
    async with async_session() as session:
        session.add(
            StarLearningPlan(
                user_id=user_id,
                cards_per_day=cards_per_day,
                reminder_on=reminder_on,
                path=path,
                cursor_pos=cursor_pos,
            )
        )
        await session.commit()


async def _seed_learned_today(user_id: str, card_ids: list[int], day: date) -> None:
    """直接插入今日已学行（learned_at==day，学满判定数据源）。"""
    async with async_session() as session:
        for cid in card_ids:
            session.add(
                StarLearningProgress(
                    user_id=user_id,
                    card_id=cid,
                    learned_at=day,
                    review_count=0,
                )
            )
        await session.commit()


def _learning_snapshot(uid: str, openid: str) -> daily_push._UserSnapshot:
    """构造与推送循环同款的纯值快照（T6-3 纯函数测试用）。"""
    return daily_push._UserSnapshot(
        id=uid, openid=openid, zodiac=None, birth_date=None,
        created_at=None, quota_available=1,
    )


async def _learning_event(uid: str, openid: str, day: date) -> dict | None:
    """直接调用 _learning_reminder_event（三态判定中间件单测）。"""
    async with async_session() as session:
        return await daily_push._learning_reminder_event(
            session, _learning_snapshot(uid, openid), day
        )


@pytest.fixture
def clean_learning_state():
    """学习提醒用例前后清理：额度 + 星语缓存 + 学习计划/进度 + 教学种子卡 4/5。

    只清 4/5 的教学行（本文件自种）——不动 test_teaching 导入期种子卡
    （1/7/14），避免跨文件顺序依赖。
    """

    async def _clean():
        async with async_session() as session:
            await session.execute(delete(SubscribeQuota))
            await session.execute(delete(StarWordDaily))
            await session.execute(delete(StarLearningProgress))
            await session.execute(delete(StarLearningPlan))
            await session.execute(
                delete(CardTeaching).where(CardTeaching.card_id.in_([4, 5]))
            )
            await session.commit()

    async def _seed():
        async with async_session() as session:
            for seed in _LESSON_REMINDER_TEACHING:
                session.add(CardTeaching(**seed))
            await session.commit()

    asyncio.run(_clean())
    asyncio.run(_seed())
    yield
    asyncio.run(_clean())


def test_learning_reminder_event_fields(
    client: TestClient, monkeypatch, clean_learning_state
):
    """T6-3 字段：thing1 ≤20 字且含牌名、page=pages/academy/lesson/lesson?card_id=、
    thing4 固定「点击点亮这颗星 ✦」；无计划用户 → None（默认分支不变）。"""
    _, openid = asyncio.run(_new_user("learn_field_001"))
    uid = asyncio.run(_uid_by_openid("learn_field_001"))
    asyncio.run(_seed_plan(uid, cards_per_day=1, reminder_on=True, path="major", cursor_pos=3))

    # 大阿卡纳游标 3（0-based）→ 卡牌4（皇帝）：今日学牌 = 今日应学牌
    event = asyncio.run(_learning_event(uid, openid, date(2026, 8, 8)))
    assert event is not None
    assert event["kind"] == "learning_reminder"
    assert event["title"] == "今日学牌：卡牌4"
    assert len(event["title"]) <= 20
    assert event["keywords"] == "关键词·稳固·秩序"  # CardTeaching.keywords_learning 前两个
    assert len(event["keywords"]) <= 20
    assert event["page"] == "pages/academy/lesson/lesson?card_id=4"

    data = daily_push.build_learning_push_data(event, date(2026, 8, 8))
    assert data["thing1"]["value"] == "今日学牌：卡牌4"
    assert len(data["thing1"]["value"]) <= 20
    assert data["thing2"]["value"] == "关键词·稳固·秩序"
    assert data["date3"]["value"] == "2026.08.08"
    assert data["thing4"]["value"] == "点击点亮这颗星 ✦"

    # 无计划用户 → None（学习提醒默认关闭：无计划天然不触发）
    _, no_plan_openid = asyncio.run(_new_user("learn_field_002"))
    no_plan_uid = asyncio.run(_uid_by_openid("learn_field_002"))
    assert asyncio.run(_learning_event(no_plan_uid, no_plan_openid, date(2026, 8, 8))) is None


def test_morning_push_learning_reminder_replaces_regular(
    client: TestClient, monkeypatch, clean_learning_state
):
    """普通学习日（2026-08-08 非节点）7:37 晨讯 → 学习提醒替代常规今日星光。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("learn_morning_001"))
    uid = asyncio.run(_uid_by_openid("learn_morning_001"))
    asyncio.run(_seed_quota(uid, 1, slot="morning"))
    asyncio.run(_seed_plan(uid, 1, True, "major", 3))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _morning_send(NOW_0737)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert calls[0]["page"] == "pages/academy/lesson/lesson?card_id=4"
    assert calls[0]["data"]["thing1"]["value"] == "今日学牌：卡牌4"
    assert calls[0]["data"]["thing2"]["value"] == "关键词·稳固·秩序"
    assert calls[0]["data"]["date3"]["value"] == "2026.08.08"
    assert calls[0]["data"]["thing4"]["value"] == "点击点亮这颗星 ✦"

    # 主题切换不破纪律：quota-1、last_sent_date=今天（仍 1 条/天）
    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 0
    assert quota.last_sent_date == NOW_0737.date()


def test_morning_push_learning_stops_when_day_goal_met(
    client: TestClient, monkeypatch, clean_learning_state
):
    """今日已学满 cards_per_day → 学习提醒停发，晨讯回落常规今日星光。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("learn_full_001"))
    uid = asyncio.run(_uid_by_openid("learn_full_001"))
    asyncio.run(_seed_quota(uid, 1, slot="morning"))
    asyncio.run(_seed_plan(uid, cards_per_day=1, reminder_on=True, path="major", cursor_pos=3))
    asyncio.run(_seed_learned_today(uid, [4], NOW_0737.date()))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _morning_send(NOW_0737)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert calls[0]["page"] == "pages/index/index"
    assert calls[0]["data"]["thing1"]["value"].startswith("今日星光")
    assert calls[0]["data"]["thing4"]["value"].startswith("星光色")

    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 0
    assert quota.last_sent_date == NOW_0737.date()


def test_morning_push_learning_off_by_default(
    client: TestClient, monkeypatch, clean_learning_state
):
    """reminder_on=false → 学习提醒不触发，晨讯保持常规内容（默认关闭）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("learn_off_001"))
    uid = asyncio.run(_uid_by_openid("learn_off_001"))
    asyncio.run(_seed_quota(uid, 1, slot="morning"))
    asyncio.run(_seed_plan(uid, cards_per_day=1, reminder_on=False, path="major", cursor_pos=3))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _morning_send(NOW_0737)
    assert result["status"] == "sent"
    assert calls[0]["page"] == "pages/index/index"
    assert calls[0]["data"]["thing1"]["value"].startswith("今日星光")


def test_morning_push_node_day_priority_over_learning(
    client: TestClient, monkeypatch, clean_learning_state
):
    """新月当天（2026-01-03）7:37 → 节点内容优先于学习提醒（三态第一优先）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("learn_node_001"))
    uid = asyncio.run(_uid_by_openid("learn_node_001"))
    asyncio.run(_seed_quota(uid, 1, slot="morning"))
    # 学习条件全满足（reminder_on + 未学满）——仍要让位节点主题
    asyncio.run(_seed_plan(uid, cards_per_day=1, reminder_on=True, path="major", cursor_pos=3))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    new_moon_now = datetime(2026, 1, 3, 7, 37, tzinfo=BEIJING_TZ)
    result = _morning_send(new_moon_now)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert calls[0]["page"] == "pages/wish/wish"
    assert calls[0]["data"]["thing1"]["value"] == "今日新月 · 许愿之夜"
    assert calls[0]["data"]["thing2"]["value"] == "写给月亮的三行愿望"

    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 0
    assert quota.last_sent_date == new_moon_now.date()


def test_learning_reminder_no_quota_not_sent(
    client: TestClient, monkeypatch, clean_learning_state
):
    """有学习计划但无额度 → 不发送（既有扫描条件不变，quota=0 不进候选）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, _ = asyncio.run(_new_user("learn_zero_001"))
    uid = asyncio.run(_uid_by_openid("learn_zero_001"))
    asyncio.run(_seed_quota(uid, 0, slot="morning"))
    asyncio.run(_seed_plan(uid, cards_per_day=1, reminder_on=True, path="major", cursor_pos=3))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _morning_send(NOW_0737)
    assert result["status"] == "no_subscribers"
    assert calls == []


def test_night_push_learning_reminder_replaces_star_word(
    client: TestClient, monkeypatch, clean_learning_state
):
    """普通日 21:00 night 用户 + 学习计划 → 学习提醒替代睡前星语（page=lesson）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("learn_night_001"))
    uid = asyncio.run(_uid_by_openid("learn_night_001"))
    asyncio.run(_seed_quota(uid, 1))
    asyncio.run(_seed_plan(uid, cards_per_day=1, reminder_on=True, path="major", cursor_pos=3))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    result = _send_if_due(NOW_2130)  # 2026-08-08 普通日（非月相事件）
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert calls[0]["openid"] == openid
    assert calls[0]["page"] == "pages/academy/lesson/lesson?card_id=4"
    assert calls[0]["data"]["thing1"]["value"] == "今日学牌：卡牌4"
    assert calls[0]["data"]["thing2"]["value"] == "关键词·稳固·秩序"
    assert calls[0]["data"]["date3"]["value"] == "2026.08.08"
    assert calls[0]["data"]["thing4"]["value"] == "点击点亮这颗星 ✦"

    # 学习提醒不发星语：无星语缓存落库（星语日才写缓存）
    assert asyncio.run(_get_star_word_row(uid, NOW_2130.date())) is None

    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 0
    assert quota.last_sent_date == NOW_2130.date()


def test_night_push_full_moon_priority_over_learning(
    client: TestClient, monkeypatch, clean_learning_state
):
    """满月当天（2026-08-28）21:00 → 节点内容优先于学习提醒（月相节点召回）。"""
    _reset_state(monkeypatch)
    monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
    _, openid = asyncio.run(_new_user("learn_fullmoon_001"))
    uid = asyncio.run(_uid_by_openid("learn_fullmoon_001"))
    asyncio.run(_seed_quota(uid, 1))
    # 学习条件全满足——仍要让位满月节点
    asyncio.run(_seed_plan(uid, cards_per_day=1, reminder_on=True, path="major", cursor_pos=3))

    calls: list = []
    _fake_wechat_ok(monkeypatch, calls)

    full_moon_now = datetime(2026, 8, 28, 21, 30, tzinfo=BEIJING_TZ)
    result = _send_if_due(full_moon_now)
    assert result["status"] == "sent"
    assert result["sent"] == 1
    assert calls[0]["openid"] == openid
    assert calls[0]["page"] == "pages/review/review"
    assert "满月" in calls[0]["data"]["thing2"]["value"]

    quota = asyncio.run(_get_quota_row(uid))
    assert quota.quota_available == 0
    assert quota.last_sent_date == full_moon_now.date()
