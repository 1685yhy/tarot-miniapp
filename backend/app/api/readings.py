"""
Tarot reading API endpoints.

- POST   /readings/spread/{spread_type}   – create a new reading
- GET    /readings/{reading_id}           – retrieve a single reading
- GET    /readings/history                – list the current user's readings
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models.card import TarotCard
from app.models.reading import DrawnCard, Reading
from app.models.user import User
from app.schemas.reading import (
    CreateReadingRequest,
    DrawnCardResponse,
    ReadingHistoryItem,
    ReadingHistoryResponse,
    ReadingResponse,
)
from app.services.ai_engine import generate_reading
from app.services.tarot import draw_cards
from app.utils.auth import get_current_user

router = APIRouter(prefix="/readings", tags=["占卜解读"])


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _today() -> datetime:
    """Return the start-of-day (midnight) for the current UTC date."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def _reset_daily_count_if_new_day(user: User) -> None:
    """
    If the user hasn't done a reading ''today'', reset their daily counters.

    The field ``last_reading_date`` stores the timestamp of the *last*
    reading; we compare its date part against today.
    """
    if user.last_reading_date is None:
        return
    # Compare only the date portion
    last = user.last_reading_date.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if last < _today():
        user.free_readings_today = 0
        user.free_chats_today = 0


async def _load_card_name(db: AsyncSession, card_id: int) -> str:
    result = await db.execute(select(TarotCard.name_zh).where(TarotCard.id == card_id))
    row = result.scalar_one_or_none()
    return row if row else f"卡牌#{card_id}"


async def _load_drawn_cards_response(
    db: AsyncSession, drawn_cards: list[DrawnCard]
) -> list[dict]:
    """Build the ``DrawnCardResponse``-compatible dict list for a reading."""
    resp = []
    for dc in drawn_cards:
        card_name = await _load_card_name(db, dc.card_id)
        resp.append(
            {
                "id": dc.id,
                "card_id": dc.card_id,
                "card_name": card_name,
                "position": dc.position,
                "position_name": dc.position_name,
                "is_reversed": dc.is_reversed,
            }
        )
    return resp


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------


@router.post("/spread/{spread_type}", response_model=ReadingResponse)
async def create_reading(
    spread_type: str,
    req: CreateReadingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Draw cards, create a reading record, and generate an AI interpretation.

    Free-tier users are limited to ``FREE_DAILY_READINGS`` per day.
    Members have unlimited usage.
    """
    # ── Reset daily counters if last reading was on a previous day ──
    await _reset_daily_count_if_new_day(user)

    # ── Free-tier limit check ──
    if not user.is_member and user.free_readings_today >= settings.FREE_DAILY_READINGS:
        raise HTTPException(
            status_code=402,
            detail="今日免费次数已用完，请开通会员",
        )

    # ── Draw cards ──
    cards_data = draw_cards(spread_type)

    # ── Create reading record ──
    reading = Reading(
        user_id=user.id,
        spread_type=spread_type,
        question=req.question,
        theme=req.theme,
        is_paid=user.is_member,
    )
    db.add(reading)
    await db.flush()

    # ── Save DrawnCard rows & collect enriched info for AI ──
    cards_info: list[dict] = []
    for c in cards_data:
        result = await db.execute(
            select(TarotCard).where(TarotCard.id == c["card_id"])
        )
        card = result.scalar_one_or_none()
        if card is None:
            continue  # should never happen with valid IDs

        drawn = DrawnCard(
            reading_id=reading.id,
            card_id=c["card_id"],
            position=c["position"],
            position_name=c["position_name"],
            is_reversed=c["is_reversed"],
        )
        db.add(drawn)

        cards_info.append(
            {
                **c,
                "name_zh": card.name_zh,
                "name_en": card.name_en,
                "image_description": card.image_description,
                "meaning_upright": card.meaning_upright,
                "meaning_reversed": card.meaning_reversed,
                "love_upright": card.love_upright,
                "love_reversed": card.love_reversed,
                "career_upright": card.career_upright,
                "career_reversed": card.career_reversed,
                "finance_upright": card.finance_upright,
                "finance_reversed": card.finance_reversed,
            }
        )

    # ── Generate AI interpretation ──
    interpretation = await generate_reading(
        spread_type, req.question, req.theme, cards_info
    )
    if interpretation is not None:
        reading.interpretation = interpretation

    # ── Update user state ──
    user.free_readings_today += 1
    user.last_reading_date = datetime.now(timezone.utc)

    # ── Flush so the drawn_cards relationship is populated ──
    await db.flush()
    await db.refresh(reading, ["drawn_cards"])

    # ── Build response ──
    drawn_resp = []
    for dc in reading.drawn_cards:
        result = await db.execute(
            select(TarotCard).where(TarotCard.id == dc.card_id)
        )
        card = result.scalar_one_or_none()
        drawn_resp.append(
            {
                "id": dc.id,
                "card_id": dc.card_id,
                "card_name": card.name_zh if card else f"卡牌#{dc.card_id}",
                "position": dc.position,
                "position_name": dc.position_name,
                "is_reversed": dc.is_reversed,
            }
        )

    return ReadingResponse(
        id=reading.id,
        spread_type=reading.spread_type,
        question=reading.question,
        theme=reading.theme,
        interpretation=reading.interpretation,
        is_paid=reading.is_paid,
        created_at=reading.created_at,
        drawn_cards=[DrawnCardResponse(**d) for d in drawn_resp],
    )


@router.get("/history", response_model=ReadingHistoryResponse)
async def list_readings(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's reading history, newest first."""
    # Total count
    count_result = await db.execute(
        select(func.count(Reading.id)).where(Reading.user_id == user.id)
    )
    total = count_result.scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Reading)
        .where(Reading.user_id == user.id)
        .options(selectinload(Reading.drawn_cards))
        .order_by(Reading.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    readings: list[Reading] = result.scalars().all()

    items: list[ReadingHistoryItem] = []
    for r in readings:
        first_card_name = None
        first_card_reversed = None
        if r.drawn_cards:
            fcard = r.drawn_cards[0]
            first_card_name = await _load_card_name(db, fcard.card_id)
            first_card_reversed = fcard.is_reversed

        items.append(
            ReadingHistoryItem(
                id=r.id,
                spread_type=r.spread_type,
                question=r.question,
                theme=r.theme,
                interpretation=r.interpretation,
                is_paid=r.is_paid,
                created_at=r.created_at,
                first_card_name=first_card_name,
                first_card_is_reversed=first_card_reversed,
            )
        )

    return ReadingHistoryResponse(total=total, items=items)


@router.get("/{reading_id}", response_model=ReadingResponse)
async def get_reading(
    reading_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single reading by its ID (must belong to the current user)."""
    result = await db.execute(
        select(Reading)
        .where(Reading.id == reading_id)
        .options(selectinload(Reading.drawn_cards))
    )
    reading = result.scalar_one_or_none()

    if reading is None:
        raise HTTPException(status_code=404, detail="解读不存在")
    if reading.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看他人的解读")

    drawn_resp = await _load_drawn_cards_response(db, reading.drawn_cards)

    return ReadingResponse(
        id=reading.id,
        spread_type=reading.spread_type,
        question=reading.question,
        theme=reading.theme,
        interpretation=reading.interpretation,
        is_paid=reading.is_paid,
        created_at=reading.created_at,
        drawn_cards=[DrawnCardResponse(**d) for d in drawn_resp],
    )
