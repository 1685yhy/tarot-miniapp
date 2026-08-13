"""
星灵学堂测试（SDD P2 阶段3 · T6-1）：学习进度 + 已学/复习 + 里程碑奖励幂等。

- POST /academy/learned — 首学 first_star +1 且 star_tier 同步；重复已学幂等
  （learned=false 不重复奖励）；里程碑边界 7 / 22(major) / 56(minor) / 78 各档发放；
  全通封顶星尘总增量；壁纸发放
- POST /academy/review — 复习计数递增且无星尘奖励（防刷）
- GET  /academy/lesson/{card_id} — 公开免登录可看牌库 + 登录附带 my 进度
- 里程碑文案过 compliance 禁词扫描；未登录 401；card_id 非法 404
"""

import asyncio
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import async_session
from app.models.card import TarotCard
from app.models.card_teaching import CardTeaching
from app.models.reading import DrawnCard, Reading
from app.models.star_learning_progress import StarLearningProgress
from app.models.subscribe_quota import SubscribeQuota
from app.models.user import User
from app.services.academy import (
    MILESTONES,
    PATH_NAMES,
    PATH_REASONS,
    SUIT_ORDER,
    check_milestones,
    major_cards,
    minor_cards,
    next_card,
    pick_related,
)
from app.services.ai_personas import get_persona, get_persona_prompt_suffix
from app.services.compliance import AI_OUTPUT_BLACKLIST, MEET_BLACKLIST, find_forbidden
from app.services.stardust import tier_for
from app.utils.auth import create_token

# ---------------------------------------------------------------------------
# 教学库种子（lesson 公开接口需要；模仿 test_teaching.py 的导入期播种）。
# 注意避开 test_teaching.py 已占用的卡：1/7/14 为已种教学卡，2 是它的
# 「无教学数据 404」哨兵卡（导入期先到先得，冲突会破坏对方断言），
# 故只用 3/6；story 保持 >20 字与对方口径一致。
# ---------------------------------------------------------------------------

_LESSON_TEACHING_SEEDS = [
    {
        "card_id": 3,
        "symbols": json.dumps([{"symbol": "白色玫瑰", "meaning": "纯洁与超越世俗的爱"}]),
        "story": "女皇是塔罗大阿尔卡纳的第三张牌，象征丰饶与滋养的生机。",
        "keywords_learning": json.dumps(["开端", "信任", "冒险"]),
        "life_connection": "真正的勇气是带着恐惧依然迈出那一步。",
        "element_association": "风元素——思想与精神的自由流动。",
    },
    {
        "card_id": 6,
        "symbols": json.dumps([{"symbol": "黑白斯芬克斯", "meaning": "对立力量的拉扯"}]),
        "story": "恋人对应爱神与选择的课题，象征联结与价值的抉择。",
        "keywords_learning": json.dumps(["意志力", "胜利", "驾驭"]),
        "life_connection": "力量来自对立面的整合。",
        "element_association": "水元素——情感力量与内在驱动力。",
    },
]


async def _seed_teaching():
    async with async_session() as session:
        for seed in _LESSON_TEACHING_SEEDS:
            existing = await session.execute(
                select(CardTeaching).where(CardTeaching.card_id == seed["card_id"])
            )
            if existing.scalar_one_or_none():
                continue
            session.add(CardTeaching(**seed))
        await session.commit()


_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)
try:
    _loop.run_until_complete(_seed_teaching())
finally:
    _loop.close()


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _make_user() -> tuple[str, str, dict]:
    """创建独立测试用户，返回 (openid, user_id, 认证请求头)。"""
    openid = f"academy-api-{uuid.uuid4().hex[:12]}"

    async def _run():
        async with async_session() as session:
            user = User(openid=openid)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    user = asyncio.run(_run())
    return openid, user.id, {"Authorization": f"Bearer {create_token(user.id, user.token_version)}"}


def _read_user(openid: str) -> User:
    async def _run():
        async with async_session() as session:
            result = await session.execute(select(User).where(User.openid == openid))
            return result.scalar_one()

    return asyncio.run(_run())


def _learn(client: TestClient, headers: dict, card_id: int) -> dict:
    """POST /academy/learned 快捷方式。"""
    resp = client.post("/academy/learned", json={"card_id": card_id}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 纯函数：check_milestones / 封顶核算
# ---------------------------------------------------------------------------


class TestCheckMilestones:
    def test_returns_only_qualified_unclaimed(self):
        """只返回满足门槛且账本中未领的里程碑（按表序）。"""
        pending = check_milestones(learned=7, major=7, minor=0, awarded=[])
        assert [m["key"] for m in pending] == ["first_star", "seven_stars"]
        pending = check_milestones(learned=7, major=7, minor=0, awarded=["first_star"])
        assert [m["key"] for m in pending] == ["seven_stars"]
        pending = check_milestones(learned=78, major=22, minor=56, awarded=["first_star", "seven_stars"])
        assert [m["key"] for m in pending] == ["fool_journey", "element_court", "full_78"]
        # 已领全部 → 空
        assert check_milestones(
            78, 22, 56, awarded=[m["key"] for m in MILESTONES]
        ) == []

    def test_milestone_thresholds_and_cap(self):
        """5 档里程碑边界（1/7/22/56/78）与封顶星尘。

        注：任务简报写「全通封顶 +19」，但各档 verbatim 数值之和为 20
        （1+1+3+5+10）；按逐档数值实现，详见任务报告附注。
        """
        thresholds = [(m["metric"], m["min"]) for m in MILESTONES]
        assert ("learned", 1) in thresholds
        assert ("learned", 7) in thresholds
        assert ("major", 22) in thresholds
        assert ("minor", 56) in thresholds
        assert ("learned", 78) in thresholds
        assert sum(m["stardust"] for m in MILESTONES) == 20


# ---------------------------------------------------------------------------
# POST /academy/learned — 里程碑发放
# ---------------------------------------------------------------------------


class TestLearnMilestones:
    def test_first_learn_grants_first_star_and_syncs_tier(self, client: TestClient):
        """首学 → first_star +1 且 star_tier 随 stardust_total 同步推导。"""
        openid, _, headers = _make_user()
        data = _learn(client, headers, 1)
        assert data["learned"] is True
        assert data["ok"] is True
        assert data["review_count"] == 0
        assert data["milestone"]["key"] == "first_star"
        assert data["milestone"]["stardust_gained"] == 1
        assert data["milestone"]["wallpaper_granted"] is False
        user = _read_user(openid)
        assert user.stardust_total == 1
        assert user.star_tier == 0  # 1 星尘 < 7 → 微光；与 tier_for 一致
        assert user.star_tier == tier_for(user.stardust_total)

    def test_duplicate_learn_idempotent_no_reward(self, client: TestClient):
        """已学再学同卡 → learned=false 且里程碑不重发、星尘不增加。"""
        openid, _, headers = _make_user()
        _learn(client, headers, 1)
        data = _learn(client, headers, 1)
        assert data["learned"] is False
        assert data["milestone"] is None
        assert _read_user(openid).stardust_total == 1  # 无重复奖励

    def test_seventh_card_grants_seven_stars(self, client: TestClient):
        """第 7 张 → seven_stars +1。"""
        openid, _, headers = _make_user()
        for card_id in range(1, 7):
            _learn(client, headers, card_id)
        data = _learn(client, headers, 7)
        assert data["milestone"]["key"] == "seven_stars"
        assert data["milestone"]["stardust_gained"] == 1
        assert _read_user(openid).stardust_total == 2  # first_star 1 + seven_stars 1

    def test_fool_journey_22_major(self, client: TestClient):
        """22 张 major 全学 → fool_journey +3 + 称号入账（academy_milestones 含 key）。"""
        openid, _, headers = _make_user()
        for card_id in range(1, 22):
            _learn(client, headers, card_id)
        data = _learn(client, headers, 22)
        assert data["milestone"]["key"] == "fool_journey"
        assert data["milestone"]["stardust_gained"] == 3
        user = _read_user(openid)
        assert "fool_journey" in json.loads(user.academy_milestones or "[]")
        assert user.stardust_total == 5  # 1 + 1 + 3

    def test_element_court_56_minor(self, client: TestClient):
        """56 张 minor 全学 → element_court +5。"""
        openid, _, headers = _make_user()
        for card_id in range(23, 78):  # 23..77 = 55 张 minor
            _learn(client, headers, card_id)
        data = _learn(client, headers, 78)  # 第 56 张 minor
        assert data["milestone"]["key"] == "element_court"
        assert data["milestone"]["stardust_gained"] == 5
        assert _read_user(openid).stardust_total == 7  # 1 + 1 + 5

    def test_full_78_grants_wallpaper(self, client: TestClient):
        """78 张全学 → full_78 +10 + 壁纸（mock grant_wallpaper 恰好调用 1 次）。"""
        _, _, headers = _make_user()
        with patch("app.services.academy.grant_wallpaper", return_value="2026-08-13") as mock_wp:
            for card_id in range(1, 79):
                data = _learn(client, headers, card_id)
        assert mock_wp.call_count == 1, f"壁纸应只发放 1 次，实际 {mock_wp.call_count}"
        assert data["milestone"]["key"] == "full_78"
        assert data["milestone"]["stardust_gained"] == 10
        assert data["milestone"]["wallpaper_granted"] is True

    def test_cap_total_stardust_full_completion(self, client: TestClient):
        """封顶：0→78 张全学 stardust 总增量 == 20（5 档之和 1+1+3+5+10）。"""
        openid, _, headers = _make_user()
        for card_id in range(1, 79):
            _learn(client, headers, card_id)
        user = _read_user(openid)
        expected = sum(m["stardust"] for m in MILESTONES)
        assert user.stardust_total == expected
        assert user.star_tier == tier_for(user.stardust_total)  # 20 星尘 → 星光(1)
        # full_78 真实发放壁纸 1 张（达成日期）
        assert len(json.loads(user.wallpapers or "[]")) == 1


# ---------------------------------------------------------------------------
# POST /academy/review — 复习计数
# ---------------------------------------------------------------------------


class TestReview:
    def test_review_increments_no_stardust(self, client: TestClient):
        """复习计数递增且无星尘奖励（防刷）。"""
        openid, _, headers = _make_user()
        _learn(client, headers, 1)
        resp = client.post("/academy/review", json={"card_id": 1}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"ok": True, "review_count": 1}
        resp2 = client.post("/academy/review", json={"card_id": 1}, headers=headers)
        assert resp2.json()["review_count"] == 2
        assert _read_user(openid).stardust_total == 1  # 复习不设奖励

    def test_review_before_learn_404(self, client: TestClient):
        """未学习的卡复习 → 404（先复习后学习会绕过里程碑，直接拒绝）。"""
        _, _, headers = _make_user()
        resp = client.post("/academy/review", json={"card_id": 1}, headers=headers)
        assert resp.status_code == 404

    def test_review_invalid_card_404(self, client: TestClient):
        """复习不存在的卡 → 404。"""
        _, _, headers = _make_user()
        resp = client.post("/academy/review", json={"card_id": 999}, headers=headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /academy/lesson/{card_id} — 学习卡页（公开）
# ---------------------------------------------------------------------------


class TestLesson:
    def test_lesson_public_anonymous(self, client: TestClient):
        """lesson 未登录可看（牌库公开）+ my=null。"""
        resp = client.get("/academy/lesson/3")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        card = data["card"]
        assert card["id"] == 3
        assert card["name_zh"] == "卡牌3"
        assert card["arcana"] == "major"
        assert card["card_number"] == 2
        assert card["image_url"].endswith(".webp")
        teaching = data["teaching"]
        assert teaching["symbols"][0]["symbol"] == "白色玫瑰"
        assert teaching["story"]
        assert teaching["keywords_learning"] == ["开端", "信任", "冒险"]
        assert teaching["life_connection"]
        assert teaching["element_association"]
        assert data["my"] is None

    def test_lesson_my_progress_when_logged_in(self, client: TestClient):
        """登录后 lesson 附带 my 进度（learned/review_count）。"""
        _, _, headers = _make_user()
        _learn(client, headers, 3)
        resp = client.get("/academy/lesson/3", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["my"] == {"learned": True, "review_count": 0}

    def test_lesson_invalid_card_404(self, client: TestClient):
        """不存在的卡 lesson → 404。"""
        resp = client.get("/academy/lesson/999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 鉴权 / 非法 card_id
# ---------------------------------------------------------------------------


class TestAuthAndValidation:
    def test_learned_requires_auth(self, client: TestClient):
        """未登录 POST /academy/learned → 401。"""
        resp = client.post("/academy/learned", json={"card_id": 1})
        assert resp.status_code == 401

    def test_review_requires_auth(self, client: TestClient):
        """未登录 POST /academy/review → 401。"""
        resp = client.post("/academy/review", json={"card_id": 1})
        assert resp.status_code == 401

    def test_learned_invalid_card_404(self, client: TestClient):
        """学习不存在的卡 → 404。"""
        _, _, headers = _make_user()
        resp = client.post("/academy/learned", json={"card_id": 999}, headers=headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 里程碑文案合规（compliance 共享禁词表）
# ---------------------------------------------------------------------------


class TestMilestoneCompliance:
    def test_milestone_copy_passes_compliance_scan(self):
        """里程碑标题/称号过 compliance 禁词扫描（必/绝对/命/预测…）。"""
        for m in MILESTONES:
            assert find_forbidden(m["title"], MEET_BLACKLIST) == [], f"标题含禁词: {m}"
            assert find_forbidden(m["title"], AI_OUTPUT_BLACKLIST) == [], f"标题含红线词: {m}"
            if m.get("title_name"):
                assert find_forbidden(m["title_name"], MEET_BLACKLIST) == [], f"称号含禁词: {m}"
                assert find_forbidden(m["title_name"], AI_OUTPUT_BLACKLIST) == [], f"称号含红线词: {m}"


# ---------------------------------------------------------------------------
# T6-2（Task 13）: 学习计划 + 下一张 + 学堂概览
#   - star_learning_plans（1 用户 1 条）+ /academy/plan 读写闭环
#   - /academy/lesson/next 路径游标（major/minor 顺序、random 按日确定性、
#     related 历史抽牌频次 TOP 未学）+ 游标写回
#   - /academy/overview 总进度 + 四路径 + 称号 + today_card
# 纯函数：major_cards/minor_cards 排序、next_card 越界回 0、pick_related 破平
# ---------------------------------------------------------------------------


def _load_deck() -> list[TarotCard]:
    """按 id 加载完整牌库（与 /cards/daily 口径一致）。"""

    async def _run():
        async with async_session() as session:
            result = await session.execute(select(TarotCard).order_by(TarotCard.id))
            return list(result.scalars().all())

    return asyncio.run(_run())


def _insert_reading(user_id: str, card_ids: list[int]) -> None:
    """直接插入一次 Reading + DrawnCard（related 路径的历史抽牌频次来源）。"""

    async def _run():
        async with async_session() as session:
            reading = Reading(user_id=user_id, spread_type="three_card", question="测试问题")
            session.add(reading)
            await session.flush()
            for i, cid in enumerate(card_ids):
                session.add(
                    DrawnCard(
                        reading_id=reading.id,
                        card_id=cid,
                        position=i,
                        position_name=f"位置{i + 1}",
                        is_reversed=False,
                    )
                )
            await session.commit()

    asyncio.run(_run())


def _grant_quota(user_id: str, quota_available: int = 1, last_sent_date: date | None = None) -> None:
    """直接插入 SubscribeQuota 行（已授权锚：quota_available>0 或 last_sent_date 有值）。"""

    async def _run():
        async with async_session() as session:
            session.add(
                SubscribeQuota(
                    user_id=user_id,
                    quota_available=quota_available,
                    last_sent_date=last_sent_date,
                )
            )
            await session.commit()

    asyncio.run(_run())


def _learn_all_direct(user_id: str) -> None:
    """直接插入 78 张已学行（related 路径「无可学牌」完成态，绕过 API 提速）。"""

    async def _run():
        async with async_session() as session:
            for cid in range(1, 79):
                session.add(
                    StarLearningProgress(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        card_id=cid,
                        learned_at=date.today(),
                        review_count=0,
                    )
                )
            await session.commit()

    asyncio.run(_run())


def _set_plan(client: TestClient, headers: dict, payload: dict) -> dict:
    """POST /academy/plan 快捷方式。"""
    resp = client.post("/academy/plan", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 纯函数：major_cards / minor_cards / next_card / pick_related
# ---------------------------------------------------------------------------


class TestPathOrdering:
    def test_major_cards_sorted_by_card_number(self):
        """major_cards：22 张大阿卡纳按 card_number 0-21 升序。"""
        major = major_cards(_load_deck())
        assert len(major) == 22
        assert [c.card_number for c in major] == list(range(22))
        assert [c.id for c in major] == list(range(1, 23))

    def test_minor_cards_sorted_by_suit_then_rank(self):
        """minor_cards：suit 火(0)→水(1)→风(2)→土(3) + card_number 升序，每套 14 张。"""
        minor = minor_cards(_load_deck())
        assert len(minor) == 56
        suits = [c.suit for c in minor]
        assert suits == sorted(suits, key=lambda s: SUIT_ORDER[s])
        assert [c.card_number for c in minor] == sorted(c.card_number for c in minor)
        assert suits[:14] == ["wands"] * 14
        assert suits[14:28] == ["cups"] * 14
        assert suits[28:42] == ["swords"] * 14
        assert suits[42:] == ["pentacles"] * 14

    def test_next_card_major_overrun_wraps_done(self):
        """major 游标越界（≥22）→ 首张 + done=true + next_pos=0。"""
        deck = _load_deck()
        card, next_pos, done = next_card("major", 22, major_cards(deck), minor_cards(deck), "u", date(2026, 8, 13))
        assert (card.id, next_pos, done) == (1, 0, True)

    def test_next_card_random_deterministic_per_day(self):
        """random：同日同人恒定（两次同卡）；跨日换牌（与每日一牌同 seed）。"""
        deck = _load_deck()
        major, minor = major_cards(deck), minor_cards(deck)
        c1, p1, d1 = next_card("random", 0, major, minor, "pure-test-user", date(2026, 8, 13))
        c2, _, _ = next_card("random", 0, major, minor, "pure-test-user", date(2026, 8, 13))
        assert c1.id == c2.id
        assert p1 == 0 and d1 is False  # 随机路径忽略游标、永不到头
        c3, _, _ = next_card("random", 0, major, minor, "pure-test-user", date(2026, 8, 14))
        assert c3.id != c1.id

    def test_pick_related_tie_break_by_card_number(self):
        """pick_related：频次降序；同频 → card_number 升序取首张（确定性破平）。"""
        deck = _load_deck()
        candidates = [c for c in deck if c.id in (10, 12, 15)]
        top = pick_related(candidates, {15: 1, 10: 1, 12: 0})
        assert top.id == 10  # 10 与 15 同频，card_number 更小
        assert pick_related([], {}) is None


# ---------------------------------------------------------------------------
# GET/POST /academy/plan — 学习计划读写
# ---------------------------------------------------------------------------


class TestPlanAPI:
    def test_plan_default_when_no_row(self, client: TestClient):
        """未创建计划 → 默认 {0, false, "major", 0}（学习提醒默认关闭）。"""
        _, _, headers = _make_user()
        data = client.get("/academy/plan", headers=headers).json()
        assert data == {"cards_per_day": 0, "reminder_on": False, "path": "major", "cursor_pos": 0}

    def test_plan_write_read_roundtrip(self, client: TestClient):
        """计划写入后 GET 回显一致；reminder_on 缺省默认 false；覆盖更新生效。"""
        _, _, headers = _make_user()
        data = _set_plan(client, headers, {"cards_per_day": 3, "path": "minor"})
        assert data == {
            "cards_per_day": 3,
            "reminder_on": False,
            "path": "minor",
            "cursor_pos": 0,
            "quota_warning": False,
        }
        got = client.get("/academy/plan", headers=headers).json()
        assert got == {"cards_per_day": 3, "reminder_on": False, "path": "minor", "cursor_pos": 0}
        # 覆盖更新
        _set_plan(client, headers, {"cards_per_day": 5, "reminder_on": False, "path": "random"})
        got = client.get("/academy/plan", headers=headers).json()
        assert (got["cards_per_day"], got["path"]) == (5, "random")

    def test_plan_invalid_cards_per_day_422(self, client: TestClient):
        """cards_per_day 只允许 0|1|3|5 → 2/7 均 422。"""
        _, _, headers = _make_user()
        for bad in (2, 7):
            resp = client.post(
                "/academy/plan",
                json={"cards_per_day": bad, "reminder_on": False, "path": "major"},
                headers=headers,
            )
            assert resp.status_code == 422, resp.text

    def test_plan_invalid_path_422(self, client: TestClient):
        """path 只允许 major|minor|random|related → 非法 422。"""
        _, _, headers = _make_user()
        resp = client.post(
            "/academy/plan",
            json={"cards_per_day": 1, "reminder_on": False, "path": "diagonal"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_plan_reminder_without_quota_warns_but_saves(self, client: TestClient):
        """reminder_on=true 且无订阅额度 → 200 + quota_warning=true 且仍保存（引导授权不硬拦）。"""
        _, _, headers = _make_user()
        data = _set_plan(client, headers, {"cards_per_day": 1, "reminder_on": True, "path": "major"})
        assert data["quota_warning"] is True
        assert data["reminder_on"] is True
        got = client.get("/academy/plan", headers=headers).json()
        assert got["reminder_on"] is True  # 仍保存

    def test_plan_reminder_with_quota_no_warning(self, client: TestClient):
        """已有订阅额度（quota_available>0）→ quota_warning=false。"""
        _, user_id, headers = _make_user()
        _grant_quota(user_id, quota_available=1)
        data = _set_plan(client, headers, {"cards_per_day": 1, "reminder_on": True, "path": "major"})
        assert data["quota_warning"] is False

    def test_plan_reminder_authorized_by_last_sent_date(self, client: TestClient):
        """额度 0 但 last_sent_date 有值（已发过晨讯）→ 视为已授权不警告。"""
        _, user_id, headers = _make_user()
        _grant_quota(user_id, quota_available=0, last_sent_date=date(2026, 8, 12))
        data = _set_plan(client, headers, {"cards_per_day": 3, "reminder_on": True, "path": "related"})
        assert data["quota_warning"] is False

    def test_plan_requires_auth(self, client: TestClient):
        """未登录 GET/POST /academy/plan → 401。"""
        assert client.get("/academy/plan").status_code == 401
        resp = client.post("/academy/plan", json={"cards_per_day": 1, "path": "major"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /academy/lesson/next — 路径下一张（游标推进 + 写回）
# ---------------------------------------------------------------------------


class TestNextLesson:
    def test_next_major_advances_cursor(self, client: TestClient):
        """next major 游标推进 0→1→…，且写回 plans.cursor_pos。"""
        _, _, headers = _make_user()
        r1 = client.get("/academy/lesson/next?path=major&pos=0", headers=headers).json()
        assert r1 == {"card_id": 1, "name_zh": "卡牌1", "path": "major", "next_pos": 1, "done": False}
        r2 = client.get("/academy/lesson/next?path=major&pos=1", headers=headers).json()
        assert r2["card_id"] == 2 and r2["next_pos"] == 2 and r2["done"] is False
        plan = client.get("/academy/plan", headers=headers).json()
        assert (plan["path"], plan["cursor_pos"]) == ("major", 2)

    def test_next_major_out_of_range_done_wraps(self, client: TestClient):
        """游标越界 → done=true 且循环回 0（首张）。"""
        _, _, headers = _make_user()
        data = client.get("/academy/lesson/next?path=major&pos=99", headers=headers).json()
        assert data == {"card_id": 1, "name_zh": "卡牌1", "path": "major", "next_pos": 0, "done": True}

    def test_next_random_same_day_same_card(self, client: TestClient):
        """random 同日同人恒定：两次调用同一张牌，游标不动、done=false。"""
        _, _, headers = _make_user()
        r1 = client.get("/academy/lesson/next?path=random&pos=3", headers=headers).json()
        r2 = client.get("/academy/lesson/next?path=random&pos=3", headers=headers).json()
        assert r1["card_id"] == r2["card_id"]
        assert r1["name_zh"] == r2["name_zh"]
        assert r1["next_pos"] == 3 and r2["next_pos"] == 3
        assert r1["done"] is False

    def test_next_random_matches_daily_card(self, client: TestClient):
        """random 与每日一牌 pick_daily_card 同牌（同 seed 同卡，随机路径确定性）。"""
        _, user_id, headers = _make_user()
        data = client.get("/academy/lesson/next?path=random&pos=0", headers=headers).json()
        card, _, _ = next_card("random", 0, major_cards(_load_deck()), minor_cards(_load_deck()), user_id, date.today())
        assert data["card_id"] == card.id

    def test_next_related_top_unlearned_by_frequency(self, client: TestClient):
        """related：未学牌中按历史抽牌频次 TOP（已学的高频牌被排除）。"""
        _, user_id, headers = _make_user()
        _learn(client, headers, 5)  # 先学掉最高频的牌
        _insert_reading(user_id, card_ids=[5, 5, 5, 7, 7, 9])  # 5×3 / 7×2 / 9×1
        data = client.get("/academy/lesson/next?path=related&pos=0", headers=headers).json()
        assert data["card_id"] == 7  # 5 已学排除 → TOP 未学 = 7
        assert data["done"] is False
        assert data["next_pos"] == 0  # related 忽略游标

    def test_next_related_all_learned_done_wraps(self, client: TestClient):
        """related 全部已学 → done=true 循环回 0。"""
        _, user_id, headers = _make_user()
        _insert_reading(user_id, card_ids=[5, 5, 7])
        _learn_all_direct(user_id)
        data = client.get("/academy/lesson/next?path=related&pos=0", headers=headers).json()
        assert data["done"] is True
        assert data["next_pos"] == 0
        assert data["card_id"] == 1

    def test_next_preserves_saved_plan_path_when_path_omitted(self, client: TestClient):
        """lesson/next 只推进游标不覆写计划路径：缺省 path=major 的调用不得把
        random 计划改成 major（否则 GET /plan 与 overview.today_card 都漂移）。"""
        _, _, headers = _make_user()
        _set_plan(client, headers, {"cards_per_day": 1, "reminder_on": False, "path": "random"})
        data = client.get("/academy/lesson/next?pos=0", headers=headers).json()
        assert data["path"] == "major"  # 本次调用按默认 major 响应
        plan = client.get("/academy/plan", headers=headers).json()
        assert plan["path"] == "random"  # 已存路径不被覆写
        assert plan["cursor_pos"] == 1  # 游标照常写回
        overview = client.get("/academy/overview", headers=headers).json()
        assert overview["today_card"]["reason"] == "今日之牌·随机星选"

    def test_next_update_branch_keeps_stored_path(self, client: TestClient):
        """既有计划：显式传不同 path 调用 lesson/next → 仍保留已存路径，仅写回游标。"""
        _, _, headers = _make_user()
        _set_plan(client, headers, {"cards_per_day": 3, "reminder_on": False, "path": "minor"})
        client.get("/academy/lesson/next?path=major&pos=0", headers=headers)
        plan = client.get("/academy/plan", headers=headers).json()
        assert (plan["path"], plan["cursor_pos"]) == ("minor", 1)

    def test_next_invalid_path_422(self, client: TestClient):
        """next 非法路径 → 422。"""
        _, _, headers = _make_user()
        resp = client.get("/academy/lesson/next?path=diagonal&pos=0", headers=headers)
        assert resp.status_code == 422

    def test_next_requires_auth(self, client: TestClient):
        """未登录 GET /academy/lesson/next → 401。"""
        resp = client.get("/academy/lesson/next?path=major&pos=0")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /academy/overview — 学堂主页概览
# ---------------------------------------------------------------------------


class TestOverview:
    def test_overview_empty_state(self, client: TestClient):
        """未学任何牌且无计划 → 全 0 进度 + 无称号 + today_card=null。"""
        _, _, headers = _make_user()
        data = client.get("/academy/overview", headers=headers).json()
        assert data["total"] == 78
        assert data["learned"] == 0
        assert data["percent"] == 0
        assert data["paths"]["major"] == {"learned": 0, "total": 22}
        assert data["paths"]["minor"] == {"learned": 0, "total": 56}
        assert data["paths"]["random"] == {"learned": 0, "total": None}
        assert data["paths"]["related"] == {"learned": 0, "total": None}
        assert data["titles"] == []
        assert data["today_card"] is None

    def test_overview_progress_paths_and_titles(self, client: TestClient):
        """22 张大阿卡纳全学 → major 满进度、percent 同步、称号「星辉学者」。"""
        _, _, headers = _make_user()
        for card_id in range(1, 23):
            _learn(client, headers, card_id)
        data = client.get("/academy/overview", headers=headers).json()
        assert data["total"] == 78
        assert data["learned"] == 22
        assert data["percent"] == round(22 * 100 / 78)
        assert data["paths"]["major"] == {"learned": 22, "total": 22}
        assert data["paths"]["minor"] == {"learned": 0, "total": 56}
        assert data["paths"]["random"] == {"learned": 22, "total": None}
        assert data["paths"]["related"] == {"learned": 22, "total": None}
        assert data["titles"] == ["星辉学者"]

    def test_overview_full_completion_percent_and_titles(self, client: TestClient):
        """78 张全学 → percent=100、titles 含两称号、四路径满。"""
        _, _, headers = _make_user()
        for card_id in range(1, 79):
            _learn(client, headers, card_id)
        data = client.get("/academy/overview", headers=headers).json()
        assert data["learned"] == 78
        assert data["percent"] == 100
        assert data["paths"]["major"] == {"learned": 22, "total": 22}
        assert data["paths"]["minor"] == {"learned": 56, "total": 56}
        assert data["titles"] == ["星辉学者", "星光塔罗师"]

    def test_overview_today_card_follows_plan_path(self, client: TestClient):
        """计划路径 minor → today_card = 小阿卡纳第一张，reason 描述路径。"""
        _, _, headers = _make_user()
        _set_plan(client, headers, {"cards_per_day": 1, "reminder_on": False, "path": "minor"})
        data = client.get("/academy/overview", headers=headers).json()
        assert data["today_card"]["card_id"] == 23  # 小阿卡纳第一张（wands 首位）
        assert data["today_card"]["name_zh"] == "卡牌23"
        assert data["today_card"]["reason"] == "四元素庭院·按顺序学习"

    def test_overview_today_card_random_deterministic(self, client: TestClient):
        """random 路径 → today_card 同日同人恒定，且与 lesson/next 同牌。"""
        _, _, headers = _make_user()
        _set_plan(client, headers, {"cards_per_day": 1, "reminder_on": False, "path": "random"})
        d1 = client.get("/academy/overview", headers=headers).json()
        d2 = client.get("/academy/overview", headers=headers).json()
        assert d1["today_card"]["card_id"] == d2["today_card"]["card_id"]
        nxt = client.get("/academy/lesson/next?path=random&pos=0", headers=headers).json()
        assert nxt["card_id"] == d1["today_card"]["card_id"]
        assert d1["today_card"]["reason"] == "今日之牌·随机星选"

    def test_overview_today_card_null_without_plan(self, client: TestClient):
        """未创建计划 → today_card=null。"""
        _, _, headers = _make_user()
        data = client.get("/academy/overview", headers=headers).json()
        assert data["today_card"] is None

    def test_overview_requires_auth(self, client: TestClient):
        """未登录 GET /academy/overview → 401。"""
        assert client.get("/academy/overview").status_code == 401


# ---------------------------------------------------------------------------
# T6-2 新增文案合规
# ---------------------------------------------------------------------------


class TestAcademyCopyCompliance:
    def test_path_names_and_reasons_pass_compliance_scan(self):
        """路径名/今日卡 reason 文案过 compliance 禁词扫描。"""
        for name in PATH_NAMES.values():
            assert find_forbidden(name, MEET_BLACKLIST) == [], f"路径名含禁词: {name}"
            assert find_forbidden(name, AI_OUTPUT_BLACKLIST) == [], f"路径名含红线词: {name}"
        for reason in PATH_REASONS.values():
            assert find_forbidden(reason, MEET_BLACKLIST) == [], f"reason 含禁词: {reason}"
            assert find_forbidden(reason, AI_OUTPUT_BLACKLIST) == [], f"reason 含红线词: {reason}"


# ---------------------------------------------------------------------------
# T6-4（Task 15）: POST /academy/chat 陪学小星 AI
#   - 免费 3 次内成功 + remaining 递减（3→2→1）；第 4 次 → 402「明天再来」
#   - 独立计数：academy_chat_count_today 与 free_chats_today 互不挤占
#   - 会员不限（10 次全成功 remaining=None，且不计数）
#   - AI 失败 → degraded=true 降级文案（不空屏、不消耗配额）
#   - AI 输出含黑名单词 → _sanitize 清洗后 reply 合规（find_forbidden == []）
#   - 日复位（quota_reset_date=昨天 → 首次调用计数从 0 起）
#   - message 空 → 422；card_id 非法 → 404；未登录 401
#   - 同卡同人二次提问 → 短版（前 80 字）且 AI 调用次数不增（成本控制）
#   - 系统 prompt 含 academy_tutor persona + 输出红线 + teaching 上下文
# 教学卡用 3/6（本文件导入期种子），避开 test_teaching 的 1/2/7/14。
# ---------------------------------------------------------------------------


class _ChatFakeCompletions:
    """仿 test_star_words._FakeCompletions 的假 AI：记录调用并返回固定内容。"""

    def __init__(self, content: str | None = None, raise_error: bool = False):
        self._content = content
        self._raise_error = raise_error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raise_error:
            raise RuntimeError("DeepSeek 服务不可用")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


class _ChatFakeAI:
    def __init__(self, completions: _ChatFakeCompletions):
        self.chat = SimpleNamespace(completions=completions)


def _chat_fake_ai(content: str | None = None, raise_error: bool = False) -> _ChatFakeAI:
    return _ChatFakeAI(_ChatFakeCompletions(content, raise_error))


def _make_member_user() -> tuple[str, str, dict]:
    """创建会员测试用户（会员不限 academy chat 配额）。"""
    openid = f"academy-chat-mem-{uuid.uuid4().hex[:12]}"

    async def _run():
        async with async_session() as session:
            user = User(openid=openid, is_member=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    user = asyncio.run(_run())
    return openid, user.id, {"Authorization": f"Bearer {create_token(user.id, user.token_version)}"}


def _set_academy_chat_state(openid: str, count: int, reset_date: date | None) -> None:
    """直接写 academy_chat_count_today + quota_reset_date（日复位测试用）。"""

    async def _run():
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.openid == openid))
            ).scalar_one()
            user.academy_chat_count_today = count
            user.quota_reset_date = reset_date
            await session.commit()

    asyncio.run(_run())


def _chat(client: TestClient, headers: dict, card_id: int = 3, message: str = "这张牌是什么意思"):
    return client.post(
        "/academy/chat", json={"card_id": card_id, "message": message}, headers=headers
    )


class TestAcademyChat:
    def test_free_quota_decrements_3_2_1_then_402(self, client, monkeypatch):
        """免费 3 次内成功 + remaining 递减（3→2→1）；第 4 次 → 402；
        独立计数不与占卜追问（free_chats_today）互挤。"""
        openid, _, headers = _make_user()
        fake = _chat_fake_ai("愚者的冒险精神，是说给生活里每个勇敢瞬间听的 ✦")
        monkeypatch.setattr("app.services.academy._get_ai_client", lambda: fake)
        # 配额语义隔离测试：禁用当日短版缓存（同卡重复提问会命中缓存不计数，
        # 缓存行为由 test_same_card_second_ask_short_version_ai_not_called_again 覆盖）
        monkeypatch.setattr("app.services.academy._chat_short_cache_get", lambda *a, **k: None)

        r1 = _chat(client, headers)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["degraded"] is False
        assert d1["remaining"] == 3
        assert "愚者的冒险精神" in d1["reply"]

        assert _chat(client, headers, message="再讲一次").json()["remaining"] == 2
        assert _chat(client, headers, message="第三次").json()["remaining"] == 1

        r4 = _chat(client, headers, message="第四次")
        assert r4.status_code == 402
        assert "明天再来" in r4.json()["detail"]

        user = _read_user(openid)
        assert user.academy_chat_count_today == 3
        assert user.free_chats_today == 0  # 独立计数，不挤占占卜追问额度

    def test_member_unlimited_remaining_none(self, client, monkeypatch):
        """会员 10 次全成功 remaining=None，且不计数。"""
        openid, _, headers = _make_member_user()
        fake = _chat_fake_ai("这张牌的典故很有意思 ✦")
        monkeypatch.setattr("app.services.academy._get_ai_client", lambda: fake)
        for i in range(10):
            resp = _chat(client, headers, message=f"第 {i} 问")
            assert resp.status_code == 200, resp.text
            assert resp.json()["remaining"] is None
        assert _read_user(openid).academy_chat_count_today == 0  # 会员不计数

    def test_ai_failure_degraded_reply_no_quota_consumed(self, client, monkeypatch):
        """AI 失败 → degraded=true 降级文案（不空屏），且不消耗免费次数。"""
        _, _, headers = _make_user()
        fake = _chat_fake_ai(raise_error=True)
        monkeypatch.setattr("app.services.academy._get_ai_client", lambda: fake)
        resp = _chat(client, headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["degraded"] is True
        assert data["reply"] == "小星在休息，先看看学习卡吧 ✦"
        assert data["remaining"] == 3  # 降级不计数 → 剩余仍为 3

    def test_no_api_key_degraded(self, client):
        """无 DEEPSEEK_API_KEY（测试环境为空）→ 降级文案，不 500。"""
        _, _, headers = _make_user()
        resp = _chat(client, headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["degraded"] is True
        assert data["reply"] == "小星在休息，先看看学习卡吧 ✦"

    def test_ai_output_sanitized_blacklist_words(self, client, monkeypatch):
        """AI 输出含黑名单词 → _sanitize 清洗后 reply 不含禁词（find_forbidden == []）。"""
        _, _, headers = _make_user()
        fake = _chat_fake_ai("你命中注定会成功，明天一定会转运，不必焦虑")
        monkeypatch.setattr("app.services.academy._get_ai_client", lambda: fake)
        resp = _chat(client, headers)
        assert resp.status_code == 200, resp.text
        reply = resp.json()["reply"]
        assert find_forbidden(reply, AI_OUTPUT_BLACKLIST) == [], f"reply 仍含禁词: {reply}"
        assert "命中注定" not in reply and "转运" not in reply
        assert reply == "你自有答案会成功，明天会调整，无需焦虑"

    def test_daily_reset_starts_count_from_zero(self, client, monkeypatch):
        """quota_reset_date=昨天且计数=3 → 首次调用即复位（计数从 0 起，不再 402）。

        日界以 quota 复位管线口径为准（UTC：datetime.now(timezone.utc).date()），
        不能用本地 date.today()——本地凌晨（CST 00:00-08:00）UTC 还是前一天，
        会误判「已是今天」不复位（午夜回归钉住）。
        """
        utc_today = datetime.now(timezone.utc).date()
        openid, _, headers = _make_user()
        _set_academy_chat_state(openid, count=3, reset_date=utc_today - timedelta(days=1))
        fake = _chat_fake_ai("复位成功 ✦")
        monkeypatch.setattr("app.services.academy._get_ai_client", lambda: fake)
        resp = _chat(client, headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["remaining"] == 3
        user = _read_user(openid)
        assert user.academy_chat_count_today == 1
        assert user.quota_reset_date == utc_today

    def test_same_card_second_ask_short_version_ai_not_called_again(self, client, monkeypatch):
        """同卡同人二次提问 → 回前 80 字短版，AI 调用次数不增（成本控制）；
        换卡提问仍走完整 AI。"""
        _, _, headers = _make_user()
        full = "恋人牌讲的是爱与选择：牌面上的一对，代表着心中两种声音的对话。" \
               "真正的爱不是非此即彼，而是愿意与不同意见共处。愿你在每一次选择里，都听见自己的心。" \
               "它也在提醒你：慢一点，爱会更有温度。"
        assert len(full) > 80
        fake = _chat_fake_ai(full)
        monkeypatch.setattr("app.services.academy._get_ai_client", lambda: fake)

        r1 = client.post(
            "/academy/chat", json={"card_id": 6, "message": "讲讲恋人牌"}, headers=headers
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["reply"] == full
        assert r1.json()["remaining"] == 3

        r2 = client.post(
            "/academy/chat", json={"card_id": 6, "message": "再讲一遍"}, headers=headers
        )
        assert r2.status_code == 200, r2.text
        assert len(fake.chat.completions.calls) == 1  # AI 只调一次
        assert r2.json()["reply"] == full[:80]  # 短版 = 前 80 字
        assert r2.json()["degraded"] is False
        assert r2.json()["remaining"] == 2  # 短版命中不消耗配额

        r3 = _chat(client, headers, card_id=3, message="讲讲这张")
        assert r3.status_code == 200, r3.text
        assert len(fake.chat.completions.calls) == 2  # 换卡 → 完整 AI 再调一次
        assert r3.json()["reply"] == full

    def test_prompt_includes_persona_redline_and_teaching(self, client, monkeypatch):
        """system prompt 含 academy_tutor persona + 输出红线；user prompt 含 teaching 上下文。"""
        _, _, headers = _make_user()
        fake = _chat_fake_ai("回复 ✦")
        monkeypatch.setattr("app.services.academy._get_ai_client", lambda: fake)
        resp = _chat(client, headers, card_id=3, message="讲讲这张牌")
        assert resp.status_code == 200, resp.text
        system = fake.chat.completions.calls[0]["messages"][0]["content"]
        user_msg = fake.chat.completions.calls[0]["messages"][1]["content"]
        assert "陪学小星" in system  # academy_tutor persona 注入
        assert "输出红线" in system  # _OUTPUT_RED_LINE 注入
        assert "白色玫瑰" in user_msg  # teaching.symbols 上下文
        assert "丰饶与滋养" in user_msg  # teaching.story 上下文
        assert "开端" in user_msg  # keywords_learning 上下文
        assert "讲讲这张牌" in user_msg  # 用户提问透传

    def test_empty_message_422(self, client):
        """message 空/缺失 → 422。"""
        _, _, headers = _make_user()
        resp = client.post("/academy/chat", json={"card_id": 3, "message": ""}, headers=headers)
        assert resp.status_code == 422
        resp = client.post("/academy/chat", json={"card_id": 3}, headers=headers)
        assert resp.status_code == 422

    def test_invalid_card_404(self, client):
        """card_id 非法 → 404。"""
        _, _, headers = _make_user()
        resp = client.post(
            "/academy/chat", json={"card_id": 999, "message": "hi"}, headers=headers
        )
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        """未登录 POST /academy/chat → 401。"""
        resp = client.post("/academy/chat", json={"card_id": 3, "message": "hi"})
        assert resp.status_code == 401


class TestAcademyTutorPersonaCompliance:
    def test_academy_tutor_persona_copy_passes_compliance_scan(self):
        """academy_tutor persona 文案过 compliance 禁词扫描（prompt 注入面不引红线词）。"""
        suffix = get_persona_prompt_suffix("academy_tutor")
        assert suffix, "academy_tutor persona 缺失 prompt_suffix"
        assert find_forbidden(suffix, MEET_BLACKLIST) == [], f"persona 含禁词: {suffix}"
        assert find_forbidden(suffix, AI_OUTPUT_BLACKLIST) == [], f"persona 含红线词: {suffix}"
        persona = get_persona("academy_tutor")
        assert persona["signature"] == "小星陪你 ✦"
