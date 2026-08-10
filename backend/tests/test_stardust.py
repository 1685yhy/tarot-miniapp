"""
星尘/星阶字段与阈值服务测试。

- User 模型默认值：stardust_total / star_tier 建用户后默认 0
- tier_for(stardust) 按 STAR_TIERS 阈值返回星阶索引
- tier_name(tier) 返回星阶名称
"""

import asyncio
import uuid

from sqlalchemy import select

from app.db.database import async_session
from app.models.user import User
from app.services.stardust import STAR_TIERS, tier_for, tier_name
from app.utils.auth import create_token


def _make_api_user() -> tuple[str, dict]:
    """创建独立测试用户，返回 (openid, 认证请求头)。"""
    openid = f"stardust-api-{uuid.uuid4().hex[:12]}"

    async def _run():
        async with async_session() as session:
            user = User(openid=openid)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    user = asyncio.run(_run())
    return openid, {"Authorization": f"Bearer {create_token(user.id, user.token_version)}"}


# ─────────────────────────────────────────────────────────────────────────────
# User 模型默认值
# ─────────────────────────────────────────────────────────────────────────────


def test_new_user_defaults_to_zero_stardust():
    """新建用户 stardust_total / star_tier 默认 0。"""

    async def _run():
        async with async_session() as session:
            user = User(openid=f"stardust-test-{uuid.uuid4().hex[:12]}")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            assert user.stardust_total == 0
            assert user.star_tier == 0

    asyncio.run(_run())


def test_persisted_user_reads_stardust_fields():
    """写入非零星尘后重新读取字段不丢失。"""

    async def _run():
        async with async_session() as session:
            user = User(openid=f"stardust-persist-{uuid.uuid4().hex[:12]}")
            user.stardust_total = 42
            user.star_tier = 2
            session.add(user)
            await session.commit()
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.openid.like("stardust-persist-%"))
            )
            found = result.scalar_one()
            assert found.stardust_total == 42
            assert found.star_tier == 2

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# STAR_TIERS 常量
# ─────────────────────────────────────────────────────────────────────────────


def test_star_tiers_constant_shape():
    """STAR_TIERS 为 (阈值, 名称) 有序列表，起点为 0。"""
    assert STAR_TIERS[0] == (0, "微光")
    assert [t for t, _ in STAR_TIERS] == sorted(t for t, _ in STAR_TIERS)
    assert len(STAR_TIERS) == 4


# ─────────────────────────────────────────────────────────────────────────────
# tier_for 边界
# ─────────────────────────────────────────────────────────────────────────────


def test_tier_for_boundaries():
    """星阶阈值：0→0，7→1，29→1，30→2，100→3。"""
    assert tier_for(0) == 0
    assert tier_for(7) == 1
    assert tier_for(29) == 1
    assert tier_for(30) == 2
    assert tier_for(100) == 3


def test_tier_for_out_of_range():
    """低于 0 按 0 处理，高于最高阈值封顶到最高阶。"""
    assert tier_for(-5) == 0
    assert tier_for(999) == 3


# ─────────────────────────────────────────────────────────────────────────────
# tier_name
# ─────────────────────────────────────────────────────────────────────────────


def test_tier_name():
    """星阶名称映射。"""
    assert tier_name(0) == "微光"
    assert tier_name(1) == "星光"
    assert tier_name(2) == "星辉"
    assert tier_name(3) == "星冠"


def test_tier_name_out_of_range():
    """越界星阶回退到最近合法名称。"""
    assert tier_name(99) == "星冠"
    assert tier_name(-1) == "微光"


# ─────────────────────────────────────────────────────────────────────────────
# 签到接口产出星尘/星阶（任务2）
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckinStardust:
    """POST /tasks/checkin 签到收集星尘、GET /tasks/status 返回星尘/星阶。"""

    def test_checkin_first_time_awards_one_stardust(self, client):
        """首次签到：stardust_total=1，star_tier=0（tier_for(1)），star_tier_name='微光'。"""
        _openid, headers = _make_api_user()
        resp = client.post("/tasks/checkin", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["stardust_total"] == 1, f"首次签到应 +1 星尘，got {data}"
        assert data["star_tier"] == tier_for(1)
        assert data["star_tier_name"] == tier_name(tier_for(1))

    def test_checkin_duplicate_does_not_double_stardust(self, client):
        """同一天第 2 次签到返回已签到，不再 +1 星尘。"""
        _openid, headers = _make_api_user()
        first = client.post("/tasks/checkin", headers=headers)
        assert first.status_code == 200
        assert first.json()["stardust_total"] == 1

        second = client.post("/tasks/checkin", headers=headers)
        assert second.status_code == 200, second.text
        second_data = second.json()
        assert second_data["reward"] == "今日已签到"
        assert second_data["stardust_total"] == 1, (
            f"重复签到不应再加星尘，got {second_data['stardust_total']}"
        )

    def test_checkin_persists_star_tier_matches_tier_for(self, client):
        """审查断言：签到写入后库中 star_tier == tier_for(stardust_total)。"""
        openid, headers = _make_api_user()
        resp = client.post("/tasks/checkin", headers=headers)
        assert resp.status_code == 200, resp.text

        async def _read():
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.openid == openid)
                )
                return result.scalar_one()

        user = asyncio.run(_read())
        assert user.stardust_total == 1
        assert user.star_tier == tier_for(user.stardust_total), (
            f"star_tier({user.star_tier}) 必须等于 tier_for(stardust_total)"
            f"({tier_for(user.stardust_total)})，防止展示不一致"
        )

    def test_status_returns_stardust_fields(self, client):
        """GET /tasks/status 返回 stardust_total / star_tier / star_tier_name。"""
        _openid, headers = _make_api_user()
        client.post("/tasks/checkin", headers=headers)
        resp = client.get("/tasks/status", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["stardust_total"] == 1
        assert data["star_tier"] == tier_for(1)
        assert data["star_tier_name"] == tier_name(tier_for(1))
