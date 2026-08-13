"""
星灵学堂 API（SDD P2 阶段3 · T6-1/2）

- POST /academy/learned — 点亮一颗星（学一张牌）：INSERT 成功（rowcount==1）
  才跑里程碑判定（幂等锚：uq_user_card 唯一约束 + 里程碑账本双保险）；
  重复已学 → learned=false 不重复奖励；card_id 非法 → 404
- GET  /academy/lesson/{card_id} — 学习卡页（公开免登录可看牌库；登录附带
  my 进度）；teaching 直接读 card_teaching 表
- POST /academy/review — 复习计数 +1（仅计数不设奖励防刷）
- GET/POST /academy/plan — 学习计划读写（T6-2）：1 用户 1 条；无行默认
  {0, false, "major", 0}；非法值 422；reminder_on=true 无订阅额度 →
  quota_warning=true 仅引导授权不硬拦（学习提醒默认关闭）
- GET  /academy/lesson/next?path=&pos= — 路径内下一张（T6-2）：major/minor
  游标推进、random 按日确定性（pick_daily_card 同牌）、related 历史抽牌
  频次 TOP 未学；推进写回 plans.cursor_pos（upsert）
- GET  /academy/overview — 学堂主页（T6-2）：总进度 + 四路径 + 称号 + today_card
"""

import json
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.horoscope import card_image_url
from app.db.database import get_db
from app.models.card import TarotCard
from app.models.card_teaching import CardTeaching
from app.models.star_learning_plan import StarLearningPlan
from app.models.star_learning_progress import StarLearningProgress
from app.models.subscribe_quota import SubscribeQuota
from app.models.user import User
from app.schemas.academy import (
    LearnedRequest,
    LearnedResponse,
    LessonCard,
    LessonResponse,
    LessonTeaching,
    MilestoneInfo,
    MyProgress,
    NextLessonResponse,
    OverviewResponse,
    PathsStats,
    PathStat,
    PlanRequest,
    PlanResponse,
    PlanSetResponse,
    ReviewRequest,
    ReviewResponse,
    TodayCard,
)
from app.services.academy import (
    DECK_SIZE,
    MAJOR_SIZE,
    MINOR_SIZE,
    PATH_REASONS,
    apply_milestones,
    major_cards,
    minor_cards,
    next_card,
    related_next_card,
    titles_of,
)
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


@router.get("/lesson/next", response_model=NextLessonResponse)
async def next_lesson(
    path: Literal["major", "minor", "random", "related"] = Query("major"),
    pos: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """路径内下一张牌，推进写回 plans.cursor_pos（upsert，前端无状态轮询）。

    注意：本路由必须声明在 /lesson/{card_id} 之前（静态段优先匹配，
    否则 "next" 会被当作 card_id 解析报 422 int_parsing）。

    - major/minor：游标推进，越界 → done=true 循环回 0
    - random：pick_daily_card 同款确定性（同日同人恒定），忽略游标
    - related：历史抽牌频次 TOP 的未学牌；全部已学 → done=true 循环回 0
    """
    cards_result = await db.execute(select(TarotCard).order_by(TarotCard.id))
    all_cards = list(cards_result.scalars().all())
    if not all_cards:
        raise HTTPException(status_code=500, detail="卡牌数据为空")
    major = major_cards(all_cards)
    minor = minor_cards(all_cards)

    if path == "related":
        card = await related_next_card(db, user.id, all_cards)
        next_pos, done = pos, False  # related 忽略游标（cursor 派生自历史频次）
        if card is None:
            card, next_pos, done = major[0], 0, True  # 全部已学 → 完成态循环回 0
    else:
        card, next_pos, done = next_card(path, pos, major, minor, user.id, date.today())

    # upsert：新行才写 path；既有行只推进 cursor_pos（读多写少端点不得覆写
    # 用户已存计划路径——否则缺省 path=major 的调用会把 random/related 计划
    # 静默改成 major，GET /plan 与 overview.today_card 都会漂移）
    plan = await db.get(StarLearningPlan, user.id)
    if plan:
        plan.cursor_pos = next_pos
    else:
        db.add(StarLearningPlan(user_id=user.id, path=path, cursor_pos=next_pos))
    await db.commit()

    return NextLessonResponse(
        card_id=card.id, name_zh=card.name_zh, path=path, next_pos=next_pos, done=done
    )


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


# ── T6-2 学习计划 / 下一张 / 学堂概览 ───────────────────────────────────


@router.get("/plan", response_model=PlanResponse)
async def get_plan(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """学习计划读取（无行 → 默认 {0, false, "major", 0}）。"""
    plan = await db.get(StarLearningPlan, user.id)
    if not plan:
        return PlanResponse(cards_per_day=0, reminder_on=False, path="major", cursor_pos=0)
    return PlanResponse(
        cards_per_day=plan.cards_per_day,
        reminder_on=plan.reminder_on,
        path=plan.path,
        cursor_pos=plan.cursor_pos,
    )


@router.post("/plan", response_model=PlanSetResponse)
async def set_plan(
    payload: PlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """学习计划写入：非法 cards_per_day/path 由 Literal 校验 422。

    reminder_on=true 时校验订阅额度（quota_available>0 或 last_sent_date 有值
    视为已授权）；无额度 → 200 + quota_warning=true 引导授权，不硬拦。
    """
    quota_warning = False
    if payload.reminder_on:
        quota = await db.get(SubscribeQuota, user.id)
        authorized = quota is not None and (
            quota.quota_available > 0 or quota.last_sent_date is not None
        )
        quota_warning = not authorized

    plan = await db.get(StarLearningPlan, user.id)
    if plan:
        plan.cards_per_day = payload.cards_per_day
        plan.reminder_on = payload.reminder_on
        plan.path = payload.path
    else:
        plan = StarLearningPlan(
            user_id=user.id,
            cards_per_day=payload.cards_per_day,
            reminder_on=payload.reminder_on,
            path=payload.path,
        )
        db.add(plan)
    await db.commit()
    return PlanSetResponse(
        cards_per_day=payload.cards_per_day,
        reminder_on=payload.reminder_on,
        path=payload.path,
        cursor_pos=plan.cursor_pos,
        quota_warning=quota_warning,
    )


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """学堂主页：总进度 + 四路径进度 + 已获称号 + 今日学习卡（random 按日确定性）。"""
    cards_result = await db.execute(select(TarotCard).order_by(TarotCard.id))
    all_cards = list(cards_result.scalars().all())
    if not all_cards:
        raise HTTPException(status_code=500, detail="卡牌数据为空")
    major = major_cards(all_cards)
    minor = minor_cards(all_cards)

    progress_rows = (
        await db.execute(
            select(StarLearningProgress.card_id, TarotCard.arcana)
            .join(TarotCard, TarotCard.id == StarLearningProgress.card_id)
            .where(StarLearningProgress.user_id == user.id)
        )
    ).all()
    learned = len(progress_rows)
    major_learned = sum(1 for _, arcana in progress_rows if arcana == "major")
    minor_learned = learned - major_learned
    percent = round(learned * 100 / DECK_SIZE) if learned else 0

    plan = await db.get(StarLearningPlan, user.id)
    today_card = None
    if plan:
        if plan.path == "related":
            card = await related_next_card(db, user.id, all_cards)
            if card is None:
                card = major[0]  # 全部已学 → 完成态（与 lesson/next 口径一致）
        else:
            card, _, _ = next_card(plan.path, plan.cursor_pos, major, minor, user.id, date.today())
        today_card = TodayCard(
            card_id=card.id, name_zh=card.name_zh, reason=PATH_REASONS[plan.path]
        )

    return OverviewResponse(
        total=DECK_SIZE,
        learned=learned,
        percent=percent,
        paths=PathsStats(
            major=PathStat(learned=major_learned, total=MAJOR_SIZE),
            minor=PathStat(learned=minor_learned, total=MINOR_SIZE),
            random=PathStat(learned=learned),
            related=PathStat(learned=learned),
        ),
        titles=titles_of(user),
        today_card=today_card,
    )
