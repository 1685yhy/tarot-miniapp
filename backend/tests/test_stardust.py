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
