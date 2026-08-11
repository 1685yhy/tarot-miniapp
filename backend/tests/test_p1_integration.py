"""
T5-1 四功能串联验证（SDD P1 设计五）——跨端点/跨功能集成测试。

验证矩阵（每条链路 = 登录 → A 功能 → B 功能 → 断言状态/数据一致）：

1. 星尘经济闭环（手账×日历×相遇 → 星阶 → 名片）
   - 三来源（签到 +1 / 手账连续 7 天 +1 / 节点打卡 +1）各自幂等；
   - stardust_total 累加后 star_tier 恒等于 tier_for(stardust_total)（同步推导）；
   - 星阶透传名片（/share/card-info）、任务状态（/tasks/status）与
     相遇公开页（/meet/public）三处一致。

2. 推送体系闭环（晨讯×星语×节点 → 每日 ≤1 条）
   - morning 用户 7:37 收晨讯、21:00 不收星语；night 用户 7:37 不收、21:00 收；
   - 节点日（2026-08-12 新月+日全食）晨讯走节点版（page=wish），21:00
     月相事件优先（new_moon_eve → night 用户收节点版），已收晨讯者不再发
     → 每日 ≤1 条；跨日解锁（次日可再收）。
   - 偏好切换（morning→night）：当日已发不重发，次日按新槽位收星语，
     每日仍 ≤1 条。

3. 分享裂变闭环（四种海报 scene 区分）
   - 名片码：/share/wxacode scene=invite_code → card-landing；
   - 相遇码：/meet/invite scene=m:{meet_id} → meet-landing；
   - 月光卡/手账海报复用名片码（/share/wxacode；前端约定由
     miniapp/scripts/verify-p1-frontend.js 静态断言）；
   - 历史别名：/share/wxa-code?path= 兼容（T5-1 修复：此前 path= 被静默
     丢弃 → 码指向首页，裂变断链）。

4. 情感主线闭环（手账 → 月历聚合 → 月度复盘有料）
   - 手账记录 → /journal/calendar 当月含今日、current_streak ≥ 1；
   - /journal/review 当月 days_recorded > 0 且 trend_summary 非空（AI 禁用
     时降级模板，仍"有料"）+ 二次请求缓存命中；share-preview 统计与复盘
     同口径、无敏感字段。

5. 合盘跨链路（quick → invite → public → join → 双向奖励）
   - 公开页星阶透传发起人当前星阶（stardust → tier → 名片）；
   - 归属校验：发起人/好友可见、第三人 404、重复 join 幂等 400；
   - 我的相遇列表双方可见。
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import app.api.astral as astral_api
import app.api.journal as journal_api
import app.api.meet as meet_api
import app.api.share as share_api
import app.api.tasks as tasks_api
from app.config import settings
from app.db.database import async_session
from app.models.astral_activity_log import AstralActivityLog
from app.models.checkin import CheckIn
from app.models.diary import DiaryEntry
from app.models.share_log import Invite
from app.models.star_meeting import StarMeeting
from app.models.star_monthly_review import StarMonthlyReview
from app.models.star_word_daily import StarWordDaily
from app.models.subscribe_quota import SubscribeQuota
from app.models.user import User
from app.services import daily_push
from app.services import diary_entries
from app.services.diary_entries import upsert_diary_entry
from app.services.stardust import tier_for, tier_name
from app.utils.auth import create_token

BEIJING_TZ = timezone(timedelta(hours=8))
NOW_0737 = datetime(2026, 8, 11, 7, 37, tzinfo=BEIJING_TZ)
NOW_2130 = datetime(2026, 8, 11, 21, 30, tzinfo=BEIJING_TZ)
# 2026-08-12 = 狮子座新月 + 日全食（星象日历节点日；21:00 新月前夜月相事件日）
NODE_DAY = date(2026, 8, 12)


# ── helpers ─────────────────────────────────────────────────────────────


class _FixedToday(date):
    """date 子类：today() 返回固定日期（钉住 API 层 date.today()）。"""

    fixed: date = NODE_DAY

    @classmethod
    def today(cls) -> date:
        return cls.fixed


def _new_user(openid: str, **fields) -> tuple[str, str, dict[str, str]]:
    """创建隔离测试用户，返回 (user_id, openid, auth_headers)。"""

    async def _go() -> tuple[str, str, str]:
        async with async_session() as session:
            user = User(openid=openid, nickname="串联验证", **fields)
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return user.id, user.openid, token

    uid, openid, token = asyncio.run(_go())
    return uid, openid, {"Authorization": f"Bearer {token}"}


def _cleanup(*user_ids: str) -> None:
    """删除测试用户的全部相关行（隔离用例间状态，不留残留影响其他测试文件）。"""

    async def _go() -> None:
        async with async_session() as session:
            for uid in user_ids:
                await session.execute(
                    delete(SubscribeQuota).where(SubscribeQuota.user_id == uid)
                )
                await session.execute(
                    delete(StarWordDaily).where(StarWordDaily.user_id == uid)
                )
                await session.execute(
                    delete(CheckIn).where(CheckIn.user_id == uid)
                )
                await session.execute(
                    delete(AstralActivityLog).where(AstralActivityLog.user_id == uid)
                )
                await session.execute(
                    delete(DiaryEntry).where(DiaryEntry.user_id == uid)
                )
                await session.execute(
                    delete(StarMonthlyReview).where(StarMonthlyReview.user_id == uid)
                )
                await session.execute(
                    delete(Invite).where(Invite.inviter_id == uid)
                )
                await session.execute(
                    delete(Invite).where(Invite.invitee_id == uid)
                )
                await session.execute(
                    delete(StarMeeting).where(StarMeeting.initiator_id == uid)
                )
                await session.execute(
                    delete(StarMeeting).where(StarMeeting.friend_user_id == uid)
                )
            await session.execute(
                delete(User).where(User.id.in_(list(user_ids)))
            )
            await session.commit()

    asyncio.run(_go())


def _seed_diary_entries(user_id: str, rows: list[tuple[date, str]]) -> None:
    """批量回填手账记录（服务层直写，供 streak/复盘聚合用）。"""

    async def _go() -> None:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one()
            for d, mood in rows:
                await upsert_diary_entry(session, user, mood, entry_date=d)
            await session.commit()

    asyncio.run(_go())


def _fetch_user(user_id: str) -> tuple[int, int | None]:
    """读取 (stardust_total, star_tier)。"""

    async def _go() -> tuple[int, int | None]:
        async with async_session() as session:
            u = await session.get(User, user_id)
            return u.stardust_total or 0, u.star_tier

    return asyncio.run(_go())


def _quota_row(user_id: str) -> tuple[int, date | None]:
    """读取 (quota_available, last_sent_date)。"""

    async def _go() -> tuple[int, date | None]:
        async with async_session() as session:
            q = (
                await session.execute(
                    select(SubscribeQuota).where(SubscribeQuota.user_id == user_id)
                )
            ).scalar_one_or_none()
            if q is None:
                return -1, None
            return q.quota_available, q.last_sent_date

    return asyncio.run(_go())


def _reset_push_state(monkeypatch) -> None:
    """隔离 daily_push 模块内存态 + 状态文件。"""
    monkeypatch.setattr(daily_push, "_last_sent_date", None)
    monkeypatch.setattr(daily_push, "_last_config_error_date", None)
    monkeypatch.setattr(daily_push, "_morning_sent_date", None)
    monkeypatch.setattr(daily_push, "_morning_fail_counts", {})
    monkeypatch.setattr(daily_push, "_night_fail_counts", {})
    monkeypatch.setattr(daily_push, "_load_state", lambda: None)
    monkeypatch.setattr(daily_push, "_save_state", lambda: None)


def _run_morning(now: datetime) -> dict:
    async def _go():
        async with async_session() as session:
            return await daily_push.send_starlight_morning_if_due(session, now)

    return asyncio.run(_go())


def _run_night(now: datetime) -> dict:
    async def _go():
        async with async_session() as session:
            return await daily_push.send_daily_push_if_due(session, now)

    return asyncio.run(_go())


def _fake_wechat_ok(monkeypatch, calls: list) -> None:
    """拦截微信订阅消息发送（errcode=0），记录调用参数。"""

    async def _fake_send(**kwargs):
        calls.append(kwargs)
        return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(daily_push, "send_subscribe_message", _fake_send)


def _calls_for(calls: list[dict], openid: str) -> list[dict]:
    """筛出指定 openid 的推送调用（断言按用户隔离，不受其他测试残留用户影响）。"""
    return [c for c in calls if c.get("openid") == openid]


def _reset_public_limiters(monkeypatch) -> None:
    """重置公开接口限流桶（/meet/public 与 /share/card-info，各 30 次/分/IP）。

    test_meet.py 的 429 用例会把进程内 meet_info 限流桶烧尽并残留到后续
    用例（进程内共享、按同一测试客户端 IP 计）→ 跨文件顺序依赖在此切断：
    换成全新限流器实例，monkeypatch 在本用例结束后自动还原。
    """
    import app.middleware.rate_limit as rl_mod

    monkeypatch.setattr(
        rl_mod,
        "_meet_info_limiter",
        rl_mod.RateLimiter(max_requests=30, window_seconds=60),
    )
    monkeypatch.setattr(
        rl_mod,
        "_card_info_limiter",
        rl_mod.RateLimiter(max_requests=30, window_seconds=60),
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. 星尘经济闭环：签到 / 手账连续 7 天 / 节点打卡 → 星阶 → 名片
# ═══════════════════════════════════════════════════════════════════════


class TestStardustEconomyClosedLoop:
    """三来源累加 + star_tier 同步 + 名片/状态/相遇公开页透传 + 各来源幂等。"""

    def test_three_sources_accumulate_and_tier_syncs_everywhere(
        self, client: TestClient, monkeypatch
    ):
        _reset_public_limiters(monkeypatch)  # /share/card-info 30/分/IP 桶隔离
        uid, _, headers = _new_user(f"integ-econ-{date.today().isoformat()}")
        try:
            # ── 1) 签到 +1（当天幂等）──
            with mock.patch.object(tasks_api, "date", _FixedToday):
                resp = client.post("/tasks/checkin", headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body["stardust_total"] == 1
            assert body["star_tier"] == tier_for(1) == 0
            with mock.patch.object(tasks_api, "date", _FixedToday):
                resp2 = client.post("/tasks/checkin", headers=headers)
            assert resp2.json()["stardust_total"] == 1  # 同日重复不累加

            # ── 2) 手账连续 7 天 +1（ISO 周幂等）──
            today = date.today()
            backdated = [
                (today - timedelta(days=6), "happy"),
                (today - timedelta(days=5), "calm"),
                (today - timedelta(days=4), "excited"),
                (today - timedelta(days=3), "thoughtful"),
                (today - timedelta(days=2), "happy"),
                (today - timedelta(days=1), "calm"),
            ]
            _seed_diary_entries(uid, backdated)
            resp = client.post(
                "/journal/entries", headers=headers, json={"mood": "happy"}
            )
            assert resp.status_code == 200
            assert resp.json()["streak"] == 7
            assert resp.json()["reward"]  # 连续 7 天 → +1 星尘
            stardust, tier = _fetch_user(uid)
            assert stardust == 2
            assert tier == tier_for(2)
            # 同周重复记录（同日更新）不再发奖励
            resp = client.post(
                "/journal/entries", headers=headers, json={"mood": "calm"}
            )
            assert resp.json()["streak"] == 7
            assert resp.json()["reward"] is False
            stardust, tier = _fetch_user(uid)
            assert stardust == 2

            # ── 3) 节点打卡 +1（节点日幂等）──
            with mock.patch.object(astral_api, "date", _FixedToday):
                resp = client.post(
                    "/astral/activity", headers=headers, json={"event_key": "wish"}
                )
            assert resp.status_code == 200
            assert resp.json()["rewarded"] is True
            assert resp.json()["stardust_total"] == 3
            with mock.patch.object(astral_api, "date", _FixedToday):
                resp = client.post(
                    "/astral/activity", headers=headers, json={"event_key": "wish"}
                )
            assert resp.json()["rewarded"] is False
            assert resp.json()["stardust_total"] == 3  # 重复打卡不累加

            stardust, tier = _fetch_user(uid)
            assert stardust == 3
            assert tier == tier_for(stardust)

            # ── 4) 星阶透传名片（card-info 与用户表一致）──
            code_resp = client.get("/share/invite-code", headers=headers)
            invite_code = code_resp.json()["invite_code"]
            card = client.get(f"/share/card-info?code={invite_code}").json()
            assert card["stardust_total"] == stardust
            assert card["star_tier"] == tier
            assert card["star_tier_name"] == tier_name(tier)

            # ── 5) 任务状态同口径 + 手账月历聚合（前端入口数据源）──
            now = date.today()
            cal = client.get(
                f"/journal/calendar?year={now.year}&month={now.month}",
                headers=headers,
            ).json()
            assert cal["stats"]["current_streak"] >= 1
            assert now.isoformat() in [d["date"] for d in cal["days"]]
            status = client.get("/tasks/status", headers=headers).json()
            assert status["stardust_total"] == stardust
            assert status["star_tier"] == tier
            assert status["star_tier_name"] == tier_name(tier)
        finally:
            _cleanup(uid)


# ═══════════════════════════════════════════════════════════════════════
# 2. 推送体系闭环：槽位分流 + 节点日切换 → 每日 ≤1 条
# ═══════════════════════════════════════════════════════════════════════


class TestPushInvariantOnePerDay:
    """morning/night 分流 + 节点日 + 偏好切换 → 任意组合每日 ≤1 条。"""

    def test_night_user_only_receives_2130_star_word(
        self, client: TestClient, monkeypatch
    ):
        uid, openid, headers = _new_user(f"integ-night-{date.today().isoformat()}")
        calls: list[dict] = []
        try:
            _reset_push_state(monkeypatch)
            monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
            _fake_wechat_ok(monkeypatch, calls)
            # API 契约：授权额度 + 槽位偏好 night
            assert client.post("/notify/subscribe-grant", headers=headers).json()[
                "quota_available"
            ] == 1
            assert client.post(
                "/notify/preference", headers=headers, json={"slot": "night"}
            ).json()["slot_preference"] == "night"

            # 7:37 晨讯不发 night 用户（普通日）：本用户 0 条调用
            _run_morning(NOW_0737)
            assert _calls_for(calls, openid) == []
            # 21:00 星语发 night 用户（AI 禁用 → 短句库兜底，确定性）
            result = _run_night(NOW_2130)
            assert result["status"] == "sent" and result["sent"] >= 1
            mine = _calls_for(calls, openid)
            assert len(mine) == 1
            assert mine[0]["page"] == "pages/moon-card/moon-card"  # 星语 → 月光卡

            # 同日第二次 21:00 跑批：批标记 + last_sent_date 双保险 → 不再发
            again = _run_night(datetime(2026, 8, 11, 22, 0, tzinfo=BEIJING_TZ))
            assert again["status"] == "not_due"
            assert len(_calls_for(calls, openid)) == 1
            # 额度已消费 + last_sent_date 已记（跨槽位共用 1 条/天硬上限）
            quota_left, last_sent = _quota_row(uid)
            assert quota_left == 0
            assert last_sent == date(2026, 8, 11)
        finally:
            _cleanup(uid)

    def test_node_day_morning_version_and_moon_event_stay_one_per_day(
        self, client: TestClient, monkeypatch
    ):
        """节点日（2026-08-12 新月+日全食）：morning 用户 7:37 收节点版晨讯
        （wish 页）；night 用户 21:00 收新月前夜月相事件（wish 页）；两者各自
        当日 ≤1 条；跨日解锁。"""
        uid_a, openid_a, h_a = _new_user(f"integ-nodea-{date.today().isoformat()}")
        uid_b, openid_b, h_b = _new_user(f"integ-nodeb-{date.today().isoformat()}")
        calls: list[dict] = []
        try:
            _reset_push_state(monkeypatch)
            monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
            _fake_wechat_ok(monkeypatch, calls)
            # A: morning 用户、额度 2（晨讯消费 1 条后 21:00 仍持额，验证"已发不重发"）
            client.post("/notify/subscribe-grant", headers=h_a)
            client.post("/notify/subscribe-grant", headers=h_a)
            client.post(
                "/notify/preference", headers=h_a, json={"slot": "morning"}
            )
            # B: night 用户、额度 1（21:00 月相事件日不分槽位全部召回）
            client.post("/notify/subscribe-grant", headers=h_b)
            client.post(
                "/notify/preference", headers=h_b, json={"slot": "night"}
            )

            # ── 7:37 节点版晨讯：仅 A（T3-2 新月当天 → 许愿页）──
            r = _run_morning(datetime(2026, 8, 12, 7, 37, tzinfo=BEIJING_TZ))
            assert r["status"] == "sent" and r["sent"] >= 1
            a_calls = _calls_for(calls, openid_a)
            assert len(a_calls) == 1
            assert a_calls[0]["page"] == "pages/wish/wish"
            assert "新月" in a_calls[0]["data"]["thing1"]["value"]
            assert _calls_for(calls, openid_b) == []  # night 用户不收晨讯

            # ── 21:00 新月前夜月相事件：B 收到节点版（wish），A 已发过 → 跳过 ──
            r = _run_night(datetime(2026, 8, 12, 21, 30, tzinfo=BEIJING_TZ))
            assert r["status"] == "sent" and r["sent"] >= 1
            b_calls = _calls_for(calls, openid_b)
            assert len(b_calls) == 1
            assert b_calls[0]["page"] == "pages/wish/wish"
            assert "新月" in b_calls[0]["data"]["thing1"]["value"]
            assert len(_calls_for(calls, openid_a)) == 1  # A 当日仍 1 条

            # ── 跨日解锁：8/13 早晨 A 再收常规晨讯（1 条/天不变量跨日重置）──
            r = _run_morning(datetime(2026, 8, 13, 7, 37, tzinfo=BEIJING_TZ))
            assert r["status"] == "sent" and r["sent"] >= 1
            a_calls = _calls_for(calls, openid_a)
            assert len(a_calls) == 2
            assert a_calls[1]["page"] == "pages/index/index"  # 普通日 → 首页常规版
            # 两用户配额都恰被消费（A 2 条 = 2 条额度；B 1 条 = 1 条额度）
            assert _quota_row(uid_a)[0] == 0
            assert _quota_row(uid_b)[0] == 0
        finally:
            _cleanup(uid_a, uid_b)

    def test_preference_switch_keeps_one_per_day(self, client: TestClient, monkeypatch):
        """偏好切换：当日已发晨讯后切 night → 当日 21:00 不重发；
        次日按新槽位收星语（无晨讯），每日仍 ≤1 条。"""
        uid, openid, headers = _new_user(f"integ-switch-{date.today().isoformat()}")
        calls: list[dict] = []
        try:
            _reset_push_state(monkeypatch)
            monkeypatch.setattr(settings, "WX_TEMPLATE_DAILY_CARD", "TEST_TMPL")
            _fake_wechat_ok(monkeypatch, calls)
            # 未设置偏好 → 默认 morning（回显契约）
            assert client.get("/notify/preference", headers=headers).json()[
                "slot_preference"
            ] == "morning"
            client.post("/notify/subscribe-grant", headers=headers)
            client.post("/notify/subscribe-grant", headers=headers)

            # 8/13 早 7:37 收晨讯（普通日 → 首页常规版）
            r = _run_morning(datetime(2026, 8, 13, 7, 37, tzinfo=BEIJING_TZ))
            assert r["status"] == "sent" and r["sent"] >= 1
            # 8/13 中午切到 night
            assert client.post(
                "/notify/preference", headers=headers, json={"slot": "night"}
            ).json()["slot_preference"] == "night"
            # 8/13 晚 21:30：已发过（last_sent_date=8/13）→ 不重复
            _run_night(datetime(2026, 8, 13, 21, 30, tzinfo=BEIJING_TZ))
            mine = _calls_for(calls, openid)
            assert len(mine) == 1
            assert mine[0]["page"] == "pages/index/index"

            # 8/14：night 槽位 → 7:37 晨讯不再选他；21:00 星语发 → 当日 1 条
            _run_morning(datetime(2026, 8, 14, 7, 37, tzinfo=BEIJING_TZ))
            assert len(_calls_for(calls, openid)) == 1  # 晨讯未发
            r = _run_night(datetime(2026, 8, 14, 21, 30, tzinfo=BEIJING_TZ))
            assert r["status"] == "sent" and r["sent"] >= 1
            mine = _calls_for(calls, openid)
            assert len(mine) == 2
            assert mine[1]["page"] == "pages/moon-card/moon-card"
            # 两日各 1 条：日期集合精确
            assert {c["data"]["date3"]["value"] for c in mine} == {
                "2026.08.13",
                "2026.08.14",
            }
        finally:
            _cleanup(uid)


# ═══════════════════════════════════════════════════════════════════════
# 3. 分享裂变闭环：四种海报 scene 区分 + 扫码落地
# ═══════════════════════════════════════════════════════════════════════


class TestShareFissionScenes:
    """名片=invite_code / 相遇=m:{meet_id}；月光卡/手账海报复用名片码。"""

    def test_card_code_uses_invite_code_scene(self, client: TestClient, monkeypatch):
        uid, _, headers = _new_user(f"integ-card-{date.today().isoformat()}")
        captured: dict = {}
        try:
            async def _fake_get_wxacode(**kwargs):
                captured.update(kwargs)
                return b"PNG"

            monkeypatch.setattr(share_api, "get_wxacode", _fake_get_wxacode)
            resp = client.get("/share/wxacode", headers=headers)
            assert resp.status_code == 200
            assert resp.content == b"PNG"
            # 名片码：scene=用户邀请码 → card-landing（扫码落地名片页）
            code_resp = client.get("/share/invite-code", headers=headers).json()
            assert captured["scene"] == code_resp["invite_code"]
            assert captured["page"] == "pages/card-landing/card-landing"
        finally:
            _cleanup(uid)

    def test_meet_code_uses_m_meet_id_scene(self, client: TestClient, monkeypatch):
        uid, _, headers = _new_user(
            f"integ-meet-{date.today().isoformat()}", zodiac="aries"
        )
        captured: dict = {}
        try:
            async def _fake_get_wxacode(**kwargs):
                captured.update(kwargs)
                return b"PNG"

            monkeypatch.setattr(meet_api, "get_wxacode", _fake_get_wxacode)
            quick = client.post(
                "/meet/quick",
                headers=headers,
                json={"relation": "friend", "zodiac_b": "taurus"},
            )
            assert quick.status_code == 200
            meet_id = quick.json()["meet_id"]
            resp = client.post(
                "/meet/invite", headers=headers, json={"meet_id": meet_id}
            )
            assert resp.status_code == 200
            # 相遇码：scene=m:{meet_id} → meet-landing（扫码落地 join 流程）
            assert captured["scene"] == f"m:{meet_id}"
            assert captured["page"] == "pages/meet-landing/meet-landing"
        finally:
            _cleanup(uid)

    def test_wxa_code_path_alias_lands_on_meet_landing(
        self, client: TestClient, monkeypatch
    ):
        """T5-1 修复钉住：前端历史调用用 path= 传参 → 必须落到 meet-landing
        （此前被 FastAPI 静默丢弃 → 码指向首页，裂变断链）。"""
        captured: dict = {}

        async def _fake_get_wxacode(**kwargs):
            captured.update(kwargs)
            return b"PNG"

        monkeypatch.setattr(share_api, "get_wxacode", _fake_get_wxacode)
        resp = client.get(
            "/share/wxa-code?path=pages/meet-landing/meet-landing"
            "&width=280&scene=m:test-123"
        )
        assert resp.status_code == 200
        assert captured["page"] == "pages/meet-landing/meet-landing"
        assert captured["scene"] == "m:test-123"
        # 规范参数 page= 同传时优先（新旧双兼容）
        resp = client.get(
            "/share/wxa-code?page=pages/wish/wish&path=pages/review/review"
        )
        assert resp.status_code == 200
        assert captured["page"] == "pages/wish/wish"


# ═══════════════════════════════════════════════════════════════════════
# 4. 情感主线闭环：手账 → 月历聚合 → 月度复盘有料
# ═══════════════════════════════════════════════════════════════════════


class TestEmotionMainlineJournalReview:
    """手账记录 → 月历聚合 → 月度复盘有料 → 海报预览同口径。"""

    def test_journal_entries_feed_monthly_review(self, client: TestClient):
        uid, _, headers = _new_user(f"integ-review-{date.today().isoformat()}")
        try:
            # 钉月（T5-1 审查 Important 修复）：固定 2026-08-12（NODE_DAY），
            # 回填 8/9..8/11 + 今日 = 当月 4 条。若用真实日期，每月 1-3 日回填
            # 天落上月 → days_recorded 当月口径 < 4 确定性失败（月界时间炸弹）；
            # _FixedToday 让测试任何日期运行都绿。
            today = _FixedToday.fixed
            _seed_diary_entries(
                uid,
                [
                    (today - timedelta(days=3), "excited"),
                    (today - timedelta(days=2), "happy"),
                    (today - timedelta(days=1), "calm"),
                ],
            )
            with mock.patch.object(diary_entries, "date", _FixedToday), mock.patch.object(
                journal_api, "date", _FixedToday
            ):
                resp = client.post(
                    "/journal/entries", headers=headers, json={"mood": "thoughtful"}
                )
                assert resp.status_code == 200
                assert resp.json()["streak"] == 4

                # 月历聚合：当月含今日记录 + current_streak ≥ 1
                now = _FixedToday.fixed
                month = f"{now.year:04d}-{now.month:02d}"
                cal = client.get(
                    f"/journal/calendar?year={now.year}&month={now.month}",
                    headers=headers,
                ).json()
                assert cal["stats"]["days_recorded"] >= 4
                assert now.isoformat() in [d["date"] for d in cal["days"]]
                assert cal["stats"]["current_streak"] >= 1

                # 月度复盘有料（AI 禁用 → 降级模板仍非空）＋ 落缓存
                review = client.get(
                    f"/journal/review?month={month}", headers=headers
                ).json()
                assert review["stats"]["days_recorded"] >= 4
                assert review["trend_summary"]
                assert review["mood_series"]
                # 缓存命中（二次请求不重复生成）
                again = client.get(
                    f"/journal/review?month={month}", headers=headers
                ).json()
                assert again["cached"] is True

                # 海报预览：与复盘同口径统计，且无敏感字段
                preview = client.get(
                    f"/journal/review/share-preview?month={month}", headers=headers
                ).json()
                assert preview["stats"]["days_recorded"] == review["stats"][
                    "days_recorded"
                ]
            for key in ("user_id", "nickname", "openid"):
                assert key not in preview
        finally:
            _cleanup(uid)


# ═══════════════════════════════════════════════════════════════════════
# 5. 合盘跨链路：quick → invite → public → join → 双向奖励 + 星阶透传
# ═══════════════════════════════════════════════════════════════════════


class TestMeetInviteChainAndStarTierPassthrough:
    """快速合盘 → 邀请 → 公开页（星阶透传）→ 好友加入 → 双向奖励。"""

    def test_quick_invite_public_join_reward(self, client: TestClient, monkeypatch):
        _reset_public_limiters(monkeypatch)  # /meet/public 30/分/IP 桶隔离
        initiator_id, _, h_a = _new_user(
            f"integ-meeta-{date.today().isoformat()}", zodiac="aries"
        )
        friend_id, _, h_b = _new_user(
            f"integ-meetb-{date.today().isoformat()}", zodiac="taurus"
        )
        captured: dict = {}
        try:
            # 发起人先攒星尘（签到），验证公开页星阶随 tier_for 透传
            with mock.patch.object(tasks_api, "date", _FixedToday):
                client.post("/tasks/checkin", headers=h_a)
            stardust, tier = _fetch_user(initiator_id)
            assert stardust == 1

            async def _fake_get_wxacode(**kwargs):
                captured.update(kwargs)
                return b"PNG"

            monkeypatch.setattr(meet_api, "get_wxacode", _fake_get_wxacode)

            # 1) quick：发起人星座（aries）+ 对方星座
            quick = client.post(
                "/meet/quick",
                headers=h_a,
                json={"relation": "love", "zodiac_b": "taurus"},
            )
            assert quick.status_code == 200
            meet_id = quick.json()["meet_id"]
            assert quick.json()["score"] is not None

            # 2) invite：发起人邀请 → 相遇码 scene=m:{meet_id}
            assert client.post(
                "/meet/invite", headers=h_a, json={"meet_id": meet_id}
            ).status_code == 200
            assert captured["scene"] == f"m:{meet_id}"
            # 非发起人邀请 → 404（归属校验）
            assert client.post(
                "/meet/invite", headers=h_b, json={"meet_id": meet_id}
            ).status_code == 404

            # 3) public：公开页星阶 = 发起人当前星阶（stardust → tier → 名片）
            public = client.get(f"/meet/public/{meet_id}").json()
            assert public["star_tier_name"] == tier_name(tier)
            assert public["meet_id"] == meet_id
            for key in ("invite_code", "openid", "birth_date"):
                assert key not in public

            # 4) 发起人已有名片邀请码 → join 触发双向免费解读奖励
            invite_code = client.get("/share/invite-code", headers=h_a).json()[
                "invite_code"
            ]
            assert invite_code
            join = client.post(
                "/meet/join",
                headers=h_b,
                json={
                    "meet_id": meet_id,
                    "zodiac_b": "taurus",
                    "b_birth_date": "1995-05-20",
                    "b_birth_time": "14:30",
                },
            )
            assert join.status_code == 200
            assert join.json()["reward_granted"] is True
            assert join.json()["score"] is not None

            # 5) 归属校验：双方可见，第三人 404；重复 join 幂等 400
            assert client.get(f"/meet/{meet_id}", headers=h_b).status_code == 200
            assert client.get(f"/meet/{meet_id}", headers=h_a).status_code == 200
            uid_c, _, h_c = _new_user(f"integ-meetc-{date.today().isoformat()}")
            assert client.get(f"/meet/{meet_id}", headers=h_c).status_code == 404
            again = client.post(
                "/meet/join",
                headers=h_b,
                json={"meet_id": meet_id, "zodiac_b": "taurus"},
            )
            assert again.status_code == 400

            # 6) 我的相遇列表：双方都出现该 meet
            assert meet_id in [
                m["meet_id"]
                for m in client.get("/meet/list", headers=h_a).json()["meetings"]
            ]
            assert meet_id in [
                m["meet_id"]
                for m in client.get("/meet/list", headers=h_b).json()["meetings"]
            ]
        finally:
            _cleanup(initiator_id, friend_id, uid_c)
