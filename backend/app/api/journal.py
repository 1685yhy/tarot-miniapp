"""星光手账 API —— T1-1 月历聚合 + 亮度映射。

数据源复用 ``diary_entries``（6 档情绪，唯一情绪数据源）；
star_color 由 ``build_today_guidance(date, user.zodiac)`` 确定性生成，不落库。
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.diary import DiaryEntry
from app.models.user import User
from app.schemas.journal import JournalCalendarResponse
from app.services.journal import journal_days_for, month_stats
from app.utils.auth import get_current_user

router = APIRouter(prefix="/journal", tags=["星光手账"])


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
    stats = month_stats(days, date.today())
    return JournalCalendarResponse(days=days, stats=stats)
