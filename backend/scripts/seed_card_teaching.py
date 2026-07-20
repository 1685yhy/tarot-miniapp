#!/usr/bin/env python3
"""为 78 张塔罗牌填充教学数据（牌面符号、典故、关键词、生活关联、元素关联）。

用法:
    cd /mnt/e/tarot-miniapp/backend
    python -m scripts.seed_card_teaching
"""

import asyncio
import json
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.db.database import Base
from app.models.card import TarotCard
from app.models.card_teaching import CardTeaching


async def seed_card_teaching():
    """Populate the card_teaching table with all 78 cards' teaching data."""
    _engine_kwargs = {"echo": False}
    if "sqlite" not in settings.DATABASE_URL:
        _engine_kwargs["pool_size"] = 20
    else:
        _engine_kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check if already seeded
        existing = await session.execute(select(CardTeaching).limit(1))
        if existing.scalar_one_or_none() is not None:
            print("教学数据已存在，跳过导入。")
            await engine.dispose()
            return

        # Load data from JSON file
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "card_teaching_data.json"
        )
        with open(data_path, "r", encoding="utf-8") as f:
            teaching_data = json.load(f)

        # Build map from card_number to card_id
        result = await session.execute(select(TarotCard).order_by(TarotCard.card_number))
        cards = result.scalars().all()
        card_number_to_id = {c.card_number: c.id for c in cards}

        count = 0
        for item in teaching_data:
            card_id = card_number_to_id.get(item["card_number"])
            if card_id is None:
                print(f"警告: card_number {item['card_number']} 未找到对应卡牌")
                continue

            teaching = CardTeaching(
                card_id=card_id,
                symbols=json.dumps(item["symbols"], ensure_ascii=False),
                story=item["story"],
                keywords_learning=json.dumps(item["keywords_learning"], ensure_ascii=False),
                life_connection=item["life_connection"],
                element_association=item["element_association"],
            )
            session.add(teaching)
            count += 1

        await session.commit()
        print(f"成功导入 {count} 张卡牌的教学数据!")

        # Verify card count
        verify = await session.execute(select(CardTeaching))
        total = len(verify.scalars().all())
        print(f"教学数据总数: {total}")
        assert total == 78, f"预期 78 条教学数据，实际 {total} 条"

    await engine.dispose()


async def main():
    await seed_card_teaching()


if __name__ == "__main__":
    asyncio.run(main())
