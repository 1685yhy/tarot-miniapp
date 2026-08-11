"""
星空时刻表（SDD P1 · T3-1）测试：/astral/calendar + /astral/events/{date} + /astral/event/{type}

覆盖：
- 区间展开：2026-01-14~02-04 每一天 events 含 mercury_retrograde（含端点日期）
- 同日多事件：2026-08-12 狮子座新月 + 日全食 → 两条、按 ASTRAL_TYPE_PRIORITY
  排序（solar_eclipse 在前）、activity=info（由最高优先级决定，确定性钉住）
- 无事件日：phase 字段非空、activity=info、guidance 走中性宜忌池
- next_event 倒计时（参数化 today）：跨月取首个、当天取当日首个、空表 None
- 2027 空表：不崩溃、days 全空 events、phase 仍非空
- node_content 四形态字段完整；mercury_guide range 空态规格化（末次水逆后
  空对象、键恒在）；7 件小事清单 ≥7 条且无黑名单词；daily_sentence 同日恒定
  且属于轮换池
- wish window days_left 边界（新月日/窗口末日/窗口外/跨月）；2027 回退月相引擎
- API：未登录 401；登录后 200 且字段完整；calendar next_event 用固定 today
  参数化比对（不依赖真实日期，任何日期跑都绿）；wish/review 的 wish_counts
  接 db（双向用户隔离，真实用户 id 播种）；非法 month / 未知事件类型 /
  非法日期 → 4xx
"""

import asyncio
from datetime import date, timedelta
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.astral as astral_api
from app.db.database import async_session
from app.models.astral_activity_log import AstralActivityLog
from app.models.user import User
from app.models.wish import Wish
from app.services.astral_calendar import (
    MERCURY_CARE_ITEMS,
    MERCURY_DAILY_SENTENCES,
    day_detail,
    month_view,
    node_content,
)
from app.services.moon import next_full_moon_after, next_new_moon_after
from app.services.stardust import tier_for
from app.utils.auth import create_token

# 与用户决策禁词表对齐（2026-08-11 确认）：必/绝对/改运/化解/转运/注定/命
# + 现有 预测/明天一定会；字符级口径（含"不必""必定"等含"必"形态）
BLACKLIST_WORDS = ("必", "绝对", "改运", "化解", "转运", "注定", "命", "预测", "明天一定会")

PHASE_KEYS = {"new_moon", "waxing", "first_quarter", "full_moon", "last_quarter", "waning"}


# ── helpers ─────────────────────────────────────────────────────────────


def _new_user(openid: str) -> tuple[str, dict[str, str]]:
    """创建隔离测试用户，返回 (user_id, auth_headers)。"""

    async def _go() -> tuple[str, str]:
        async with async_session() as session:
            user = User(openid=openid, nickname="星象日历测试")
            session.add(user)
            await session.flush()
            token = create_token(user.id, user.token_version)
            await session.commit()
            return user.id, token

    uid, token = asyncio.run(_go())
    return uid, {"Authorization": f"Bearer {token}"}


class _FixedToday(date):
    """date 子类：today() 返回固定日期（把 API 层的 date.today() 钉死，用于参数化）。"""

    fixed: date = date(2026, 8, 11)

    @classmethod
    def today(cls) -> date:
        return cls.fixed


def _seed_wishes(user_id: str, statuses: list[str]) -> None:
    """为用户批量写入愿望（按给定状态）。"""

    async def _go() -> None:
        async with async_session() as session:
            for i, status in enumerate(statuses):
                session.add(Wish(user_id=user_id, content=f"测试愿望{i}", status=status))
            await session.commit()

    asyncio.run(_go())


# ── month_view：区间展开 / 同日多事件 / 月相 / next_event ────────────────


def test_month_view_retrograde_range_expanded_every_day():
    """水逆区间 2026-01-14 ~ 2026-02-04（含端点）每一天 events 都含 mercury_retrograde。"""
    start, end = date(2026, 1, 14), date(2026, 2, 4)
    # 区间跨 1/2 两月，合并两个视图按日期索引
    views = [
        month_view(2026, 1, today=date(2026, 2, 10)),
        month_view(2026, 2, today=date(2026, 2, 10)),
    ]
    by_date = {d["date"]: d for view in views for d in view["days"]}

    d = start
    while d <= end:
        day = by_date[d.isoformat()]
        types = {ev["type"] for ev in day["events"]}
        assert "mercury_retrograde" in types, f"{d} 应含水逆"
        assert day["is_retrograde_range"] is True, f"{d} 应为逆行区间日"
        d += timedelta(days=1)


def test_month_view_multi_event_day_sorted_by_priority():
    """2026-08-12 狮子座新月 + 日全食：两条事件、按优先级排序、新月带落座。"""
    view = month_view(2026, 8, today=date(2026, 8, 9))
    day = next(d for d in view["days"] if d["date"] == "2026-08-12")
    assert [ev["type"] for ev in day["events"]] == ["solar_eclipse", "new_moon"]
    labels = [ev["label"] for ev in day["events"]]
    assert "狮子座日全食" in labels and "狮子座新月" in labels
    new_moon = next(ev for ev in day["events"] if ev["type"] == "new_moon")
    assert new_moon["moon_sign"] == "狮子"
    assert day["is_retrograde_range"] is False


def test_month_view_phase_present_every_day():
    """每一天都有月相小字（phase/emoji/label 非空）。"""
    view = month_view(2026, 2, today=date(2026, 2, 10))
    assert len(view["days"]) == 28
    for day in view["days"]:
        phase = day["phase"]
        assert phase["phase"] in PHASE_KEYS
        assert phase["emoji"] and phase["label"]


def test_month_view_no_event_day():
    """2026-02-10 无事件日：events 空、is_retrograde_range False、phase 非空。"""
    view = month_view(2026, 2, today=date(2026, 2, 10))
    day = next(d for d in view["days"] if d["date"] == "2026-02-10")
    assert day["events"] == []
    assert day["is_retrograde_range"] is False
    assert day["phase"]["phase"] in PHASE_KEYS


def test_month_view_next_event_countdown():
    """next_event 倒计时（参数化 today）：跨月取首个 / 当天取当日首个 / 空表 None。"""
    # 2026-02-10 → 首个事件为 02-17 满月，days_until=7
    view = month_view(2026, 2, today=date(2026, 2, 10))
    assert view["next_event"] == {
        "type": "full_moon",
        "label": "满月",
        "date": "2026-02-17",
        "days_until": 7,
    }
    # 当天有事件 → 取当日优先级最高的首个（08-12 日全食）
    view = month_view(2026, 8, today=date(2026, 8, 12))
    assert view["next_event"] == {
        "type": "solar_eclipse",
        "label": "狮子座日全食",
        "date": "2026-08-12",
        "days_until": 0,
    }
    # 年末无后续事件 → None
    view = month_view(2026, 12, today=date(2026, 12, 31))
    assert view["next_event"] is None


def test_month_view_2027_empty_no_crash():
    """2027 表中无事件：不崩溃、days 全空 events、phase 仍非空、next_event None。"""
    view = month_view(2027, 1, today=date(2027, 1, 1))
    assert len(view["days"]) == 31
    for day in view["days"]:
        assert day["events"] == []
        assert day["is_retrograde_range"] is False
        assert day["phase"]["phase"] in PHASE_KEYS
    assert view["next_event"] is None


# ── day_detail：同日多事件 / 无事件日 ────────────────────────────────────


def test_day_detail_multi_event_activity_and_guidance():
    """2026-08-12：activity=info 由最高优先级 solar_eclipse 决定；guidance 复用宜忌库。"""
    detail = day_detail(date(2026, 8, 12))
    assert detail["date"] == "2026-08-12"
    assert detail["activity"] == "info"
    assert detail["guidance"] == {"do": "宜·开启新篇", "dont": "忌·原地打转"}
    assert [ev["type"] for ev in detail["events"]] == ["solar_eclipse", "new_moon"]
    for ev in detail["events"]:
        assert ev["note"], f"{ev['type']} 应有 note 文案"


def test_day_detail_no_event_day_neutral():
    """无事件日：activity=info、events 空、guidance 走中性宜忌池。"""
    detail = day_detail(date(2026, 2, 10))
    assert detail["activity"] == "info"
    assert detail["events"] == []
    assert detail["guidance"]["do"].startswith("宜·")
    assert detail["guidance"]["dont"].startswith("忌·")


# ── node_content：wish / review / mercury_guide / info ───────────────────


def test_node_content_wish_shape():
    """wish 节点：窗口=最近新月日 00:00 至其后 2 天，days_left 从今天倒计。"""
    node = node_content("wish", date(2026, 8, 12))
    assert node["type"] == "wish"
    assert node["title"] == "许愿之夜"
    assert node["window"] == {
        "start": "2026-08-12",
        "end": "2026-08-14",
        "days_left": 2,
    }
    assert node["content"] == "写给月亮的三行愿望"
    assert node["target_page"] == "pages/wish/wish"
    # 未传 wish_counts → 全零
    assert node["wish_counts"] == {"active": 0, "grown": 0, "answered": 0}


def test_node_content_wish_window_boundaries():
    """wish window days_left 边界：窗口末日=0 / 窗口前倒计 / 窗口后滚到下一新月。"""
    # 新月日当天 → days_left=2
    assert node_content("wish", date(2026, 8, 12))["window"]["days_left"] == 2
    # 窗口末日（新月+2 天）→ 0
    assert node_content("wish", date(2026, 8, 14))["window"]["days_left"] == 0
    # 窗口前 3 天 → 目标 08-12，days_left=5
    assert node_content("wish", date(2026, 8, 9))["window"] == {
        "start": "2026-08-12",
        "end": "2026-08-14",
        "days_left": 5,
    }
    # 窗口结束后 → 滚到下一新月 09-11，days_left=(09-13 - 08-15)=29
    assert node_content("wish", date(2026, 8, 15))["window"] == {
        "start": "2026-09-11",
        "end": "2026-09-13",
        "days_left": 29,
    }


def test_node_content_wish_window_2027_fallback():
    """2027 表中无新月事件 → 回退月相引擎 next_new_moon_after（不崩溃、可算）。"""
    today = date(2027, 1, 5)
    expected_start = next_new_moon_after(today)
    node = node_content("wish", today)
    assert node["window"]["start"] == expected_start.isoformat()
    assert node["window"]["end"] == (expected_start + timedelta(days=2)).isoformat()
    assert node["window"]["days_left"] == (expected_start + timedelta(days=2) - today).days


def test_node_content_review_shape():
    """review 节点：复盘之夜 + wish_counts 透传 + target_page + 打卡门控窗口。

    window.start = 最近满月日（2026-08-12 视角下一满月 09-27），供前端
    打卡「当天门控」比对（today === window.start）。
    """
    node = node_content(
        "review",
        date(2026, 8, 12),
        wish_counts={"active": 2, "grown": 1, "answered": 0},
    )
    assert node == {
        "type": "review",
        "title": "复盘之夜",
        "window": {
            "start": "2026-09-27",
            "end": "2026-09-27",
            "days_left": 46,
        },
        "wish_counts": {"active": 2, "grown": 1, "answered": 0},
        "target_page": "pages/review/review",
    }


def test_node_content_review_window_full_moon_day():
    """满月当天 → review window.start = 当天（start=end、days_left=0），打卡门控放行。"""
    node = node_content("review", date(2026, 1, 11))
    assert node["window"] == {
        "start": "2026-01-11",
        "end": "2026-01-11",
        "days_left": 0,
    }


def test_node_content_review_window_2027_fallback():
    """2027 无表内满月 → 回退月相引擎 next_full_moon_after（门控数据仍可算）。"""
    today = date(2027, 1, 5)
    expected = next_full_moon_after(today)
    node = node_content("review", today)
    assert node["window"]["start"] == expected.isoformat()
    assert node["window"]["end"] == expected.isoformat()


def test_node_content_mercury_guide_shape():
    """mercury_guide 节点：慢行期 + 当前逆行区间 + 固定清单 + 确定性句子。"""
    node = node_content("mercury_guide", date(2026, 1, 20))
    assert node["type"] == "mercury_guide"
    assert node["title"] == "慢行期"
    assert node["range"] == {
        "start": "2026-01-14",
        "end": "2026-02-04",
        "days_left": 15,
    }
    assert len(node["items"]) == 7
    assert node["daily_sentence"] in MERCURY_DAILY_SENTENCES
    # 同日同人恒定
    assert node_content("mercury_guide", date(2026, 1, 20))["daily_sentence"] == node["daily_sentence"]


def test_node_content_mercury_guide_upcoming_range():
    """区间外 → 取下一个水逆区间（2026-02-10 → 03-30~04-22，days_left=71）。"""
    node = node_content("mercury_guide", date(2026, 2, 10))
    assert node["range"] == {
        "start": "2026-03-30",
        "end": "2026-04-22",
        "days_left": 71,
    }


def test_node_content_mercury_guide_empty_range():
    """末次水逆（2026-09-18~10-10）之后 / 2027 无逆行期：range 为规格化空对象。"""
    assert node_content("mercury_guide", date(2026, 12, 31))["range"] == {
        "start": "",
        "end": "",
        "days_left": 0,
    }
    assert node_content("mercury_guide", date(2027, 1, 1))["range"] == {
        "start": "",
        "end": "",
        "days_left": 0,
    }


def test_node_content_info_shape():
    """info 节点：notes 文案列表（其余事件类型的说明）。"""
    node = node_content("info", date(2026, 8, 12))
    assert node["type"] == "info"
    assert len(node["notes"]) == 4
    assert all(n for n in node["notes"])


def test_care_items_and_sentences_compliance():
    """7 件小事 =7 条（与标题「慢下来的 7 件小事」对齐，T3-5 Fix 契约）、
    句子池 ≥12 条，且全部无黑名单词。"""
    assert len(MERCURY_CARE_ITEMS) == 7
    assert len(MERCURY_DAILY_SENTENCES) >= 12
    all_texts = list(MERCURY_CARE_ITEMS) + list(MERCURY_DAILY_SENTENCES)
    for text in all_texts:
        assert len(text) > 0
        for word in BLACKLIST_WORDS:
            assert word not in text, f"文案含禁词「{word}」: {text}"


# ── API 端点 ─────────────────────────────────────────────────────────────


def test_api_requires_auth(client: TestClient):
    """三端点未登录一律 401。"""
    assert client.get("/astral/calendar", params={"year": 2026, "month": 8}).status_code == 401
    assert client.get("/astral/events/2026-08-12").status_code == 401
    assert client.get("/astral/event/new_moon").status_code == 401


@pytest.mark.parametrize(
    "fixed_today",
    [
        date(2026, 1, 1),   # 年初：首个事件 01-03 摩羯新月
        date(2026, 8, 11),  # 日食前一天
        date(2026, 8, 13),  # 日食后、处暑前（旧断言的时间炸弹场景）
        date(2026, 8, 23),  # 处暑当天
        date(2026, 9, 1),   # 处暑后：首个事件 09-08 白露
        date(2026, 12, 31),  # 年末无后续事件 → None
        date(2027, 1, 1),   # 2027 空表 → None
    ],
)
def test_api_calendar_ok(client: TestClient, fixed_today: date):
    """登录后月历 200：字段完整、08-12 两条事件；next_event 固定 today 参数化比对。

    不依赖真实 date.today()：旧版断言真实 today 计算出的 next_event 必为
    solar_eclipse/2026-08-12，2026-08-13 起真实 today 的首个事件变为 08-23
    处暑 → 必挂（时间炸弹）。现把 API 层 today 钉为固定日期，期望值由同源
    纯函数 month_view 算出再与响应比对，任何日期跑都绿。
    """
    _, headers = _new_user(f"openid_calendar_{fixed_today.isoformat().replace('-', '')}")
    with mock.patch.object(astral_api, "date", _FixedToday):
        _FixedToday.fixed = fixed_today
        resp = client.get("/astral/calendar", params={"year": 2026, "month": 8}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026 and body["month"] == 8
    assert len(body["days"]) == 31
    day = next(d for d in body["days"] if d["date"] == "2026-08-12")
    assert [ev["type"] for ev in day["events"]] == ["solar_eclipse", "new_moon"]
    # next_event：期望 = 固定 today 调 month_view（与 API 同源逻辑），全字段比对
    assert body["next_event"] == month_view(2026, 8, today=fixed_today)["next_event"]
    # 钉住时间炸弹场景的具体形态：日食后首个事件是 08-23 处暑（而非 08-12 日食）
    if fixed_today == date(2026, 8, 13):
        assert body["next_event"]["type"] == "solar_term"
        assert body["next_event"]["date"] == "2026-08-23"
    # 钉住空态：年末 / 2027 无后续事件 → None
    if fixed_today >= date(2026, 12, 31):
        assert body["next_event"] is None


def test_api_day_events_ok(client: TestClient):
    """登录后日详情 200：activity/guidance/events 完整。"""
    _, headers = _new_user("openid_day_ok")
    resp = client.get("/astral/events/2026-08-12", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-08-12"
    assert body["activity"] == "info"
    assert body["guidance"]["do"] == "宜·开启新篇"
    assert len(body["events"]) == 2


def test_api_event_node_wish_counts_from_db(client: TestClient):
    """wish 节点 wish_counts 接 db（按用户隔离：他人愿望不计入）。"""
    uid, headers = _new_user("openid_wish_counts")
    other_uid, other_headers = _new_user("openid_wish_counts_other")
    _seed_wishes(uid, ["active", "active", "grown"])
    # 用真实第二个用户 id 播种（旧版用不存在的 id，依赖 SQLite FK 关闭）
    _seed_wishes(other_uid, ["active", "answered"])

    resp = client.get("/astral/event/new_moon", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "wish"
    assert body["title"] == "许愿之夜"
    assert body["window"]["days_left"] >= 0
    assert body["wish_counts"] == {"active": 2, "grown": 1, "answered": 0}

    # 他人视角只看到自己的愿望（双向隔离钉死：真实播种的 other_uid 计 1/0/1）
    resp_other = client.get("/astral/event/new_moon", headers=other_headers)
    assert resp_other.json()["wish_counts"] == {"active": 1, "grown": 0, "answered": 1}


def test_api_event_node_types(client: TestClient):
    """事件类型 → 节点形态：full_moon→review、mercury_retrograde→mercury_guide、其余→info。"""
    _, headers = _new_user("openid_node_types")
    resp = client.get("/astral/event/full_moon", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["type"] == "review"
    assert resp.json()["title"] == "复盘之夜"

    resp = client.get("/astral/event/mercury_retrograde", headers=headers)
    body = resp.json()
    assert body["type"] == "mercury_guide"
    assert len(body["items"]) == 7
    assert body["daily_sentence"]

    resp = client.get("/astral/event/solar_eclipse", headers=headers)
    body = resp.json()
    assert body["type"] == "info"
    assert len(body["notes"]) == 4


def test_api_mercury_guide_range_empty_state(client: TestClient):
    """API：2027 无逆行期 → range 键仍存在（旧版被 exclude_none 剔除），为空对象。"""
    _, headers = _new_user("openid_range_empty")
    with mock.patch.object(astral_api, "date", _FixedToday):
        _FixedToday.fixed = date(2027, 1, 1)
        resp = client.get("/astral/event/mercury_retrograde", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "mercury_guide"
    assert body["range"] == {"start": "", "end": "", "days_left": 0}


def test_api_invalid_inputs(client: TestClient):
    """非法输入：month 越界 422、未知事件类型 400、非法日期 422。"""
    _, headers = _new_user("openid_invalid")
    assert client.get("/astral/calendar", params={"year": 2026, "month": 13}, headers=headers).status_code == 422
    assert client.get("/astral/event/unknown_type", headers=headers).status_code == 400
    assert client.get("/astral/events/not-a-date", headers=headers).status_code == 422


# ── 节点活动打卡（T3-3）：事件当天 +1 星尘，幂等 ─────────────────────────


def _set_stardust(user_id: str, total: int) -> None:
    """预置用户星尘（星阶按 tier_for 同步），供阈值断言。"""

    async def _go() -> None:
        async with async_session() as session:
            user = await session.get(User, user_id)
            user.stardust_total = total
            user.star_tier = tier_for(total)
            await session.commit()

    asyncio.run(_go())


def _get_stardust_tier(user_id: str) -> tuple[int, int | None]:
    """独立会话读用户星尘/星阶（避开 API 会话 identity map）。"""

    async def _go() -> tuple[int, int | None]:
        async with async_session() as session:
            user = await session.get(User, user_id)
            return user.stardust_total or 0, user.star_tier

    return asyncio.run(_go())


def _activity_logs(user_id: str) -> list[dict]:
    """读用户打卡日志（event_key + event_date）。"""

    async def _go() -> list[dict]:
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(AstralActivityLog)
                    .where(AstralActivityLog.user_id == user_id)
                    .order_by(AstralActivityLog.event_key)
                )
            ).scalars().all()
            return [
                {"event_key": r.event_key, "event_date": r.event_date.isoformat()}
                for r in rows
            ]

    return asyncio.run(_go())


def test_api_activity_requires_auth(client: TestClient):
    """打卡与 summary 未登录一律 401。"""
    assert client.post("/astral/activity", json={"event_key": "wish"}).status_code == 401
    assert client.get("/astral/activity/summary", params={"month": "2026-08"}).status_code == 401


def test_api_activity_first_checkin_rewards_and_syncs_tier(client: TestClient):
    """首次打卡：stardust+1、star_tier 随 tier_for 同步、落库 event_key=类型-日期。"""
    uid, headers = _new_user("openid_activity_first")
    _set_stardust(uid, 6)  # 7 是星光门槛：+1 后星阶应从 0 升 1
    with mock.patch.object(astral_api, "date", _FixedToday):
        _FixedToday.fixed = date(2026, 8, 12)  # 狮子座新月
        resp = client.post("/astral/activity", json={"event_key": "wish"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "rewarded": True, "stardust_total": 7}
    total, tier = _get_stardust_tier(uid)
    assert total == 7
    assert tier == tier_for(7) == 1
    logs = _activity_logs(uid)
    assert logs == [{"event_key": "new_moon-2026-08-12", "event_date": "2026-08-12"}]


def test_api_activity_duplicate_same_day_idempotent(client: TestClient):
    """同日同 event_key 重复打卡：rewarded=false，星尘不重复加、日志不重复。"""
    uid, headers = _new_user("openid_activity_dup")
    with mock.patch.object(astral_api, "date", _FixedToday):
        _FixedToday.fixed = date(2026, 8, 12)
        first = client.post("/astral/activity", json={"event_key": "wish"}, headers=headers)
        second = client.post("/astral/activity", json={"event_key": "wish"}, headers=headers)
    assert first.json()["rewarded"] is True
    assert second.json() == {"ok": True, "rewarded": False, "stardust_total": 1}
    assert len(_activity_logs(uid)) == 1


def test_api_activity_concurrent_conflict_fallback_refresh(client: TestClient):
    """并发同 key 打卡（唯一约束兜底路径）：不 500，返回并发赢家已提交的星尘总值。

    时序（flush 时刻注入赢家提交，等价于并发窗口撞 UNIQUE 约束）：
    1. 端点 SELECT 时赢家尚未提交（无日志）→ 不短路
    2. db.add 日志 + user.stardust_total 内存 5→6
    3. flush 瞬间赢家（独立会话）提交同 key 日志 + 星尘=6 → 端点 flush 抛
       IntegrityError
    4. rollback 无条件过期会话内**所有** ORM 对象（expire_on_commit=False 只
       影响 commit 不影响 rollback）→ 修复前 except 分支读 user.stardust_total
       触发 async 惰性加载抛 MissingGreenlet → 500（红验证：修复前本测试
       FAILED status=500）
    5. 修复后 except 内 await db.refresh(user) 回读 → 赢家已提交值 6
    """
    uid, headers = _new_user("openid_activity_conflict")
    _set_stardust(uid, 5)
    _flush_orig = AsyncSession.flush

    async def _winner_commits_same_key() -> None:
        """模拟并发赢家恰在冲突窗口提交：同 key 日志 + 星尘 5→6（独立会话）。"""
        async with async_session() as session:
            session.add(
                AstralActivityLog(
                    user_id=uid,
                    event_key="new_moon-2026-08-12",
                    event_date=date(2026, 8, 12),
                )
            )
            user = await session.get(User, uid)
            user.stardust_total = 6
            user.star_tier = tier_for(6)
            await session.commit()

    async def _conflicting_flush(self) -> None:
        # 赢家先提交（临时还原原版 flush——类级补丁需放行独立会话的正常 commit）
        with mock.patch.object(AsyncSession, "flush", _flush_orig):
            await _winner_commits_same_key()
        raise IntegrityError(
            "INSERT INTO astral_activity_logs (user_id, event_key, event_date) VALUES (?, ?, ?)",
            (uid, "new_moon-2026-08-12", date(2026, 8, 12)),
            Exception(
                "UNIQUE constraint failed: astral_activity_logs.user_id, "
                "astral_activity_logs.event_key, astral_activity_logs.event_date"
            ),
        )

    with mock.patch.object(astral_api, "date", _FixedToday):
        _FixedToday.fixed = date(2026, 8, 12)  # 狮子座新月
        with mock.patch.object(AsyncSession, "flush", _conflicting_flush):
            resp = client.post(
                "/astral/activity", json={"event_key": "wish"}, headers=headers
            )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "rewarded": False, "stardust_total": 6}
    # 赢家已提交值落库：星尘 6、无重复 +1；日志仅赢家一条（端点 add 被回滚丢弃）
    assert _get_stardust_tier(uid) == (6, tier_for(6))
    assert _activity_logs(uid) == [
        {"event_key": "new_moon-2026-08-12", "event_date": "2026-08-12"}
    ]


def test_api_activity_same_day_different_keys_each_rewarded(client: TestClient):
    """同日不同 event_key（09-27 满月 + 水逆区间日：review+mercury_guide）：各 +1。"""
    uid, headers = _new_user("openid_activity_multi")
    with mock.patch.object(astral_api, "date", _FixedToday):
        _FixedToday.fixed = date(2026, 9, 27)  # 满月 + 水逆区间日
        r1 = client.post("/astral/activity", json={"event_key": "review"}, headers=headers)
        r2 = client.post("/astral/activity", json={"event_key": "mercury_guide"}, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["rewarded"] is True and r2.json()["rewarded"] is True
    assert r2.json()["stardust_total"] == 2
    keys = sorted(l["event_key"] for l in _activity_logs(uid))
    assert keys == ["full_moon-2026-09-27", "mercury_retrograde-2026-09-27"]


def test_api_activity_invalid_key(client: TestClient):
    """非法 event_key → 400。"""
    _, headers = _new_user("openid_activity_invalid")
    with mock.patch.object(astral_api, "date", _FixedToday):
        _FixedToday.fixed = date(2026, 8, 12)
        resp = client.post("/astral/activity", json={"event_key": "solar_eclipse"}, headers=headers)
    assert resp.status_code == 400


def test_api_activity_only_on_node_day(client: TestClient):
    """仅事件当天可打卡：无事件日 / 新月前一天 / 满月日打 wish 均 400。"""
    _, headers = _new_user("openid_activity_node_day")
    with mock.patch.object(astral_api, "date", _FixedToday):
        _FixedToday.fixed = date(2026, 2, 10)  # 无事件日
        assert client.post("/astral/activity", json={"event_key": "wish"}, headers=headers).status_code == 400
        _FixedToday.fixed = date(2026, 8, 11)  # 新月前一天
        assert client.post("/astral/activity", json={"event_key": "wish"}, headers=headers).status_code == 400
        _FixedToday.fixed = date(2026, 9, 27)  # 满月日但当天没有新月
        assert client.post("/astral/activity", json={"event_key": "wish"}, headers=headers).status_code == 400


def test_api_activity_summary_counts(client: TestClient):
    """summary 按月计数：completed=打卡数、keys=去重活动形态、用户双向隔离、非法 month 422。"""
    uid, headers = _new_user("openid_activity_summary")
    other_uid, other_headers = _new_user("openid_activity_summary_other")
    with mock.patch.object(astral_api, "date", _FixedToday):
        _FixedToday.fixed = date(2026, 8, 12)
        client.post("/astral/activity", json={"event_key": "wish"}, headers=headers)
        client.post("/astral/activity", json={"event_key": "wish"}, headers=other_headers)
        _FixedToday.fixed = date(2026, 9, 27)
        client.post("/astral/activity", json={"event_key": "review"}, headers=headers)
        client.post("/astral/activity", json={"event_key": "mercury_guide"}, headers=headers)

    resp = client.get("/astral/activity/summary", params={"month": "2026-08"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"month": "2026-08", "completed": 1, "keys": ["wish"]}

    resp = client.get("/astral/activity/summary", params={"month": "2026-09"}, headers=headers)
    assert resp.json() == {"month": "2026-09", "completed": 2, "keys": ["mercury_guide", "review"]}

    # 双向隔离：他人月视图只看自己的（09 月空态）
    resp_other = client.get("/astral/activity/summary", params={"month": "2026-08"}, headers=other_headers)
    assert resp_other.json() == {"month": "2026-08", "completed": 1, "keys": ["wish"]}
    resp_other = client.get("/astral/activity/summary", params={"month": "2026-09"}, headers=other_headers)
    assert resp_other.json() == {"month": "2026-09", "completed": 0, "keys": []}

    # 非法 month：格式错误 / 越界月份 → 422
    assert client.get("/astral/activity/summary", params={"month": "bad"}, headers=headers).status_code == 422
    assert client.get("/astral/activity/summary", params={"month": "2026-13"}, headers=headers).status_code == 422
