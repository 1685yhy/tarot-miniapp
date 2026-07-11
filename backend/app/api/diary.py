import random
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.models.diary import DiaryEntry
from app.models.card import TarotCard
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.diary import DiaryCreate, DiaryEntryResponse, DiaryListResponse

router = APIRouter(prefix="/diary", tags=["塔罗日记"])


@router.post("/entries", response_model=DiaryEntryResponse)
async def create_entry(
    body: DiaryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Draw a random card for today's reflection
    result = await db.execute(select(func.count(TarotCard.id)))
    count = result.scalar()
    random_id = random.randint(1, count)

    entry = DiaryEntry(
        user_id=user.id,
        entry_date=date.today(),
        mood=body.mood,
        card_id=random_id,
        reflection=body.reflection,
    )
    db.add(entry)
    await db.flush()

    card_result = await db.execute(select(TarotCard).where(TarotCard.id == random_id))
    card = card_result.scalar_one()

    return DiaryEntryResponse(
        id=entry.id,
        date=str(entry.entry_date),
        mood=entry.mood,
        card={"id": card.id, "name_zh": card.name_zh, "meaning_upright": card.meaning_upright[:200]},
        reflection=entry.reflection,
    )


@router.get("/entries", response_model=DiaryListResponse)
async def list_entries(
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page_size = 20
    offset = (page - 1) * page_size
    result = await db.execute(
        select(DiaryEntry)
        .where(DiaryEntry.user_id == user.id)
        .order_by(DiaryEntry.entry_date.desc())
        .offset(offset)
        .limit(page_size)
    )
    entries = result.scalars().all()

    return DiaryListResponse(
        entries=[
            {
                "id": e.id,
                "date": str(e.entry_date),
                "mood": e.mood,
                "reflection": e.reflection,
            }
            for e in entries
        ],
        page=page,
    )
