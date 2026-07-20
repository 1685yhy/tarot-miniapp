from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.db.database import get_db
from app.models.card import TarotCard
from app.models.card_teaching import CardTeaching
from app.schemas.card import CardBrief, CardDetail, CardListResponse, CardTeachingResponse

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
            | (TarotCard.meaning_reversed.contains(keyword))
            | (TarotCard.keywords_upright.contains(keyword))
            | (TarotCard.love_upright.contains(keyword))
            | (TarotCard.career_upright.contains(keyword))
            | (TarotCard.finance_upright.contains(keyword))
        )

    result = await db.execute(query.order_by(TarotCard.card_number))
    cards = result.scalars().all()
    return CardListResponse(
        total=len(cards), cards=[CardBrief.model_validate(c) for c in cards]
    )


@router.get("/daily", response_model=CardDetail)
async def daily_card(db: AsyncSession = Depends(get_db)):
    """每日一牌 - 随机抽取一张（使用数据库随机排序，避免ID不连续问题）"""
    result = await db.execute(
        select(TarotCard).order_by(func.random()).limit(1)
    )
    card = result.scalar_one()
    return CardDetail.model_validate(card)


@router.get("/{card_id}", response_model=CardDetail)
async def get_card(card_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TarotCard).where(TarotCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="卡牌不存在")
    return CardDetail.model_validate(card)


@router.get("/{card_id}/teaching", response_model=CardTeachingResponse)
async def get_card_teaching(card_id: int, db: AsyncSession = Depends(get_db)):
    """获取卡牌教学数据（牌面符号解读、典故、关键词、生活关联）。"""
    # Verify card exists
    card_result = await db.execute(select(TarotCard).where(TarotCard.id == card_id))
    card = card_result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="卡牌不存在")

    # Fetch teaching data
    result = await db.execute(
        select(CardTeaching).where(CardTeaching.card_id == card_id)
    )
    teaching = result.scalar_one_or_none()
    if not teaching:
        raise HTTPException(status_code=404, detail="教学数据不存在")

    # Parse JSON string fields to Python objects
    return CardTeachingResponse(
        card_id=teaching.card_id,
        symbols=json.loads(teaching.symbols),
        story=teaching.story,
        keywords_learning=json.loads(teaching.keywords_learning),
        life_connection=teaching.life_connection,
        element_association=teaching.element_association,
    )
