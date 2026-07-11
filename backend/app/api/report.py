"""
Annual report API endpoint.

- GET /report/annual – generate an AI-powered annual fortune report (members only)
"""

import random
from datetime import date

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.card import TarotCard
from app.models.user import User
from app.services.tarot import draw_cards
from app.utils.auth import get_current_user

router = APIRouter(prefix="/report", tags=["年度报告"])


@router.get("/annual")
async def get_annual_report(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an annual fortune report with 13 cards (one per month + theme)."""
    if not user.is_member:
        raise HTTPException(status_code=402, detail="年度报告仅限会员使用")

    # Draw 13 cards for the year ahead
    cards_data = draw_cards("year_ahead")
    cards_info = []
    for c in cards_data:
        result = await db.execute(
            select(TarotCard).where(TarotCard.id == c["card_id"])
        )
        card = result.scalar_one()
        direction = "逆位" if c["is_reversed"] else "正位"
        cards_info.append({
            "month": c["position_name"],
            "card_name": card.name_zh,
            "direction": direction,
            "meaning": card.meaning_upright[:200] if not c["is_reversed"] else card.meaning_reversed[:200],
        })

    # AI generates the annual report
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = f"""生成一份专业的塔罗年度运势报告。当前年份: {date.today().year}

各月运势牌:
{chr(10).join(f'{c["month"]}: {c["card_name"]}({c["direction"]})' for c in cards_info)}

请撰写一份温暖的年度运势报告，包含:
1. 年度主题：这一年的核心能量是什么
2. 逐月运势：每个月的情感、事业、财运要点（每个月3-4句话）
3. 关键月份：哪几个月是关键转折点
4. 年度寄语"""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=3072,
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "cards": cards_info,
        "report": response.content[0].text,
        "generated_at": str(date.today()),
    }
