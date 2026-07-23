"""
签到 + 任务 API 端点

- POST /tasks/checkin — 每日签到
- GET  /tasks/status — 签到状态 + 等级 + 今日任务
"""

from datetime import date, timedelta, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.models.checkin import CheckIn
from app.models.reading import Reading
from app.utils.auth import get_current_user
from app.schemas.task import CheckInResponse, TaskStatusResponse, LevelInfo

router = APIRouter(prefix="/tasks", tags=["签到与任务"])

# ── 等级定义 ──────────────────────────────────────────────
LEVELS = [
    {"name": "星光旅人", "min_days": 0, "max_days": 6, "badge_color": "#9A95B8"},
    {"name": "星辰学徒", "min_days": 7, "max_days": 29, "badge_color": "#B8A9E0"},
    {"name": "月光智者", "min_days": 30, "max_days": 99, "badge_color": "#F4D48C"},
    {"name": "银河导师", "min_days": 100, "max_days": 999999, "badge_color": "#FFD700"},
]


def _resolve_level(streak: int) -> dict:
    for lv in LEVELS:
        if lv["min_days"] <= streak <= lv["max_days"]:
            return lv
    return LEVELS[-1]


def _next_level_info(streak: int) -> tuple[str, int]:
    """Return (next_level_name, days_need_to_reach_it)."""
    for lv in LEVELS:
        if streak < lv["min_days"]:
            return lv["name"], lv["min_days"] - streak
    return LEVELS[-1]["name"], 0


# ── POST /tasks/checkin ──────────────────────────────────


@router.post("/checkin", response_model=CheckInResponse)
async def checkin(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    today = date.today()

    # 1. Check if already checked in today
    existing = await db.execute(
        select(CheckIn).where(
            CheckIn.user_id == user.id,
            CheckIn.checkin_date == today,
        )
    )
    if existing.scalar_one_or_none():
        # Already signed in — return current streak
        # Get the latest checkin streak
        latest = await db.execute(
            select(CheckIn)
            .where(CheckIn.user_id == user.id)
            .order_by(CheckIn.checkin_date.desc())
            .limit(1)
        )
        last = latest.scalar_one_or_none()
        streak = last.streak_count if last else 0
        return CheckInResponse(signed_in=True, streak=streak, reward="今日已签到")

    # 2. Calculate streak
    yesterday = today - timedelta(days=1)
    prev = await db.execute(
        select(CheckIn).where(
            CheckIn.user_id == user.id,
            CheckIn.checkin_date == yesterday,
        )
    )
    prev_checkin = prev.scalar_one_or_none()
    new_streak = (prev_checkin.streak_count + 1) if prev_checkin else 1

    # 3. Create checkin record
    checkin_record = CheckIn(
        user_id=user.id,
        checkin_date=today,
        streak_count=new_streak,
    )
    db.add(checkin_record)

    # 4. Reward: +1 free reading
    reward = "+1 免费解读"
    user.free_readings_today = (user.free_readings_today or 0) + 1

    return CheckInResponse(signed_in=True, streak=new_streak, reward=reward)


# ── GET /tasks/status ────────────────────────────────────


@router.get("/status", response_model=TaskStatusResponse)
async def task_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    today = date.today()

    # 1. Check-in status
    checkin_today = await db.execute(
        select(CheckIn).where(
            CheckIn.user_id == user.id,
            CheckIn.checkin_date == today,
        )
    )
    checked_in_today = checkin_today.scalar_one_or_none() is not None

    # 2. Current streak (from most recent checkin)
    latest = await db.execute(
        select(CheckIn)
        .where(CheckIn.user_id == user.id)
        .order_by(CheckIn.checkin_date.desc())
        .limit(1)
    )
    last = latest.scalar_one_or_none()
    streak = last.streak_count if last else 0

    # 3. Level
    current_lv = _resolve_level(streak)
    next_name, need_days = _next_level_info(streak)
    level_info = LevelInfo(
        current_level=current_lv["name"],
        next_level=next_name,
        days_needed=need_days,
        progress=need_days if need_days > 0 else 0,
    )

    # 4. Daily card drawn today
    today_start = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=timezone.utc)
    today_end = datetime(today.year, today.month, today.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    daily_card_result = await db.execute(
        select(func.count(Reading.id)).where(
            Reading.user_id == user.id,
            Reading.spread_type == "daily",
            Reading.created_at >= today_start,
            Reading.created_at <= today_end,
        )
    )
    daily_card_drawn = daily_card_result.scalar() > 0

    # 5. Any reading done today (not daily — that's separate)
    reading_result = await db.execute(
        select(func.count(Reading.id)).where(
            Reading.user_id == user.id,
            Reading.spread_type != "daily",
            Reading.created_at >= today_start,
            Reading.created_at <= today_end,
        )
    )
    reading_done_today = reading_result.scalar() > 0

    # 6. Shared today (from app storage — we'll check via share_log if it exists)
    #    We reuse the ShareLog model if it tracks per-user shares
    from app.models.share_log import ShareLog
    share_result = await db.execute(
        select(func.count(ShareLog.id)).where(
            ShareLog.sharer_id == user.id,
            ShareLog.created_at >= today_start,
            ShareLog.created_at <= today_end,
        )
    )
    shared_today = share_result.scalar() > 0

    # Total tasks
    tasks = [daily_card_drawn, reading_done_today, shared_today]
    tasks_completed = sum(1 for t in tasks if t)

    return TaskStatusResponse(
        checked_in_today=checked_in_today,
        streak=streak,
        level=level_info,
        daily_card_drawn=daily_card_drawn,
        reading_done_today=reading_done_today,
        shared_today=shared_today,
        tasks_completed=tasks_completed,
        tasks_total=3,
    )
