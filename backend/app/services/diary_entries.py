"""日记/手账共享 upsert 服务（T1-3 从 api/diary.py 抽取，不复制逻辑）。

``upsert_diary_entry`` 同时服务 /diary/entries（api/diary.py）与
/journal/entries（api/journal.py）：同一用户同一天只保留一行 diary_entries
（6 档情绪的唯一情绪数据源），同日再次提交走更新路径。

更新路径只覆盖 mood 与非空 reflection，不动 card / image_url —— 与抽取前的
diary.py 行为完全一致（回归约束，见 tests/test_diary_review.py）。
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.card import TarotCard
from app.models.diary import DiaryEntry
from app.models.user import User


async def upsert_diary_entry(
    db: AsyncSession,
    user: User,
    mood: str | None,
    reflection: str | None = None,
    card_id: int | None = None,
    entry_date: date | None = None,
    image_url: str | None = None,
) -> DiaryEntry:
    """同日已存在则更新（mood/reflection），否则新建；card_id 缺省随机取一张。

    - 更新路径：只覆盖 mood 与非空 reflection，不动 card / image_url
    - 新建路径：card_id 缺省随机取一张；指定卡牌不存在 → 404；无卡牌 → 500
    - 返回已 flush 的 DiaryEntry（由调用方负责最终 commit）
    """
    entry_date = entry_date or date.today()

    # ── 同日已存在 → 更新（不新建，保持 diary 语义）──
    existing_result = await db.execute(
        select(DiaryEntry).where(
            DiaryEntry.user_id == user.id,
            DiaryEntry.entry_date == entry_date,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        existing.mood = mood
        if reflection is not None:
            existing.reflection = reflection
        await db.flush()
        return existing

    # ── 新建：指定卡牌（404 校验）或随机兜底 ──
    if card_id is not None:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id == card_id)
        )
        card = card_result.scalar_one_or_none()
        if card is None:
            raise HTTPException(status_code=404, detail="卡牌不存在")
    else:
        card_result = await db.execute(
            select(TarotCard).order_by(func.random()).limit(1)
        )
        card = card_result.scalar_one_or_none()
        if card is None:
            raise HTTPException(status_code=500, detail="卡牌数据为空")

    entry = DiaryEntry(
        user_id=user.id,
        entry_date=entry_date,
        mood=mood,
        card_id=card.id,
        reflection=reflection,
        image_url=image_url,
    )
    db.add(entry)
    await db.flush()
    return entry
