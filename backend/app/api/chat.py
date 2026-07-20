"""
AI follow-up chat API for tarot readings.

- POST /readings/{reading_id}/chat  --  send a follow-up message about a reading
"""

import logging

from openai import AsyncOpenAI
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models.reading import ChatMessage, Reading
from app.models.user import User
from app.schemas.chat import ActionItem, ChatRequest, ChatResponse
from app.utils.auth import get_current_user
from .readings import _reset_daily_count_if_new_day, parse_action_items

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
    # ── Reset daily counters if it's a new day ──
    await _reset_daily_count_if_new_day(user)

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

    # ── Build conversation history for DeepSeek ──
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                f"你是一个温柔睿智的塔罗导师。用户刚才的解读结果是：\n"
                f"{(reading.interpretation or '')[:500]}\n\n"
                f"请基于这个解读，继续和用户深入探讨他们的问题。保持连续性和一致性。\n\n"
                f"【行动建议】\n"
                f"在回答的最后，如果合适的话，请给出 1-3 条具体的行动建议，"
                f"使用 [ACTION]建议内容[/ACTION] 格式。\n"
                f"例如：[ACTION]每天晚上写一篇日记，记录今天的感受[/ACTION]\n"
                f"每条建议请使用第二人称「你」，语气鼓励、温暖。"
            ),
        }
    ]
    for msg in reading.chat_messages:
        messages.append({"role": msg.role, "content": msg.content})

    # ── Call DeepSeek API ──
    if not settings.DEEPSEEK_API_KEY:
        raise HTTPException(status_code=503, detail="AI服务未配置")

    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )
    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=settings.AI_MAX_TOKENS,
            messages=messages,
            timeout=60.0,
        )
        ai_reply = response.choices[0].message.content
    except Exception:
        logger.exception("Failed to get AI chat reply")
        raise HTTPException(status_code=502, detail="AI回复生成失败")

    # ── Save the AI response ──
    ai_msg = ChatMessage(reading_id=reading_id, role="assistant", content=ai_reply)
    db.add(ai_msg)

    # ── Parse action items from chat response ──
    action_items = parse_action_items(ai_reply)

    # ── Update daily counter (free users only) ──
    if not user.is_member:
        user.free_chats_today += 1

    # ── Return response ──
    return ChatResponse(
        reply=ai_reply,
        remaining_free=max(0, settings.FREE_CHAT_MESSAGES - user.free_chats_today),
        action_items=[ActionItem(**a) for a in action_items],
    )
