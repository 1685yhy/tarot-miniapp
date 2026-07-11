import random
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.card import TarotCard
from app.schemas.card import CardBrief, CardDetail, CardListResponse

router = APIRouter(prefix="/cards", tags=["塔罗百科"])


@router.get("", response_model=CardListResponse)
async def list_cards(
    arcana: str | None = Query(None, description="major 或 minor"),
    suit: str | None = Query(None, description="wands/cups/swords/pentacles"),
    keyword: str | None = Query(None, description="搜索关键词"),
    db: AsyncSession = Depends(get_db),
):
    query = select(TarotCard)
    if arcana:
        query = query.where(TarotCard.arcana == arcana)
    if suit:
        query = query.where(TarotCard.suit == suit)
    if keyword:
        query = query.where(
            (TarotCard.name_zh.contains(keyword))
            | (TarotCard.name_en.contains(keyword))
            | (TarotCard.meaning_upright.contains(keyword))
        )

    result = await db.execute(query.order_by(TarotCard.card_number))
    cards = result.scalars().all()
    return CardListResponse(
        total=len(cards), cards=[CardBrief.model_validate(c) for c in cards]
    )


@router.get("/daily", response_model=CardDetail)
async def daily_card(db: AsyncSession = Depends(get_db)):
    """每日一牌 - 随机抽取一张"""
    result = await db.execute(select(func.count(TarotCard.id)))
    count = result.scalar()
    random_id = random.randint(1, count)
    result = await db.execute(select(TarotCard).where(TarotCard.id == random_id))
    card = result.scalar_one()
    return CardDetail.model_validate(card)


@router.get("/{card_id}", response_model=CardDetail)
async def get_card(card_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TarotCard).where(TarotCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="卡牌不存在")
    return CardDetail.model_validate(card)
