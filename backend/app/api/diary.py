import os
import uuid
import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI
from app.db.database import get_db
from app.models.diary import DiaryEntry
from app.models.card import TarotCard
from app.models.user import User
from app.services.diary_entries import upsert_diary_entry
from app.utils.auth import get_current_user
from app.utils.quota import reset_ai_quota_if_new_day
from app.config import settings
from app.schemas.diary import (
    DiaryCardBrief,
    DiaryCreate,
    DiaryEntryResponse,
    DiaryListResponse,
    DiaryReviewResponse,
    DiarySharePreview,
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
    """记录/更新今日日记（T1-3 起与手账共用 services.diary_entries.upsert_diary_entry）。"""
    today = date.today()
    entry = await upsert_diary_entry(
        db,
        user,
        body.mood,
        reflection=body.reflection,
        card_id=body.card_id,
        entry_date=today,
        image_url=body.image_url,
    )

    card = None
    if entry.card_id:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id == entry.card_id)
        )
        card = card_result.scalar_one_or_none()

    return DiaryEntryResponse(
        id=entry.id,
        date=str(entry.entry_date),
        mood=entry.mood,
        card={"id": card.id, "name_zh": card.name_zh, "meaning_upright": card.meaning_upright[:200]} if card else None,
        reflection=entry.reflection,
        image_url=entry.image_url,
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
                "image_url": e.image_url,
            }
            for e in entries
        ],
        page=page,
    )


@router.get("/entries/{entry_id}/share-preview", response_model=DiarySharePreview)
async def entry_share_preview(
    entry_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Anonymized share preview for a diary entry.

    Returns only share-safe fields for the poster: a short excerpt of the
    reflection (first 200 chars), mood + emoji, entry date, and card brief.
    All user-identifying information is stripped — no nickname, no user_id,
    no raw reflection beyond the excerpt.
    """
    result = await db.execute(
        select(DiaryEntry).where(
            DiaryEntry.id == entry_id,
            DiaryEntry.user_id == user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="日记不存在")

    card = None
    if entry.card_id:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id == entry.card_id)
        )
        card = card_result.scalar_one_or_none()

    mood_key = entry.mood or "thoughtful"
    mood_emoji = MOOD_EMOJI_MAP.get(mood_key, ("🤔", 3))[0]
    excerpt = (entry.reflection or "").strip()[:200]

    return DiarySharePreview(
        date=str(entry.entry_date),
        mood=entry.mood,
        mood_emoji=mood_emoji,
        excerpt=excerpt,
        card=(
            DiaryCardBrief(
                id=card.id,
                name_zh=card.name_zh,
                meaning_upright=card.meaning_upright[:200],
            )
            if card
            else None
        ),
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

    Non-members are limited to ``FREE_DIARY_AI_DAILY`` AI calls per day
    (reflection-prompt + review share the same budget).
    """
    # ── Free-tier daily quota (non-members only) ──
    if not user.is_member:
        reset_ai_quota_if_new_day(user)
        if user.diary_ai_count_today >= settings.FREE_DIARY_AI_DAILY:
            raise HTTPException(status_code=402, detail="今日 AI 日记次数已用完，请开通会员或明日再来")

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

    # ── Count toward the daily quota (non-members only) ──
    if not user.is_member:
        user.diary_ai_count_today += 1

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


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a diary entry (only the owner can delete)."""
    result = await db.execute(
        select(DiaryEntry).where(
            DiaryEntry.id == entry_id,
            DiaryEntry.user_id == user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="日记不存在")
    await db.delete(entry)
    return {"ok": True}


@router.put("/entries/{entry_id}", response_model=DiaryEntryResponse)
async def update_entry(
    entry_id: str,
    body: DiaryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a diary entry (partial update)."""
    result = await db.execute(
        select(DiaryEntry).where(
            DiaryEntry.id == entry_id,
            DiaryEntry.user_id == user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="日记不存在")
    if body.mood is not None:
        entry.mood = body.mood
    if body.reflection is not None:
        entry.reflection = body.reflection
    if body.image_url is not None:
        entry.image_url = body.image_url
    await db.flush()

    # Load card for response
    card = None
    if entry.card_id:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id == entry.card_id)
        )
        card = card_result.scalar_one_or_none()

    return DiaryEntryResponse(
        id=entry.id,
        date=str(entry.entry_date),
        mood=entry.mood,
        card={"id": card.id, "name_zh": card.name_zh, "meaning_upright": card.meaning_upright[:200]} if card else None,
        reflection=entry.reflection,
        image_url=entry.image_url,
    )


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """
    Upload an image for a diary entry.
    Saves to static/diary_uploads/ and returns the URL.
    """
    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="仅支持 JPG/PNG/WebP/GIF 格式的图片")

    # Determine upload directory
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "diary_uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # Generate unique filename — derive extension from content_type (not client filename)
    content_type = file.content_type or "image/jpeg"
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
    ext = ext_map.get(content_type, ".jpg")
    filename = f"{user.id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(upload_dir, filename)

    # Save file
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过 5MB")
    with open(filepath, "wb") as f:
        f.write(content)

    # Return accessible URL
    url = f"/static/diary_uploads/{filename}"
    return {"url": url}


class ReflectionPromptRequest(PydanticBaseModel):
    card_id: int
    card_name: str


@router.post("/reflection-prompt")
async def get_reflection_prompt(
    body: ReflectionPromptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a personalized reflection question based on today's card.
    Uses the card teaching database + AI to create a unique, thought-provoking prompt.

    Non-members are limited to ``FREE_DIARY_AI_DAILY`` AI calls per day
    (reflection-prompt + review share the same budget).
    """
    # ── Free-tier daily quota (non-members only) ──
    if not user.is_member:
        reset_ai_quota_if_new_day(user)
        if user.diary_ai_count_today >= settings.FREE_DIARY_AI_DAILY:
            raise HTTPException(status_code=402, detail="今日 AI 日记次数已用完，请开通会员或明日再来")

    # ── Fetch card teaching data ──
    from app.models.card_teaching import CardTeaching

    result = await db.execute(
        select(CardTeaching).where(CardTeaching.card_id == body.card_id)
    )
    teaching = result.scalar_one_or_none()

    teaching_context = ""
    if teaching:
        teaching_context = (
            f"卡牌符号: {teaching.symbols or '无'}\n"
            f"生活关联: {teaching.life_connection or '无'}\n"
            f"反思提示: {getattr(teaching, 'reflection_prompt', '无')}"
        )

    # ── Call AI to generate reflection question ──
    client = _get_ai_client()
    if not client:
        # Fallback without AI
        if not user.is_member:
            user.diary_ai_count_today += 1
        return {"question": f"今天的「{body.card_name}」给你带来了什么感受？它在哪些方面触动了你？"}

    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=200,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是星光映照的塔罗日记引导师。用户今天抽到了一张塔罗牌，"
                        "你需要生成一个引人深思的反思问题，帮助用户将卡牌的智慧融入当天生活。\n\n"
                        "要求:\n"
                        "1. 问题要具体、个人化，不要泛泛的「今天感觉怎么样」\n"
                        "2. 关联卡牌的符号和寓意，但用日常语言表达\n"
                        "3. 问题应该让用户想立刻开始写\n"
                        "4. 温暖而有深度，像朋友的关心\n"
                        "5. 50字以内\n"
                        "6. 只返回问题本身，不要任何前缀或解释"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"卡牌: {body.card_name}\n"
                        f"{teaching_context}\n"
                        f"请为这位用户生成一个今天的反思问题。"
                    ),
                },
            ],
            timeout=30.0,
        )
        question = response.choices[0].message.content.strip()
        if not user.is_member:
            user.diary_ai_count_today += 1
        return {"question": question}
    except Exception as exc:
        logger.warning("Failed to generate reflection prompt: %s", exc)
        if not user.is_member:
            user.diary_ai_count_today += 1
        return {"question": f"今天的「{body.card_name}」想告诉你什么？花几分钟写下你的感受吧。"}
