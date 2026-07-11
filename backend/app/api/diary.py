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
    today = date.today()

    # ── Check if entry already exists for today → update instead ──
    existing_result = await db.execute(
        select(DiaryEntry).where(
            DiaryEntry.user_id == user.id,
            DiaryEntry.entry_date == today,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        # Update existing entry
        existing.mood = body.mood
        if body.reflection is not None:
            existing.reflection = body.reflection
        await db.flush()
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id == existing.card_id)
        )
        card = card_result.scalar_one_or_none()
        return DiaryEntryResponse(
            id=existing.id,
            date=str(existing.entry_date),
            mood=existing.mood,
            card={"id": card.id, "name_zh": card.name_zh, "meaning_upright": card.meaning_upright[:200]} if card else None,
            reflection=existing.reflection,
        )

    # ── Create new entry ──
    card_result = await db.execute(
        select(TarotCard).order_by(func.random()).limit(1)
    )
    card = card_result.scalar_one_or_none()
    if card is None:
        raise HTTPException(status_code=500, detail="卡牌数据为空")

    entry = DiaryEntry(
        user_id=user.id,
        entry_date=today,
        mood=body.mood,
        card_id=card.id,
        reflection=body.reflection,
    )
    db.add(entry)
    await db.flush()

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

    # Eager-load cards for all entries
    card_ids = [e.card_id for e in entries if e.card_id is not None]
    cards_map = {}
    if card_ids:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id.in_(card_ids))
        )
        for card in card_result.scalars().all():
            cards_map[card.id] = card

    return DiaryListResponse(
        entries=[
            {
                "id": e.id,
                "date": str(e.entry_date),
                "mood": e.mood,
                "card": {
                    "id": cards_map[e.card_id].id,
                    "name_zh": cards_map[e.card_id].name_zh,
                    "meaning_upright": cards_map[e.card_id].meaning_upright[:200],
                } if e.card_id and e.card_id in cards_map else None,
                "reflection": e.reflection,
            }
            for e in entries
        ],
        page=page,
    )
