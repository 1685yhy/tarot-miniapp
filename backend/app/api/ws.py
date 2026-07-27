"""
WebSocket endpoint for streaming AI chat responses.

- WS /ws/chat/{reading_id}  --  stream follow-up chat response tokens
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import async_session
from app.models.reading import ChatMessage, Reading
from app.models.user import User
from app.services.ai_engine import stream_chat_response
from app.utils.auth import decode_token
from .readings import _reset_daily_count_if_new_day

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/chat/{reading_id}")
async def chat_stream(websocket: WebSocket, reading_id: str):
    """
    WebSocket that streams AI follow-up chat tokens character-by-character.

    Protocol (client → server):
        1. Connect with ``?token=<JWT>`` query parameter
        2. Send the user's message text as a single WebSocket text frame

    Protocol (server → client):
        - One WebSocket text frame per content token
        - ``[DONE]``  --  streaming completed successfully
        - ``[ERROR] <description>``  --  an error occurred (also closes)

    The server saves both the user message and the complete AI response
    to the database.  Free-tier quota checks are enforced server-side.
    """
    await websocket.accept()

    # ── Authenticate via query param (WeChat WS cannot set headers) ──
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.send_text("[ERROR] 未提供登录凭证")
        await websocket.close()
        return

    try:
        payload = decode_token(token)
        user_id = payload["sub"]
    except Exception:
        await websocket.send_text("[ERROR] 登录凭证无效")
        await websocket.close()
        return

    # ── Wait for the user's message ──
    try:
        user_message_text = await websocket.receive_text()
    except WebSocketDisconnect:
        return

    # ── Database operations ──
    async with async_session() as db:
        try:
            # Fetch user
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                await websocket.send_text("[ERROR] 用户不存在")
                await websocket.close()
                return

            # Fetch reading (must belong to the authenticated user)
            result = await db.execute(
                select(Reading)
                .where(Reading.id == reading_id, Reading.user_id == user.id)
                .options(selectinload(Reading.chat_messages))
            )
            reading = result.scalar_one_or_none()
            if not reading:
                await websocket.send_text("[ERROR] 解读记录不存在")
                await websocket.close()
                return

            # ── Free-tier quota check ──
            await _reset_daily_count_if_new_day(user)
            if not user.is_member and user.free_chats_today >= settings.FREE_CHAT_MESSAGES:
                await websocket.send_text("[ERROR] 402: 今日追问次数已用完")
                await websocket.close()
                return

            # ── Save user message ──
            user_msg = ChatMessage(
                reading_id=reading_id, role="user", content=user_message_text,
            )
            db.add(user_msg)
            await db.flush()

            # Update free-tier counter
            if not user.is_member:
                user.free_chats_today += 1

            # ── Build conversation context ──
            messages: list[dict] = [
                {
                    "role": "system",
                    "content": (
                        f"你是一个温柔睿智的塔罗导师。用户刚才的解读结果是：\n"
                        f"{(reading.interpretation or '')[:500]}\n\n"
                        f"请基于这个解读，继续和用户深入探讨他们的问题。"
                        f"保持连续性和一致性。\n\n"
                        f"【行动建议】\n"
                        f"在回答的最后，如果合适的话，请给出 1-3 条具体的行动建议，"
                        f"使用 [ACTION]建议内容[/ACTION] 格式。\n"
                        f"每条建议请使用第二人称「你」，语气鼓励、温暖。"
                    ),
                },
            ]
            for msg in reading.chat_messages:
                messages.append({"role": msg.role, "content": msg.content})
            # Explicitly append the new user message (the eager-loaded
            # ``reading.chat_messages`` may not include it yet).
            messages.append({"role": "user", "content": user_message_text})

            # ── Stream AI response ──
            full_response = ""
            try:
                async for token in stream_chat_response(messages):
                    full_response += token
                    await websocket.send_text(token)

                # ── Save AI response to DB ──
                ai_msg = ChatMessage(
                    reading_id=reading_id,
                    role="assistant",
                    content=full_response,
                )
                db.add(ai_msg)
                await db.commit()

                await websocket.send_text("[DONE]")

            except Exception as exc:
                logger.exception("WebSocket streaming error for %s", reading_id)
                # Still save whatever was accumulated
                if full_response.strip():
                    ai_msg = ChatMessage(
                        reading_id=reading_id,
                        role="assistant",
                        content=full_response,
                    )
                    db.add(ai_msg)
                await db.commit()
                await websocket.send_text(f"[ERROR] {str(exc)}")

        except WebSocketDisconnect:
            await db.rollback()
            return
        except Exception as exc:
            logger.exception("WebSocket handler error for %s", reading_id)
            await db.rollback()
            try:
                await websocket.send_text(f"[ERROR] {str(exc)}")
            except Exception:
                pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass
