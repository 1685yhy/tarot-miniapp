"""
星卡收藏 / 星光壁纸里程碑测试（P0-3 星尘签到收集体系 · 设计缺口 1）。

- 7 日连续签到 → 稀有星卡（正位金卡）：78 张牌按 user_id 确定性选取，不消耗额度
- 30 日连续签到 → 星光壁纸：收藏品，不消耗额度
- 里程碑不重复发放（milestones_claimed 去重）
- GET /tasks/status 返回 star_cards（含牌名）/ wallpapers
- 签到成功话术统一「星光馈赠」叙事（设计缺口 3）
"""

import asyncio
import datetime
import uuid

from sqlalchemy import select

from app.db.database import async_session
from app.models.checkin import CheckIn
from app.models.user import User
from app.services.star_collectibles import (
    DEFAULT_CARD_POOL,
    grant_star_card,
    grant_wallpaper,
    pick_star_card_index,
    star_cards_of,
    wallpapers_of,
)
from app.utils.auth import create_token

NARRATIVE_REWARD = "星光馈赠：+1 免费解读"


def _make_api_user() -> tuple[str, dict]:
    """创建独立测试用户，返回 (openid, 认证请求头)。"""
    openid = f"starcards-api-{uuid.uuid4().hex[:12]}"

    async def _run():
        async with async_session() as session:
            user = User(openid=openid)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    user = asyncio.run(_run())
    return openid, {"Authorization": f"Bearer {create_token(user.id, user.token_version)}"}


def _consecutive_rows(end_date: datetime.date, streak: int, claimed_day: int | None = None, claimed: str = ""):
    """生成 streak 1..N 的连续签到行（streak_count 1..streak），结束于 end_date。"""
    rows = []
    for i in range(1, streak + 1):
        d = end_date - datetime.timedelta(days=streak - i)
        rows.append((d, i, claimed if i == claimed_day else ""))
    return rows


def _seed_checkins(openid: str, rows: list[tuple[datetime.date, int, str]]):
    """直插签到记录：[(checkin_date, streak_count, milestones_claimed), ...]。"""

    async def _run():
        async with async_session() as session:
            result = await session.execute(select(User).where(User.openid == openid))
            user = result.scalar_one()
            for d, streak, claimed in rows:
                session.add(CheckIn(
                    user_id=user.id,
                    checkin_date=d,
                    streak_count=streak,
                    milestones_claimed=claimed,
                ))
            await session.commit()

    asyncio.run(_run())


def _read_user(openid: str) -> User:
    async def _run():
        async with async_session() as session:
            result = await session.execute(select(User).where(User.openid == openid))
            return result.scalar_one()

    return asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数：确定性选牌
# ─────────────────────────────────────────────────────────────────────────────


class TestPickStarCard:
    def test_pick_is_deterministic(self):
        """同一用户永远得到同一张星卡（user_id 做 seed）。"""
        assert pick_star_card_index("user-a", DEFAULT_CARD_POOL) == pick_star_card_index("user-a", DEFAULT_CARD_POOL)
        assert 0 <= pick_star_card_index("user-a", DEFAULT_CARD_POOL) < DEFAULT_CARD_POOL

    def test_pick_not_constant_across_users(self):
        """不同用户选牌分布足够散（30 个用户不可能全相同）。"""
        seen = {pick_star_card_index(f"u{i}", DEFAULT_CARD_POOL) for i in range(30)}
        assert len(seen) > 1, f"30 个用户全部选中同一张牌: {seen}"

    def test_pick_spans_pool_well(self):
        """300 个用户覆盖 78 张牌中的大部分（确定性+分布校验）。"""
        seen = {pick_star_card_index(f"u{i}", DEFAULT_CARD_POOL) for i in range(300)}
        assert len(seen) > 40, f"分布过集中: 仅覆盖 {len(seen)} 张"

    def test_pick_respects_pool_size(self):
        """不同牌池大小下索引始终落在池内。"""
        for pool in (1, 7, 78, 200):
            assert 0 <= pick_star_card_index("u-x", pool) < pool


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数：star_cards / wallpapers 存储读写
# ─────────────────────────────────────────────────────────────────────────────


class TestStarCardStorage:
    def test_grant_star_card_roundtrip(self):
        """星卡记录 {card_id, date, tier, orientation} 可写入可读回，同卡不重复追加。"""
        user = User(openid="st-rt")
        assert star_cards_of(user) == []
        record = grant_star_card(user, 17, "2026-08-11")
        assert record["card_id"] == 17
        assert record["tier"] == "gold"
        assert record["orientation"] == "upright"
        assert star_cards_of(user) == [record]
        # 幂等：同 card_id 不重复追加
        grant_star_card(user, 17, "2026-08-11")
        assert len(star_cards_of(user)) == 1

    def test_grant_wallpaper_roundtrip(self):
        """壁纸按日期去重追加。"""
        user = User(openid="st-wp")
        assert wallpapers_of(user) == []
        grant_wallpaper(user, "2026-08-11")
        grant_wallpaper(user, "2026-08-11")
        grant_wallpaper(user, "2026-09-10")
        assert wallpapers_of(user) == ["2026-08-11", "2026-09-10"]

    def test_parse_malformed_json_is_safe(self):
        """脏数据（坏 JSON / null）解析为空列表，不抛异常。"""
        user = User(openid="st-mal", star_cards="{broken", wallpapers="null")
        assert star_cards_of(user) == []
        assert wallpapers_of(user) == []

    def test_persisted_star_cards_readable(self):
        """写库后重读不丢失（迁移列可持久化）。"""
        openid, _headers = _make_api_user()

        async def _grant():
            async with async_session() as session:
                user = (await session.execute(select(User).where(User.openid == openid))).scalar_one()
                grant_star_card(user, 42, "2026-08-11")
                grant_wallpaper(user, "2026-08-11")
                await session.commit()

        asyncio.run(_grant())
        user = _read_user(openid)
        assert star_cards_of(user) == [{"card_id": 42, "date": "2026-08-11", "tier": "gold", "orientation": "upright"}]
        assert wallpapers_of(user) == ["2026-08-11"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /tasks/checkin — 里程碑收藏品发放
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckinCollectibleMilestones:
    def test_day7_grants_star_card(self, client):
        """连续第 7 天签到：发放稀有星卡（正位金卡），不消耗免费解读额度。"""
        openid, headers = _make_api_user()
        today = datetime.date.today()
        _seed_checkins(openid, _consecutive_rows(today - datetime.timedelta(days=1), 6))
        resp = client.post("/tasks/checkin", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["streak"] == 7
        assert data["collectible_type"] == "star_card", f"第7天应发稀有星卡: {data}"
        coll = data["collectible"]
        assert 1 <= coll["card_id"] <= 78
        assert coll["card_name"], "星卡响应应带牌名"
        assert coll["tier"] == "gold"
        assert "稀有星卡" in data["reward"], f"奖励文案应提及稀有星卡: {data['reward']}"

        # 不消耗任何额度：免费解读照常 +1，星尘照常累计（本次签到 +1）
        assert data["reward_days"] == 1  # 叠加会员体验 1 天
        user = _read_user(openid)
        assert user.free_readings_today == 1, "星卡不应消耗免费解读额度"
        assert user.stardust_total == 1
        assert user.is_member is True, "7 日里程碑的会员奖励仍应生效"

        # 存储正确：star_cards 一条记录，且与响应一致
        cards = star_cards_of(user)
        assert len(cards) == 1
        assert cards[0]["card_id"] == coll["card_id"]

        # milestones_claimed 同步记录，防重复发放
        async def _read_today_checkin():
            async with async_session() as session:
                result = await session.execute(
                    select(CheckIn).where(CheckIn.user_id == user.id, CheckIn.checkin_date == today)
                )
                return result.scalar_one()

        ci = asyncio.run(_read_today_checkin())
        assert "7" in (ci.milestones_claimed or "").split(",")

        # status 接口同步返回星卡（含牌名）
        status = client.get("/tasks/status", headers=headers).json()
        assert len(status["star_cards"]) == 1
        assert status["star_cards"][0]["card_name"] == coll["card_name"]
        assert status["wallpapers"] == []

    def test_day30_grants_wallpaper_not_card(self, client):
        """连续第 30 天签到：发放星光壁纸（不发星卡），会员体验 3 天照常。"""
        openid, headers = _make_api_user()
        today = datetime.date.today()
        _seed_checkins(openid, _consecutive_rows(today - datetime.timedelta(days=1), 29))
        resp = client.post("/tasks/checkin", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["streak"] == 30
        assert data["collectible_type"] == "wallpaper", f"第30天应发星光壁纸: {data}"
        assert "星光壁纸" in data["reward"]
        assert data["reward_days"] == 3

        user = _read_user(openid)
        assert wallpapers_of(user) == [today.isoformat()]
        assert star_cards_of(user) == [], "30 日只发壁纸，不发星卡"
        assert user.is_member is True

    def test_milestone_not_reclaimed_after_streak_break(self, client, monkeypatch):
        """断签后重新累计到 7 天：milestones_claimed 已含 "7" → 星卡/会员均不重复发放。"""

        class _FakeDate(datetime.date):
            @classmethod
            def today(cls):
                return cls(2026, 8, 16)

        monkeypatch.setattr("app.api.tasks.date", _FakeDate)

        openid, headers = _make_api_user()
        # 第一段：07-27..08-02 连续 7 天，08-02 达成 7 日里程碑（已认领）
        rows = _consecutive_rows(datetime.date(2026, 8, 2), 7, claimed_day=7, claimed="7")
        # 断签一周后：08-10..08-15 重新连续 6 天
        rows += _consecutive_rows(datetime.date(2026, 8, 15), 6)
        _seed_checkins(openid, rows)

        resp = client.post("/tasks/checkin", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["streak"] == 7
        assert data["collectible_type"] == "", f"已认领的里程碑不应重复发奖: {data}"
        assert data["reward"] == NARRATIVE_REWARD

        user = _read_user(openid)
        assert star_cards_of(user) == [], "星卡不得重复发放"
        assert wallpapers_of(user) == []
        assert user.is_member is False, "会员体验也不得重复发放"

    def test_duplicate_day_checkin_has_no_collectible(self, client):
        """同一天重复签到：早退返回，不发任何收藏品。"""
        _openid, headers = _make_api_user()
        first = client.post("/tasks/checkin", headers=headers)
        assert first.json()["collectible_type"] == ""
        second = client.post("/tasks/checkin", headers=headers)
        assert second.json()["collectible_type"] == ""

    def test_checkin_normal_reward_narrative(self, client):
        """签到成功文案统一「星光馈赠」话术（缺口 3 后端同步）。"""
        _openid, headers = _make_api_user()
        data = client.post("/tasks/checkin", headers=headers).json()
        assert data["reward"] == NARRATIVE_REWARD, f"普通签到话术应为 {NARRATIVE_REWARD}: {data['reward']}"


# ─────────────────────────────────────────────────────────────────────────────
# GET /tasks/status — 收藏品数据
# ─────────────────────────────────────────────────────────────────────────────


class TestStatusCollectibles:
    def test_status_returns_star_cards_and_wallpapers(self, client):
        """status 返回 star_cards（含牌名）/ wallpapers，供我的页星卡收藏区渲染。"""
        openid, headers = _make_api_user()

        async def _grant():
            async with async_session() as session:
                user = (await session.execute(select(User).where(User.openid == openid))).scalar_one()
                grant_star_card(user, 17, "2026-07-26")
                grant_wallpaper(user, "2026-08-10")
                await session.commit()

        asyncio.run(_grant())
        data = client.get("/tasks/status", headers=headers).json()
        assert data["star_tier_name"]  # 星阶名照常返回
        assert len(data["star_cards"]) == 1
        sc = data["star_cards"][0]
        assert sc["card_id"] == 17
        assert sc["card_name"] == "卡牌17"  # conftest 种 78 张牌 name_zh=f"卡牌{i}"
        assert sc["tier"] == "gold"
        assert sc["date"] == "2026-07-26"
        assert data["wallpapers"] == ["2026-08-10"]

    def test_status_no_collectibles_empty_lists(self, client):
        """无收藏时返回空列表（我的页空态优雅，前端不用判空处理异常）。"""
        _openid, headers = _make_api_user()
        data = client.get("/tasks/status", headers=headers).json()
        assert data["star_cards"] == []
        assert data["wallpapers"] == []
