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
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import async_session
from app.models.card_teaching import CardTeaching
from app.models.user import User
from app.services.academy import MILESTONES, check_milestones
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
