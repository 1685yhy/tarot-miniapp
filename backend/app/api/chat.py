"""
AI follow-up chat API for tarot readings.

- POST /readings/{reading_id}/chat  --  send a follow-up message about a reading
"""

import logging

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models.reading import ChatMessage, Reading
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/readings", tags=["AI追问"])


@router.post("/{reading_id}/chat", response_model=ChatResponse)
async def chat_followup(
    reading_id: str,
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a follow-up question about a completed tarot reading.

    Free-tier users are limited to ``FREE_CHAT_MESSAGES`` per day.
    Members have unlimited usage.
    """
    # ── Free-tier limit check ──
    if not user.is_member and user.free_chats_today >= settings.FREE_CHAT_MESSAGES:
        raise HTTPException(status_code=402, detail="今日追问次数已用完")

    # ── Verify the reading exists and belongs to the current user ──
    result = await db.execute(
        select(Reading)
        .where(Reading.id == reading_id, Reading.user_id == user.id)
        .options(selectinload(Reading.chat_messages))
    )
    reading = result.scalar_one_or_none()
    if not reading:
        raise HTTPException(status_code=404, detail="解读记录不存在")

    # ── Save the user's message ──
    user_msg = ChatMessage(reading_id=reading_id, role="user", content=req.message)
    db.add(user_msg)
    await db.flush()  # ensure the message is visible in history below

    # ── Build conversation history for Claude ──
    messages: list[dict] = []
    for msg in reading.chat_messages:
        messages.append({"role": msg.role, "content": msg.content})
    # Also include the message we just saved (already flushed so it's in the list)
    messages.append({"role": "user", "content": req.message})

    # ── Call Claude API ──
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI服务未配置")

    system_prompt = (
        f"你是一个温柔睿智的塔罗导师。用户刚才的解读结果是：\n"
        f"{reading.interpretation[:500]}\n\n"
        f"请基于这个解读，继续和用户深入探讨他们的问题。保持连续性和一致性。"
    )

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
            timeout=60.0,
        )
        ai_reply = response.content[0].text
    except Exception:
        logger.exception("Failed to get AI chat reply")
        raise HTTPException(status_code=502, detail="AI回复生成失败")

    # ── Save the AI response ──
    ai_msg = ChatMessage(reading_id=reading_id, role="assistant", content=ai_reply)
    db.add(ai_msg)

    # ── Update daily counter ──
    user.free_chats_today += 1

    # ── Return response ──
    return ChatResponse(
        reply=ai_reply,
        remaining_free=max(0, settings.FREE_CHAT_MESSAGES - user.free_chats_today),
    )
