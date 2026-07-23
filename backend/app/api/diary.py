import random
import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI
from app.db.database import get_db
from app.models.diary import DiaryEntry
from app.models.card import TarotCard
from app.models.user import User
from app.utils.auth import get_current_user
from app.config import settings
from app.schemas.diary import (
    DiaryCreate,
    DiaryEntryResponse,
    DiaryListResponse,
    DiaryReviewResponse,
    WeeklyMoodTrend,
)

logger = logging.getLogger(__name__)


MOOD_EMOJI_MAP = {
    "happy": ("😊", 4.5),
    "calm": ("😌", 3.5),
    "excited": ("🤩", 5),
    "anxious": ("😰", 2),
    "sad": ("😢", 1),
    "thoughtful": ("🤔", 3),
}
MOOD_LABEL_MAP = {
    "happy": "开心",
    "calm": "平静",
    "excited": "兴奋",
    "anxious": "焦虑",
    "sad": "低落",
    "thoughtful": "思考",
}


def _get_ai_client() -> AsyncOpenAI | None:
    if not settings.DEEPSEEK_API_KEY:
        return None
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )

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


@router.get("/review", response_model=DiaryReviewResponse)
async def weekly_review(
    period: str = Query("weekly", pattern="^(weekly|monthly)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI-generated weekly review.
    Collects diary entries from the last 7 days, analyzes mood trends,
    finds the most influential card, and generates an insight + next week guidance.
    """
    today = date.today()
    week_ago = today - timedelta(days=7)
    week_range = f"{week_ago} ~ {today}"

    # ── Fetch last 7 days of diary entries with card data ──
    result = await db.execute(
        select(DiaryEntry)
        .where(
            DiaryEntry.user_id == user.id,
            DiaryEntry.entry_date >= week_ago,
        )
        .order_by(DiaryEntry.entry_date.asc())
    )
    entries = result.scalars().all()

    if not entries:
        return DiaryReviewResponse(
            period=period,
            week_range=week_range,
            entry_count=0,
            mood_trends=[],
            top_card_name=None,
            top_card_count=0,
            ai_insight=None,
            next_week_guidance=None,
            emotional_trend_summary="本周暂无日记记录，开始记录你的每日心情吧。",
        )

    # ── Eager-load cards ──
    card_ids = [e.card_id for e in entries if e.card_id is not None]
    cards_map = {}
    if card_ids:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id.in_(card_ids))
        )
        for card in card_result.scalars().all():
            cards_map[card.id] = card

    # ── Build mood trends ──
    mood_trends: list[WeeklyMoodTrend] = []
    for e in entries:
        mood_key = e.mood or "thoughtful"
        emoji = MOOD_EMOJI_MAP.get(mood_key, ("🤔", 3))[0]
        score = MOOD_EMOJI_MAP.get(mood_key, ("🤔", 3))[1]
        label = MOOD_LABEL_MAP.get(mood_key, "思考")
        mood_trends.append(WeeklyMoodTrend(
            date=str(e.entry_date),
            mood_score=score,
            mood_label=label,
            mood_emoji=emoji,
        ))

    # ── Find most frequent card ──
    card_count = {}
    for e in entries:
        if e.card_id and e.card_id in cards_map:
            name = cards_map[e.card_id].name_zh
            card_count[name] = card_count.get(name, 0) + 1
    top_card_name = None
    top_card_count = 0
    top_card_meaning = None
    if card_count:
        top_card_name = max(card_count, key=card_count.get)
        top_card_count = card_count[top_card_name]
        # Find the meaning for the top card
        for e in entries:
            if e.card_id and e.card_id in cards_map:
                if cards_map[e.card_id].name_zh == top_card_name:
                    top_card_meaning = cards_map[e.card_id].meaning_upright[:200]
                    break

    # ── Build entries text for AI ──
    entries_text_parts = []
    for e in entries:
        mood_key = e.mood or "thoughtful"
        mood_label = MOOD_LABEL_MAP.get(mood_key, "思考")
        card_name = cards_map[e.card_id].name_zh if e.card_id and e.card_id in cards_map else "无"
        reflection_snippet = (e.reflection[:80] + "...") if e.reflection and len(e.reflection) > 80 else (e.reflection or "无记录")
        entries_text_parts.append(
            f"- {e.entry_date} | 心情: {mood_label} | 卡牌: {card_name} | 感悟: {reflection_snippet}"
        )
    entries_text = "\n".join(entries_text_parts)

    # ── Call DeepSeek AI for insight generation ──
    ai_insight = None
    next_week_guidance = None
    emotional_trend_summary = None

    client = _get_ai_client()
    if client:
        ai_prompt = (
            "你是一位温柔且富有洞察力的塔罗日记分析师。请基于用户过去一周的星光日记记录，"
            "为用户生成一份具有深度的周回顾。\n\n"
            f"【周回顾数据】\n"
            f"时间范围: {week_range}\n"
            f"记录天数: {len(entries)} 天\n\n"
            f"每日记录:\n{entries_text}\n\n"
            f"最频繁出现的卡牌: {top_card_name or '未知'} (出现 {top_card_count} 次)\n"
            f"该卡牌含义: {top_card_meaning or '未知'}\n\n"
            "请严格按照以下 JSON 格式回复，不要包含任何多余内容：\n"
            "{\n"
            '  "emotional_trend_summary": "用一句话总结本周情绪波动趋势（例如：本周情绪呈上升趋势，从周初的焦虑逐渐转向平静。）",\n'
            '  "ai_insight": "基于用户的日记和卡牌，生成一句有启发性的洞察（50字以内，温暖而深刻，像是来自一个了解用户的老朋友）",\n'
            '  "next_week_guidance": "为下周给出具体的行动指引和心灵建议（80字以内，可操作的建议）"\n'
            "}"
        )

        try:
            response = await client.chat.completions.create(
                model=settings.DEEPSEEK_MODEL,
                max_tokens=settings.AI_MAX_TOKENS,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位温柔睿智的塔罗日记分析师，精通情绪分析和卡牌解读。回复必须只输出纯 JSON 对象，不含任何 markdown 代码块标记或其他文字。",
                    },
                    {"role": "user", "content": ai_prompt},
                ],
                timeout=60.0,
            )
            content = response.choices[0].message.content
            if content:
                import json
                # Strip potential markdown code block fences
                content_stripped = content.strip()
                if content_stripped.startswith("```"):
                    # Remove code fence
                    lines = content_stripped.split("\n")
                    content_stripped = "\n".join(
                        line for line in lines
                        if not line.strip().startswith("```")
                    )
                content_stripped = content_stripped.strip()
                try:
                    ai_data = json.loads(content_stripped)
                    emotional_trend_summary = ai_data.get("emotional_trend_summary")
                    ai_insight = ai_data.get("ai_insight")
                    next_week_guidance = ai_data.get("next_week_guidance")
                except json.JSONDecodeError:
                    logger.warning("Failed to parse AI response as JSON: %s", content_stripped[:200])
                    # Fallback: use raw content as insight
                    ai_insight = content_stripped[:200]
        except Exception as exc:
            logger.warning("AI weekly review generation failed: %s", exc)

    # ── Compute fallback summary if AI failed ──
    if not emotional_trend_summary and mood_trends:
        scores = [t.mood_score for t in mood_trends]
        avg_score = sum(scores) / len(scores)
        if avg_score > 3.5:
            emotional_trend_summary = "本周整体情绪积极向上，你保持了良好的心态。"
        elif avg_score < 2.5:
            emotional_trend_summary = "本周情绪波动较大，记得照顾好自己的内心。"
        else:
            emotional_trend_summary = "本周情绪较为平稳，有起有落，都是成长的痕迹。"

    return DiaryReviewResponse(
        period=period,
        week_range=week_range,
        entry_count=len(entries),
        mood_trends=mood_trends,
        top_card_name=top_card_name,
        top_card_count=top_card_count,
        top_card_meaning=top_card_meaning,
        ai_insight=ai_insight,
        next_week_guidance=next_week_guidance,
        emotional_trend_summary=emotional_trend_summary,
    )
