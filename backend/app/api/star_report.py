"""星象月报 API（SDD P2 · T7-1 周报 + T7-2 月报）。

GET /report/week?period=2026-W33 —— 周报：
- 会员/解锁 → 全文；非会员 → 预览版（curve + 1 段寄语）+ locked=true
- period 缺省 = 上一完整周（last_completed_week(beijing_today())）
- 缓存命中零 AI；force=1 覆盖缓存重新生成
- 空态周 → 统计 0 + 温柔引导（不报错）

GET /report/month?period=2026-08 —— 月报：
- 会员/解锁 → 全文；非会员 → 预览版（天象目录 + 1 段总评）+ locked=true
- period 缺省 = 上一完整月（last_completed_month(beijing_today())，每月 1 日后可看上月）
- 手账段直接引用 star_monthly_reviews 缓存（零新增 AI）；展望段只预告真实天象
- 空态月 → 统计 0 + 温柔引导（不报错）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.schemas.star_report import (
    MONTH_PERIOD_PATTERN,
    WEEK_PERIOD_PATTERN,
    MonthReportResponse,
    WeekReportResponse,
)
from app.services.star_reports import (
    beijing_today,
    get_or_create_month_report,
    get_or_create_week_report,
    last_completed_month,
    last_completed_week,
    month_bounds,
    week_bounds,
)
from app.utils.auth import get_current_user

router = APIRouter(prefix="/report", tags=["星象月报"])


@router.get("/week", response_model=WeekReportResponse)
async def get_week_report(
    period: str | None = Query(
        None,
        pattern=WEEK_PERIOD_PATTERN,
        description="周周期 '2026-W33'；缺省 = 上一完整周",
    ),
    force: bool = Query(False, description="强制重新生成（覆盖缓存）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """周报（懒生成 + 按人按周期缓存；统计段纯 SQL，AI 只写寄语段）。"""
    period = period or last_completed_week(beijing_today())
    try:
        start, end = week_bounds(period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    data = await get_or_create_week_report(db, user, period, force=force)

    locked = not user.is_member
    report = data["report"]
    if locked:
        # 预览版：曲线 + 1 段寄语（解锁后无需重生成，缓存保留全文）
        report = {"curve": report["curve"], "note": report["note"]}
    return {
        "period": period,
        "week_range": [start.isoformat(), end.isoformat()],
        "report": report,
        "locked": locked,
        "preview": locked,
        "cached": data["cached"],
        "source": data["source"],
    }


@router.get("/month", response_model=MonthReportResponse)
async def get_month_report(
    period: str | None = Query(
        None,
        pattern=MONTH_PERIOD_PATTERN,
        description="月周期 '2026-08'；缺省 = 上一完整月",
    ),
    force: bool = Query(False, description="强制重新生成（覆盖缓存）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """月报（懒生成 + 按人按周期缓存；统计段纯 SQL，AI 只写总评段）。"""
    period = period or last_completed_month(beijing_today())
    try:
        start, end = month_bounds(period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    data = await get_or_create_month_report(db, user, period, force=force)

    locked = not user.is_member
    report = data["report"]
    if locked:
        # 预览版：天象目录（封面+目录）+ 1 段总评（解锁后无需重生成，缓存保留全文）
        report = {
            "astral_events": report["astral_events"],
            "note": report["note"],
        }
    return {
        "period": period,
        "month_range": [start.isoformat(), end.isoformat()],
        "report": report,
        "locked": locked,
        "preview": locked,
        "cached": data["cached"],
        "source": data["source"],
    }
