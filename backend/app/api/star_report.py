"""星象月报 API（SDD P2 · T7-1 周报 + T7-2 月报 + T7-3 解锁权益 + T7-4 海报）。

GET /report/week?period=2026-W33 —— 周报：
- 会员/解锁 → 全文；非会员未解锁 → 预览版（curve + 1 段寄语）+ locked=true
- period 缺省 = 上一完整周（last_completed_week(beijing_today())）
- 缓存命中零 AI；force=1 覆盖缓存重新生成
- 空态周 → 统计 0 + 温柔引导（不报错）

GET /report/month?period=2026-08 —— 月报：
- 会员/解锁 → 全文；非会员未解锁 → 预览版（天象目录 + 1 段总评）+ locked=true
- period 缺省 = 上一完整月（last_completed_month(beijing_today())，每月 1 日后可看上月）
- 手账段直接引用 star_monthly_reviews 缓存（零新增 AI）；展望段只预告真实天象
- 空态月 → 统计 0 + 温柔引导（不报错）

POST /report/{type}/unlock —— T7-3 解锁下单：
- type 只接受 week|month（非法 → 404）；会员/已解锁 → 400「你已拥有这份星光 ✦」
- 复用 orders/fulfillment 管线（PRODUCTS weekly_report 4.9 / monthly_report 19.9，
  type=single_purchase），支付回调置对应 BOOL 列；重复下单/回调幂等

POST /report/{type}/regenerate —— T7-3 会员重生成：
- 仅会员（403）；限流周/月各 1 次/周期（内存 dict，注释见下）
- AI 失败 → 回退原缓存不覆盖（返回原报告，source 不变）
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.schemas.order import CreateOrderResponse
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
    regenerate_month_report,
    regenerate_week_report,
    week_bounds,
)
from app.utils.auth import get_current_user, utc_aware

router = APIRouter(prefix="/report", tags=["星象月报"])

# ── regenerate 限流（周/月各 1 次/周期）──
# 简单方案：进程内 dict，key = f"{user_id}:{report_type}:{period}"，value = period。
# 注：单实例部署下即用即生效；多实例部署需换共享存储（如 Redis），
# 或改存 star_reports.updated_at（重生成会更新时间戳，同一周期限 1 次即可）。
_REGEN_USED: dict[str, str] = {}

def is_member_active(user: User) -> bool:
    """会员实时判定（is_member 有效期内；expires_at=None 视为永续会员）。

    与 membership.py 语义一致：member_expires_at 已过期 → 不再视为会员。
    """
    if not user.is_member:
        return False
    if user.member_expires_at is None:
        return True  # 永续会员（membership_lifetime）
    return utc_aware(user.member_expires_at) > datetime.now(timezone.utc)


def can_read_full(user: User, report_type: str) -> bool:
    """全文权益：会员 或 对应单次购买解锁列。

    会员到期后旧解锁仍有效（单次购买是永久资产，仿 annual_report_paid 语义）。
    """
    if is_member_active(user):
        return True
    if report_type == "week":
        return bool(user.weekly_report_unlocked)
    if report_type == "month":
        return bool(user.monthly_report_unlocked)
    return False


def _validate_report_type(report_type: str) -> None:
    """unlock/regenerate 的 type 参数校验（非法 → 404，按 T7-3 计划）。"""
    if report_type not in ("week", "month"):
        raise HTTPException(status_code=404, detail="未知的报告类型")


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

    locked = not can_read_full(user, "week")
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

    locked = not can_read_full(user, "month")
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


# ═══════════════════════════════════════════════════════════════════════
# T7-3：解锁下单 + regenerate 限流
# ═══════════════════════════════════════════════════════════════════════


@router.post("/{report_type}/unlock", response_model=CreateOrderResponse)
async def unlock_report(
    report_type: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """非会员解锁下单（周报 4.9 / 月报 19.9，复用 orders/fulfillment 管线）。

    会员或已解锁 → 400「你已拥有这份星光 ✦」；支付回调成功后才置解锁列，
    重复下单/回调由订单管线幂等（已 paid 订单不重复发放）。
    """
    _validate_report_type(report_type)
    if can_read_full(user, report_type):
        raise HTTPException(status_code=400, detail="你已拥有这份星光 ✦")

    from app.api.orders import create_order_for_user

    product_type = "weekly_report" if report_type == "week" else "monthly_report"
    return await create_order_for_user(db, user, product_type)


@router.post("/{report_type}/regenerate")
async def regenerate_report(
    report_type: str,
    period: str | None = Query(
        None,
        description="周期键 '2026-W33' | '2026-08'；缺省 = 上一完整周期",
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会员重生成报告（覆盖缓存）；限流 1 次/周期；AI 失败回退原缓存。

    week → 周报（period 形如 2026-W33）；month → 月报（period 形如 2026-08）。
    响应结构与对应 GET 端点一致（locked=False，仅会员可调）。
    """
    _validate_report_type(report_type)
    if not is_member_active(user):
        raise HTTPException(status_code=403, detail="仅会员可重新生成 ✦")
    if report_type == "week":
        period = period or last_completed_week(beijing_today())
        try:
            start, end = week_bounds(period)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    else:
        period = period or last_completed_month(beijing_today())
        try:
            start, end = month_bounds(period)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    key = f"{user.id}:{report_type}:{period}"
    if key in _REGEN_USED:
        raise HTTPException(status_code=429, detail="这份星光已是最新 ✦")

    if report_type == "week":
        data = await regenerate_week_report(db, user, period)
        resp = {
            "period": period,
            "week_range": [start.isoformat(), end.isoformat()],
            "report": data["report"],
            "locked": False,
            "preview": False,
            "cached": False,
            "source": data["source"],
        }
    else:
        data = await regenerate_month_report(db, user, period)
        resp = {
            "period": period,
            "month_range": [start.isoformat(), end.isoformat()],
            "report": data["report"],
            "locked": False,
            "preview": False,
            "cached": False,
            "source": data["source"],
        }
    _REGEN_USED[key] = period
    return resp
