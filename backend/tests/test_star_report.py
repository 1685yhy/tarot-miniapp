"""
星象月报 · 周报后端测试（SDD P2 · T7-1）。

覆盖：
- period_week_key / week_bounds 周期边界（跨月/跨年周、非法周期）
- last_completed_week（周一当天 → 上周；周日 → 上周；周中 → 上周）
- aggregate_week 纯 SQL 聚合：7 天曲线（无 horoscope 记录日 total=null 不崩溃）、
  星尘统计（checkin + astral_activity_logs）、牌运（次数 + 最常牌 + keywords + 榜）
- 缓存：首次 AI 调 1 次，二次 cached=true 零 AI；force 覆盖缓存
- AI 抛异常 → source=fallback 且统计段完整
- AI 输出含禁词（find_forbidden 口径）→ 视为失败走降级
- 非会员 → locked=true 且 report 为预览结构（键集断言 {curve, note}）
- 会员 → 全文
- 空态周统计 0 + 温柔引导，不发 AI、不落缓存
- 未登录 401；非法周期 422
- 全部使用固定周期 2026-W33（2026-08-10 周一 ~ 2026-08-16 周日），不依赖当前日期

测试数据全部直插 DB（显式日期），无时间炸弹。
"""

import asyncio
import json
import uuid
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import async_session
from app.models.astral_activity_log import AstralActivityLog
from app.models.checkin import CheckIn
from app.models.card import TarotCard
from app.models.diary import DiaryEntry
from app.models.horoscope import HoroscopeHistory
from app.models.reading import DrawnCard, Reading
from app.models.star_report import StarReport
from app.models.user import User
from app.services.star_reports import last_completed_week, period_week_key, week_bounds
from app.utils.auth import create_token

# 固定测试周期：2026-W33 = 2026-08-10(周一) ~ 2026-08-16(周日)
WEEK_START = date(2026, 8, 10)
WEEK_END = date(2026, 8, 16)
PERIOD = "2026-W33"

BLACKLIST_WORDS = ("必", "绝对", "改运", "化解", "转运", "注定", "命", "预测")


# ── helpers ─────────────────────────────────────────────────────────────


def _new_user(
    openid: str, member: bool = False
) -> tuple[str, dict[str, str]]:
    """创建隔离测试用户，返回 (user_id, auth_headers)。"""

    async def _go() -> tuple[str, str]:
        async with async_session() as session:
            user = User(openid=openid, nickname="周报测试", is_member=member)
            session.add(user)
            await session.flush()
            token = create_token(user.id)
            await session.commit()
            return user.id, token

    uid, token = asyncio.run(_go())
    return uid, {"Authorization": f"Bearer {token}"}


def _seed_horoscope(uid: str, days: list[date], energy: dict) -> None:
    """为指定日期插入 HoroscopeHistory 行（energy 四维）。"""

    async def _go() -> None:
        async with async_session() as session:
            for d in days:
                session.add(HoroscopeHistory(
                    user_id=uid, date=d, energy=energy,
                ))
            await session.commit()

    asyncio.run(_go())


def _seed_readings(uid: str, card_ids: list[int]) -> None:
    """插入 N 次占卜（每次一张牌，created_at 依次落在周内）。"""

    async def _go() -> None:
        async with async_session() as session:
            for i, card_id in enumerate(card_ids):
                reading = Reading(
                    id=f"sr-r-{uid[:6]}-{i}",
                    user_id=uid,
                    spread_type="daily",
                    theme="general",
                    created_at=datetime(2026, 8, 10, 10, 0, 0) + (
                        datetime(2026, 8, 17, 0, 0) - datetime(2026, 8, 10, 10, 0, 0)
                    ) * (i / max(len(card_ids), 1)),
                )
                session.add(reading)
                session.add(DrawnCard(
                    reading_id=reading.id,
                    card_id=card_id,
                    position=0,
                    position_name="主牌",
                    is_reversed=False,
                ))
            # 周外一次占卜（必须被排除）
            old = Reading(
                id=f"sr-rold-{uid[:6]}",
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
    """周内 2 次签到 + 1 次节点活动 + 周外 1 次（必须被排除）。"""

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


def _set_card_keywords(card_id: int, keywords: list[str]) -> None:
    async def _go() -> None:
        async with async_session() as session:
            card = (await session.execute(
                select(TarotCard).where(TarotCard.id == card_id)
            )).scalar_one()
            card.keywords_upright = json.dumps(keywords, ensure_ascii=False)
            await session.commit()

    asyncio.run(_go())


def _cache_row(uid: str) -> dict | None:
    """读周报缓存行（week 类型）。"""

    async def _go() -> dict | None:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(StarReport).where(
                        StarReport.user_id == uid,
                        StarReport.report_type == "week",
                        StarReport.period_key == PERIOD,
                    )
                )
            ).scalar_one_or_none()
            return json.loads(row.data) if row else None

    return asyncio.run(_go())


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


class _FakeChat:
    def __init__(self, content: str):
        self.completions = _FakeCompletions(content)


class _FakeAIClient:
    def __init__(self, content: str):
        self.chat = _FakeChat(content)


def _boom():
    async def _raise(*a, **k):
        raise RuntimeError("ai down")

    return SimpleNamespace(chat=SimpleNamespace(completions=_raise))


AI_WEEK_NOTE_JSON = '{"note": "这一周星象在缓慢转向，你抽到最多的牌，是一盏总在提醒你慢下来的灯。"}'
AI_WEEK_NOTE_JSON_B = '{"note": "重新生成的一周寄语，星光继续陪你。"}'
AI_WEEK_BLACKLIST_JSON = '{"note": "这一周注定会有好运。"}'


def _assert_no_blacklist(text: str | None) -> None:
    if text is None:
        return
    for word in BLACKLIST_WORDS:
        assert word not in text, f"文案含黑名单词「{word}」: {text}"


# ── 周期边界纯函数 ───────────────────────────────────────────────────────


class TestWeekKeys:
    def test_period_week_key_basic(self):
        assert period_week_key(date(2026, 8, 10)) == "2026-W33"
        assert period_week_key(date(2026, 8, 16)) == "2026-W33"
        assert period_week_key(date(2026, 8, 9)) == "2026-W32"

    def test_week_bounds_monday_to_sunday(self):
        assert week_bounds("2026-W33") == (WEEK_START, WEEK_END)

    def test_week_bounds_cross_year(self):
        # 2026-W01 的周一落在 2025-12-29（跨年周）
        assert week_bounds("2026-W01") == (date(2025, 12, 29), date(2026, 1, 4))
        # 2026-W53 的周日落在 2027-01-03
        assert week_bounds("2026-W53") == (date(2026, 12, 28), date(2027, 1, 3))

    def test_week_bounds_invalid(self):
        for bad in ("2026-W99", "2026W33", "abc", "2026-08", "2026-W00"):
            with pytest.raises(ValueError):
                week_bounds(bad)

    def test_week_key_roundtrip(self):
        for day in (WEEK_START, WEEK_END):
            start, end = week_bounds(period_week_key(day))
            assert start <= day <= end

    def test_last_completed_week(self):
        # 周一当天 → 上周
        assert last_completed_week(date(2026, 8, 10)) == "2026-W32"
        # 周日 → 上周（本周尚未完成）
        assert last_completed_week(date(2026, 8, 16)) == "2026-W32"
        # 周中 → 上周
        assert last_completed_week(date(2026, 8, 12)) == "2026-W32"
        # 跨年边界：2027-01-04（周一）→ 2026-W53
        assert last_completed_week(date(2027, 1, 4)) == "2026-W53"


# ── 聚合（纯 SQL）────────────────────────────────────────────────────────


class TestAggregateWeek:
    def test_aggregate_curve_7_days_with_null_gaps(self):
        """7 天曲线逐日；无 horoscope 记录日 total=null 不崩溃。"""
        from app.services.star_reports import aggregate_week

        uid, _ = _new_user("agg_curve")
        _seed_horoscope(uid, [date(2026, 8, 10), date(2026, 8, 16)],
                        {"love": 80, "career": 70, "social": 60, "health": 50})
        # 另一用户同日记录不影响本人曲线（隔离）
        other_uid, _ = _new_user("agg_curve_other")
        _seed_horoscope(other_uid, [date(2026, 8, 10)],
                        {"love": 10, "career": 10, "social": 10, "health": 10})

        async def _go() -> dict:
            async with async_session() as session:
                user = await session.get(User, uid)
                return await aggregate_week(session, user, WEEK_START, WEEK_END)

        stats = asyncio.run(_go())
        curve = stats["curve"]
        assert len(curve) == 7
        assert [p["date"] for p in curve] == [
            "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13",
            "2026-08-14", "2026-08-15", "2026-08-16",
        ]
        assert curve[0]["total"] == 80 + 70 + 60 + 50 == 260
        assert curve[6]["total"] == 260
        for p in curve[1:6]:
            assert p["total"] is None, "无记录日 total 应为 null"

    def test_aggregate_stardust_and_cards(self):
        """星尘统计（签到+节点活动）+ 牌运（N 次 + 最常牌 + keywords + 榜）。"""
        from app.services.star_reports import aggregate_week

        uid, _ = _new_user("agg_full")
        _seed_stardust(uid)
        _seed_readings(uid, [1, 1, 1, 2])
        _set_card_keywords(1, ["勇气", "开始", "冒险"])
        _set_card_keywords(2, ["等待"])

        async def _go() -> dict:
            async with async_session() as session:
                user = await session.get(User, uid)
                return await aggregate_week(session, user, WEEK_START, WEEK_END)

        stats = asyncio.run(_go())
        # 星尘：周内 2 签到 + 1 节点活动；周外签到排除
        assert stats["stardust"] == {"checkin_days": 2, "activity_events": 1, "total": 3}
        # 牌运：4 次占卜（周外 1 次排除），最常牌 卡牌1
        assert stats["cards"]["readings_count"] == 4
        assert stats["cards"]["most_card"]["name"] == "卡牌1"
        assert stats["cards"]["most_card"]["count"] == 3
        assert stats["cards"]["most_card"]["keywords"] == ["勇气", "开始", "冒险"]
        assert stats["cards"]["card_list"] == [
            {"name": "卡牌1", "count": 3},
            {"name": "卡牌2", "count": 1},
        ]

    def test_aggregate_most_card_tie_deterministic(self):
        """最常牌平局：两张牌同次数 → 取卡名排序最前一张；同人同周期结果确定。"""
        from app.services.star_reports import aggregate_week

        uid, _ = _new_user("agg_tie")
        _seed_readings(uid, [3, 4])  # 各 1 次 → 平局
        _set_card_keywords(3, ["平衡"])
        _set_card_keywords(4, ["稳固"])

        async def _go() -> dict:
            async with async_session() as session:
                user = await session.get(User, uid)
                return await aggregate_week(session, user, WEEK_START, WEEK_END)

        stats = asyncio.run(_go())
        assert stats["cards"]["readings_count"] == 2
        # 平局规则：卡名升序首见者（"卡牌3" < "卡牌4"）
        assert stats["cards"]["most_card"] == {
            "name": "卡牌3", "count": 1, "keywords": ["平衡"],
        }
        assert stats["cards"]["card_list"] == [
            {"name": "卡牌3", "count": 1},
            {"name": "卡牌4", "count": 1},
        ]

    def test_aggregate_empty_week_zero_stats(self):
        """空态周：统计全 0，曲线 7 天 total 全 null，不报错。"""
        from app.services.star_reports import aggregate_week

        uid, _ = _new_user("agg_empty")

        async def _go() -> dict:
            async with async_session() as session:
                user = await session.get(User, uid)
                return await aggregate_week(session, user, WEEK_START, WEEK_END)

        stats = asyncio.run(_go())
        assert all(p["total"] is None for p in stats["curve"])
        assert stats["stardust"]["total"] == 0
        assert stats["cards"]["readings_count"] == 0
        assert stats["cards"]["most_card"] is None
        assert stats["cards"]["card_list"] == []
        assert len(stats["color_band"]) == 7
        for p in stats["color_band"]:
            assert p["star_color"]


# ── 端点：缓存 / 降级 / 权益 ─────────────────────────────────────────────


class TestWeekEndpoint:
    def test_week_report_requires_auth(self, client: TestClient):
        assert client.get("/report/week").status_code == 401

    def test_week_report_invalid_period_422(self, client: TestClient):
        uid, headers = _new_user("week_bad_period")
        assert client.get(
            "/report/week?period=2026-W99", headers=headers
        ).status_code == 422
        assert client.get(
            "/report/week?period=abc", headers=headers
        ).status_code == 422

    def test_week_report_member_full_and_cache_ai_once(
        self, client: TestClient, monkeypatch
    ):
        """会员：全文；首次 AI 调 1 次，二次 cached=true 零 AI。"""
        uid, headers = _new_user("week_member", member=True)
        _seed_stardust(uid)
        _seed_readings(uid, [1, 1, 2])
        _set_card_keywords(1, ["勇气", "开始"])
        _seed_horoscope(uid, [date(2026, 8, 12)],
                        {"love": 90, "career": 90, "social": 90, "health": 90})

        fake = _FakeAIClient(AI_WEEK_NOTE_JSON)
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: fake)

        resp1 = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp1.status_code == 200, resp1.text
        d1 = resp1.json()
        assert d1["period"] == PERIOD
        assert d1["week_range"] == ["2026-08-10", "2026-08-16"]
        assert d1["locked"] is False
        assert d1["preview"] is False
        assert d1["cached"] is False
        assert d1["source"] == "ai"
        # 全文键集
        report = d1["report"]
        assert set(report.keys()) == {"curve", "stardust", "cards", "color_band", "note"}
        assert len(report["curve"]) == 7
        assert report["stardust"]["total"] == 3
        assert report["cards"]["readings_count"] == 3
        assert report["cards"]["most_card"]["name"] == "卡牌1"
        assert len(report["color_band"]) == 7
        assert len(report["note"]) <= 60, "AI 寄语应 ≤60 字"
        _assert_no_blacklist(report["note"])

        # AI prompt 校验：system 含输出红线，user 含本周数据
        calls = fake.chat.completions.calls
        assert len(calls) == 1, "首次生成应恰好调用一次 AI"
        system_content = calls[0]["messages"][0]["content"]
        user_content = calls[0]["messages"][1]["content"]
        assert "输出红线" in system_content
        assert "卡牌1" in user_content

        # 第二次命中缓存：零 AI
        resp2 = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp2.status_code == 200
        d2 = resp2.json()
        assert d2["cached"] is True
        assert d2["source"] == "ai"
        assert d2["report"]["note"] == d1["report"]["note"]
        assert len(fake.chat.completions.calls) == 1, "缓存命中不应再调 AI"

    def test_week_report_force_regenerates(
        self, client: TestClient, monkeypatch
    ):
        """force=true 覆盖缓存并重新调 AI。"""
        uid, headers = _new_user("week_force", member=True)
        _seed_readings(uid, [1])

        fake = _FakeAIClient(AI_WEEK_NOTE_JSON)
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: fake)

        r1 = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert r1.json()["cached"] is False

        r2 = client.get(f"/report/week?period={PERIOD}&force=1", headers=headers)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["cached"] is False, "force 应重新生成而非命中缓存"
        assert len(fake.chat.completions.calls) == 2

        # 缓存被覆盖为同一份新内容
        assert _cache_row(uid) is not None

    def test_week_report_ai_throws_falls_back(
        self, client: TestClient, monkeypatch
    ):
        """AI 抛异常 → source=fallback 且统计段完整。"""
        uid, headers = _new_user("week_boom", member=True)
        _seed_stardust(uid)
        _seed_readings(uid, [1, 1])
        _seed_horoscope(uid, [date(2026, 8, 15)],
                        {"love": 90, "career": 90, "social": 90, "health": 90})

        monkeypatch.setattr("app.services.star_reports._get_ai_client", _boom)

        resp = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["source"] == "fallback"
        report = d["report"]
        assert len(report["curve"]) == 7
        assert report["stardust"]["total"] == 3
        assert report["cards"]["readings_count"] == 2
        assert report["cards"]["most_card"]["count"] == 2
        assert report["note"], "降级后仍应有寄语"
        _assert_no_blacklist(report["note"])
        # 降级结果同样落缓存
        assert _cache_row(uid) is not None

    def test_week_report_ai_blacklist_falls_back(
        self, client: TestClient, monkeypatch
    ):
        """AI 输出含共享禁词（find_forbidden 口径）→ 视为失败走降级模板。"""
        uid, headers = _new_user("week_blacklist", member=True)
        _seed_readings(uid, [1])
        _seed_horoscope(uid, [date(2026, 8, 10)],
                        {"love": 90, "career": 90, "social": 90, "health": 90})

        fake = _FakeAIClient(AI_WEEK_BLACKLIST_JSON)
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: fake)

        resp = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["source"] == "fallback"
        _assert_no_blacklist(d["report"]["note"])
        assert "注定" not in d["report"]["note"]

    def test_week_report_nonmember_preview(self, client: TestClient, monkeypatch):
        """非会员 → locked=true 且 report 为预览结构（键集断言 curve+note）。"""
        uid, headers = _new_user("week_free")
        _seed_readings(uid, [1, 2, 2])
        _seed_horoscope(uid, [date(2026, 8, 11)],
                        {"love": 70, "career": 70, "social": 70, "health": 70})

        # AI 隔离：不依赖真实 key/网络，避免真实付费调用（测试只关心预览结构）
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)

        resp = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["locked"] is True
        assert d["preview"] is True
        assert set(d["report"].keys()) == {"curve", "note"}, "预览应只有曲线+1 段寄语"
        assert len(d["report"]["curve"]) == 7
        assert d["report"]["note"], "预览含 1 段寄语"
        # 预览态同样落缓存（解锁后无需重生成）
        assert _cache_row(uid) is not None

    def test_week_report_empty_week(self, client: TestClient, monkeypatch):
        """空态周：统计 0 + 温柔引导；不发 AI、不落缓存、可重复请求。"""
        uid, headers = _new_user("week_empty", member=True)

        fake = _FakeAIClient(AI_WEEK_NOTE_JSON)
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: fake)

        resp = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["cached"] is False
        assert d["source"] is None
        assert d["locked"] is False
        report = d["report"]
        assert len(report["curve"]) == 7
        assert all(p["total"] is None for p in report["curve"])
        assert report["stardust"] == {"checkin_days": 0, "activity_events": 0, "total": 0}
        assert report["cards"]["readings_count"] == 0
        assert report["cards"]["most_card"] is None
        assert report["note"], "空态周应有温柔引导文案"
        _assert_no_blacklist(report["note"])
        assert len(fake.chat.completions.calls) == 0, "空态周不应调 AI"
        assert _cache_row(uid) is None, "空态周不落缓存"

        # 再请求仍稳定
        resp2 = client.get(f"/report/week?period={PERIOD}", headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["cached"] is False

    def test_week_report_fallback_tiers_by_energy(self, client: TestClient, monkeypatch):
        """降级文案按能量均值三档（≥4/≥3/<3）；无 key 时直接走降级。"""
        # AI 隔离：断言 source==fallback 依赖 AI 不可用，必须钉死 _get_ai_client
        monkeypatch.setattr("app.services.star_reports._get_ai_client", lambda: None)
        # 高能量周：四维 95 → 总分 380 → 均值星 4.75 → 高档
        hi_uid, hi_headers = _new_user("week_hi", member=True)
        _seed_horoscope(hi_uid, [WEEK_START],
                        {"love": 95, "career": 95, "social": 95, "health": 95})
        r_hi = client.get(f"/report/week?period={PERIOD}", headers=hi_headers)
        assert r_hi.status_code == 200
        assert r_hi.json()["source"] == "fallback"
        note_hi = r_hi.json()["report"]["note"]

        # 低能量周：四维 35 → 总分 140 → 均值星 1.75 → 低档
        lo_uid, lo_headers = _new_user("week_lo", member=True)
        _seed_horoscope(lo_uid, [WEEK_START],
                        {"love": 35, "career": 35, "social": 35, "health": 35})
        r_lo = client.get(f"/report/week?period={PERIOD}", headers=lo_headers)
        assert r_lo.status_code == 200
        note_lo = r_lo.json()["report"]["note"]

        assert note_hi != note_lo, "不同能量档位应给出不同降级文案"
        _assert_no_blacklist(note_hi)
        _assert_no_blacklist(note_lo)


# ── 抽取回归：service 区间函数供 /weekly 委托 ────────────────────────────


class TestRangeDelegation:
    def test_get_readings_for_range_boundaries(self):
        """区间查询：起始日 00:00 起、结束日 23:59 止，含首尾日。"""
        from app.services.star_reports import get_readings_for_range

        uid, _ = _new_user("range_readings")
        _seed_readings(uid, [1])  # 周内 1 次（08-10 10:00）+ 周外 1 次（08-01）

        async def _go() -> int:
            async with async_session() as session:
                rows = await get_readings_for_range(session, uid, WEEK_START, WEEK_END)
                return len(rows)

        assert asyncio.run(_go()) == 1

    def test_get_diary_entries_for_range_boundaries(self):
        """日记区间查询：entry_date 含首尾日。"""
        from app.services.star_reports import get_diary_entries_for_range

        uid, _ = _new_user("range_diary")

        async def _go() -> int:
            async with async_session() as session:
                for d in (date(2026, 8, 10), date(2026, 8, 16), date(2026, 8, 1)):
                    session.add(DiaryEntry(
                        id=str(uuid.uuid4()),
                        user_id=uid, entry_date=d, mood="calm",
                        reflection="测试",
                    ))
                await session.commit()
                rows = await get_diary_entries_for_range(session, uid, WEEK_START, WEEK_END)
                return len(rows)

        assert asyncio.run(_go()) == 2
