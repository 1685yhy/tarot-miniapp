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

import app.api.astral as astral_api
from app.db.database import async_session
from app.models.user import User
from app.models.wish import Wish
from app.services.astral_calendar import (
    MERCURY_CARE_ITEMS,
    MERCURY_DAILY_SENTENCES,
    day_detail,
    month_view,
    node_content,
)
from app.services.moon import next_new_moon_after
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
    """review 节点：复盘之夜 + wish_counts 透传 + target_page。"""
    node = node_content(
        "review",
        date(2026, 8, 12),
        wish_counts={"active": 2, "grown": 1, "answered": 0},
    )
    assert node == {
        "type": "review",
        "title": "复盘之夜",
        "wish_counts": {"active": 2, "grown": 1, "answered": 0},
        "target_page": "pages/review/review",
    }


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
    assert len(node["items"]) >= 7
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
    """7 件小事 ≥7 条、句子池 ≥12 条，且全部无黑名单词。"""
    assert len(MERCURY_CARE_ITEMS) >= 7
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
    assert len(body["items"]) >= 7
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
