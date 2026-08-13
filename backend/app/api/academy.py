"""
星灵学堂 API（SDD P2 阶段3 · T6-1）

- POST /academy/learned — 点亮一颗星（学一张牌）：INSERT 成功（rowcount==1）
  才跑里程碑判定（幂等锚：uq_user_card 唯一约束 + 里程碑账本双保险）；
  重复已学 → learned=false 不重复奖励；card_id 非法 → 404
- GET  /academy/lesson/{card_id} — 学习卡页（公开免登录可看牌库；登录附带
  my 进度）；teaching 直接读 card_teaching 表
- POST /academy/review — 复习计数 +1（仅计数不设奖励防刷）
"""

import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.horoscope import card_image_url
from app.db.database import get_db
from app.models.card import TarotCard
from app.models.card_teaching import CardTeaching
from app.models.star_learning_progress import StarLearningProgress
from app.models.user import User
from app.schemas.academy import (
    LearnedRequest,
    LearnedResponse,
    LessonCard,
    LessonResponse,
    LessonTeaching,
    MilestoneInfo,
    MyProgress,
    ReviewRequest,
    ReviewResponse,
)
from app.services.academy import apply_milestones
from app.utils.auth import get_current_user, get_optional_user

router = APIRouter(prefix="/academy", tags=["星灵学堂"])


@router.post("/learned", response_model=LearnedResponse)
async def mark_learned(
    payload: LearnedRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """点亮一颗星：记录已学 + 里程碑判定发放（幂等双保险）。"""
    card = await db.get(TarotCard, payload.card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡牌不存在")

    existing = await db.execute(
        select(StarLearningProgress).where(
            StarLearningProgress.user_id == user.id,
            StarLearningProgress.card_id == payload.card_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        # 已学：幂等返回，不重复奖励
        return LearnedResponse(
            ok=True, learned=False, review_count=row.review_count, milestone=None
        )

    # INSERT 成功（rowcount==1）才跑里程碑判定；uq_user_card 唯一约束兜底并发
    # 重复（重复 POST / 并发竞争）→ IntegrityError → 按已学幂等返回。
    try:
        result = await db.execute(
            insert(StarLearningProgress).values(
                id=str(uuid.uuid4()),
                user_id=user.id,
                card_id=payload.card_id,
                learned_at=date.today(),
                review_count=0,
            )
        )
    except IntegrityError:
        await db.rollback()
        row = (await db.execute(
            select(StarLearningProgress).where(
                StarLearningProgress.user_id == user.id,
                StarLearningProgress.card_id == payload.card_id,
            )
        )).scalar_one_or_none()
        return LearnedResponse(
            ok=True, learned=False, review_count=row.review_count if row else 0, milestone=None
        )

    if result.rowcount != 1:
        # 理论上不会到这里（唯一约束已在上面拦截），防御性按已学返回
        return LearnedResponse(ok=True, learned=False, review_count=0, milestone=None)

    # 统计已学总数 / 大阿卡纳 / 小阿卡纳（新插入行已计入）
    arcana_result = await db.execute(
        select(TarotCard.arcana)
        .join(StarLearningProgress, StarLearningProgress.card_id == TarotCard.id)
        .where(StarLearningProgress.user_id == user.id)
    )
    arcana_list = arcana_result.scalars().all()
    learned = len(arcana_list)
    major = sum(1 for a in arcana_list if a == "major")
    minor = learned - major

    granted = await apply_milestones(db, user, learned, major, minor)
    # 一次 INSERT 可能同时触发多档（如第 78 张同时达 element_court + full_78），
    # 响应只带最后一档（表序最高的里程碑，如全通庆祝），发放全部照常进行
    milestone = MilestoneInfo(**granted[-1]) if granted else None
    return LearnedResponse(ok=True, learned=True, review_count=0, milestone=milestone)


@router.get("/lesson/{card_id}", response_model=LessonResponse)
async def get_lesson(
    card_id: int,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """学习卡页：牌面 + 教学四区块（公开免登录可看牌库），登录附带 my 进度。"""
    card = await db.get(TarotCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡牌不存在")

    teaching_result = await db.execute(
        select(CardTeaching).where(CardTeaching.card_id == card_id)
    )
    teaching = teaching_result.scalar_one_or_none()
    if not teaching:
        raise HTTPException(status_code=404, detail="教学数据不存在")

    my = None
    if user:
        progress_result = await db.execute(
            select(StarLearningProgress).where(
                StarLearningProgress.user_id == user.id,
                StarLearningProgress.card_id == card_id,
            )
        )
        progress = progress_result.scalar_one_or_none()
        if progress:
            my = MyProgress(learned=True, review_count=progress.review_count)

    return LessonResponse(
        card=LessonCard(
            id=card.id,
            name_zh=card.name_zh,
            arcana=card.arcana,
            suit=card.suit,
            card_number=card.card_number,
            image_url=card_image_url(card),
        ),
        teaching=LessonTeaching(
            symbols=json.loads(teaching.symbols),
            story=teaching.story,
            keywords_learning=json.loads(teaching.keywords_learning),
            life_connection=teaching.life_connection,
            element_association=teaching.element_association,
        ),
        my=my,
    )


@router.post("/review", response_model=ReviewResponse)
async def review_card(
    payload: ReviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """复习计数 +1（仅计数不设奖励防刷）。"""
    card = await db.get(TarotCard, payload.card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡牌不存在")

    progress_result = await db.execute(
        select(StarLearningProgress).where(
            StarLearningProgress.user_id == user.id,
            StarLearningProgress.card_id == payload.card_id,
        )
    )
    progress = progress_result.scalar_one_or_none()
    if not progress:
        # 未学先复习会绕过里程碑发放（学到已学但无奖励），直接拒绝
        raise HTTPException(status_code=404, detail="尚未学习该卡牌，无法复习")

    progress.review_count = (progress.review_count or 0) + 1
    return ReviewResponse(ok=True, review_count=progress.review_count)
