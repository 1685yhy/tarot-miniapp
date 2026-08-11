"""星光手账 API —— T1-1 月历聚合 + T1-2 月度复盘。

数据源复用 ``diary_entries``（6 档情绪，唯一情绪数据源）；
star_color 由 ``build_today_guidance(date, user.zodiac)`` 确定性生成，不落库。

T1-2 月度复盘：缓存命中即返回（不消耗 AI 配额）；未命中聚合当月日记/卡牌/
新满月天象 → DeepSeek 生成并落缓存；非会员与 /diary/review 共享
FREE_DIARY_AI_DAILY 配额（生成时 +1）。
"""

import json
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.card import TarotCard
from app.models.diary import DiaryEntry
from app.models.star_monthly_review import StarMonthlyReview
from app.models.user import User
from app.schemas.journal import (
    MONTH_PATTERN,
    JournalCalendarResponse,
    JournalCardBrief,
    JournalEntryCreate,
    JournalEntryResponse,
    JournalReviewRegenerateRequest,
    JournalReviewResponse,
    JournalSharePreviewResponse,
)
from app.services.diary_entries import upsert_diary_entry
from app.services.energy_engine import build_today_guidance
from app.services.journal import (
    aggregate_month,
    brightness_for,
    build_monthly_review,
    current_streak_for,
    journal_days_for,
    maybe_grant_streak_reward,
    month_stats,
)
from app.utils.auth import get_current_user
from app.utils.quota import reset_ai_quota_if_new_day

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journal", tags=["星光手账"])

_QUOTA_DETAIL = "今日 AI 日记次数已用完，请开通会员或明日再来"


async def _streak_prior_dates(
    db: AsyncSession, user_id: str, month_start: date
) -> set[date]:
    """跨月连续回扫：月初之前、紧接月初的连续记录日期集（供 current_streak 补数据）。

    只取“以 month_start-1 结尾的最长连续段”，断档即止——更早的记录与当月
    不可能连续，直接舍弃。仅投影 entry_date（轻量），结果交给 ``month_stats``
    并入 current_streak 计算，保持 ``current_streak`` 纯函数语义不变。
    """
    expected = month_start - timedelta(days=1)
    result = await db.execute(
        select(DiaryEntry.entry_date)
        .where(
            DiaryEntry.user_id == user_id,
            DiaryEntry.entry_date < month_start,
        )
        .order_by(DiaryEntry.entry_date.desc())
    )
    prior: set[date] = set()
    for entry_date in result.scalars():
        if entry_date == expected:
            prior.add(entry_date)
            expected -= timedelta(days=1)
        elif entry_date < expected:
            break  # 断档：更早的记录与当月不再连续
    return prior


@router.get("/calendar", response_model=JournalCalendarResponse)
async def calendar(
    year: int = Query(..., ge=2000, le=2100, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份（1-12）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """某月星光手账：每日星点（情绪/亮度/星光色/卡牌/有无感悟）+ 月度统计。

    - ``days``：当月有记录的天（按日期升序），未记录天由前端按自然日补空
    - ``bright_count``：亮度 ≥ 4（满溢/明亮），``dim_count``：亮度 ≤ 2（微暗/隐没）
    - ``current_streak``：以今天为锚点的连续记录天然日数（跨月连续算连续）
    """
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    result = await db.execute(
        select(DiaryEntry)
        .where(
            DiaryEntry.user_id == user.id,
            DiaryEntry.entry_date >= start,
            DiaryEntry.entry_date < end,
        )
        .order_by(DiaryEntry.entry_date.asc())
    )
    entries = result.scalars().all()
    days = journal_days_for(entries, user.zodiac)
    # 跨月连续回扫：7-31→8-11 这类月初前连续记录需并入 streak，否则月初被截断
    prior_dates = await _streak_prior_dates(db, user.id, start)
    stats = month_stats(days, date.today(), prior_dates=prior_dates)
    return JournalCalendarResponse(days=days, stats=stats)


# ═══════════════════════════════════════════════════════════════════════
# T1-3 · POST /journal/entries 手账记录 + 连续 7 天星尘奖励（ISO 周幂等）
# ═══════════════════════════════════════════════════════════════════════


@router.post("/entries", response_model=JournalEntryResponse)
async def create_journal_entry(
    body: JournalEntryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """记录/更新今日星点；连续记录 ≥7 天 → +1 星尘（同周只发一次）。

    - 与 /diary/entries 共用 ``upsert_diary_entry``：同日已存在则更新（不新建）
    - mood 必填（6 档枚举，非法 422）；card_id 缺省随机取一张
    - 奖励幂等：``user.journal_streak_reward_week`` 记录发放周 ISO 周键，
      同周再次达标不重复发放；星尘/星阶写入与签到模式一致
    """
    entry = await upsert_diary_entry(
        db, user, body.mood, reflection=body.reflection, card_id=body.card_id,
    )
    today = entry.entry_date

    card = None
    if entry.card_id:
        card_result = await db.execute(
            select(TarotCard).where(TarotCard.id == entry.card_id)
        )
        card = card_result.scalar_one_or_none()

    streak = await current_streak_for(db, user.id, today)
    reward = maybe_grant_streak_reward(user, streak, today)

    return JournalEntryResponse(
        id=entry.id,
        date=today.isoformat(),
        mood=entry.mood,
        brightness=brightness_for(entry.mood),
        star_color=build_today_guidance(today, user.zodiac)["star_color"],
        card=JournalCardBrief(
            id=card.id,
            name_zh=card.name_zh,
            meaning_upright=card.meaning_upright[:200],
        ) if card else None,
        reflection=entry.reflection,
        streak=streak,
        reward=reward,
    )


# ═══════════════════════════════════════════════════════════════════════
# T1-2 · 月度星光复盘（AI 生成 + 缓存 + 降级模板 + 配额共享）
# ═══════════════════════════════════════════════════════════════════════


async def _load_cached_review(db: AsyncSession, user_id: str, month: str) -> dict | None:
    """读当月缓存（data JSON）；无缓存或损坏返回 None。"""
    result = await db.execute(
        select(StarMonthlyReview).where(
            StarMonthlyReview.user_id == user_id,
            StarMonthlyReview.month == month,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    try:
        data = json.loads(row.data)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def _save_cached_review(
    db: AsyncSession, user_id: str, month: str, data: dict
) -> None:
    """写入/覆盖当月缓存（upsert，幂等）。"""
    result = await db.execute(
        select(StarMonthlyReview).where(
            StarMonthlyReview.user_id == user_id,
            StarMonthlyReview.month == month,
        )
    )
    row = result.scalar_one_or_none()
    payload = json.dumps(data, ensure_ascii=False)
    if row:
        row.data = payload
    else:
        db.add(StarMonthlyReview(user_id=user_id, month=month, data=payload))


async def _delete_cached_review(
    db: AsyncSession, user_id: str, month: str
) -> None:
    """删除当月缓存（regenerate 撞上空月时清掉旧缓存，避免脏命中）。"""
    result = await db.execute(
        select(StarMonthlyReview).where(
            StarMonthlyReview.user_id == user_id,
            StarMonthlyReview.month == month,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)


def _to_review_response(data: dict, cached: bool) -> JournalReviewResponse:
    """生成态 dict → 响应模型（丢弃内部 source 标记）。"""
    return JournalReviewResponse(
        month=data["month"],
        stats=data["stats"],
        mood_series=data["mood_series"],
        star_color_counts=data["star_color_counts"],
        top_cards=data["top_cards"],
        trend_summary=data["trend_summary"],
        insight=data.get("insight"),
        next_guide=data.get("next_guide"),
        cached=cached,
    )


def _enforce_free_quota(user: User) -> None:
    """非会员免费配额检查（与 /diary/review 同款 402 语义）。"""
    if not user.is_member:
        reset_ai_quota_if_new_day(user)
        if user.diary_ai_count_today >= settings.FREE_DIARY_AI_DAILY:
            raise HTTPException(status_code=402, detail=_QUOTA_DETAIL)


@router.get("/review", response_model=JournalReviewResponse)
async def monthly_review(
    month: str = Query(..., pattern=MONTH_PATTERN, description="月份 'YYYY-MM'"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """月度星光复盘：缓存命中即返回（不消耗 AI 配额）；未命中聚合当月日记/
    卡牌/新满月天象 → AI 生成（trend_summary/insight/next_guide）→ 落缓存。

    非会员生成时 ``diary_ai_count_today + 1``（与 /diary/review 共享配额）；
    空月返回友好文案，不发 AI、不落缓存、不耗配额。
    """
    # 1) 缓存命中即返回（先于配额检查：已生成的复盘应随时可看）
    cached = await _load_cached_review(db, user.id, month)
    if cached is not None:
        return _to_review_response(cached, cached=True)

    # 2) 非会员配额检查（与 /diary/review 同款）
    _enforce_free_quota(user)

    # 3) 生成（含 AI 调用与降级）
    data = await build_monthly_review(db, user.id, user.zodiac, month)

    # 4) 空月不落缓存、不耗配额
    if data["stats"]["days_recorded"] == 0:
        return _to_review_response(data, cached=False)

    # 5) 非会员生成计配额（AI 成功/降级都算一次，与 /diary/review 一致）
    if not user.is_member:
        user.diary_ai_count_today += 1

    # 6) 落缓存（含降级结果，source=fallback）
    await _save_cached_review(db, user.id, month, data)
    return _to_review_response(data, cached=False)


@router.post("/review/regenerate", response_model=JournalReviewResponse)
async def regenerate_review(
    body: JournalReviewRegenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动重新生成月度复盘：覆盖当月缓存；非会员同受 FREE_DIARY_AI_DAILY 配额。"""
    _enforce_free_quota(user)

    data = await build_monthly_review(db, user.id, user.zodiac, body.month)

    if data["stats"]["days_recorded"] == 0:
        # 空月：清掉旧缓存，避免过期缓存被命中
        await _delete_cached_review(db, user.id, body.month)
        return _to_review_response(data, cached=False)

    if not user.is_member:
        user.diary_ai_count_today += 1

    await _save_cached_review(db, user.id, body.month, data)
    return _to_review_response(data, cached=False)


@router.get("/review/share-preview", response_model=JournalSharePreviewResponse)
async def review_share_preview(
    month: str = Query(..., pattern=MONTH_PATTERN, description="月份 'YYYY-MM'"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分享海报数据（脱敏：无昵称、无日记原文、无 user_id）。

    summary 取当月缓存中的 AI/降级摘要；无缓存时只回本地统计（summary 为空），
    不触发 AI、不消耗配额。
    """
    cached = await _load_cached_review(db, user.id, month)
    if cached is not None:
        return JournalSharePreviewResponse(
            month=month,
            stats=cached["stats"],
            star_color_counts=cached["star_color_counts"],
            summary=cached.get("trend_summary", ""),
        )

    agg = await aggregate_month(db, user.id, user.zodiac, month)
    return JournalSharePreviewResponse(
        month=month,
        stats=agg["stats"],
        star_color_counts=agg["star_color_counts"],
        summary="",
    )
