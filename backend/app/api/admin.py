"""
Admin dashboard routes for Starlight Tarot.

All routes live under the /admin prefix and require the
``X-Admin-User-Id`` header to match one of ``SUPER_ADMIN_IDS``.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models.card import TarotCard
from app.models.reading import Reading
from app.models.order import Order
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["管理后台"])

templates = Jinja2Templates(directory="app/templates")

# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def require_admin(
    request: Request,
    x_admin_user_id: Optional[str] = Header(None, alias="x-admin-user-id"),
    db: AsyncSession = Depends(get_db),
):
    """Check that the caller is a recognised super-admin."""
    if not x_admin_user_id or x_admin_user_id not in settings.SUPER_ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden: not a super-admin")
    result = await db.execute(select(User).where(User.id == x_admin_user_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden: admin user not found")
    return admin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_start() -> datetime:
    """Midnight UTC today (naive)."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day)


def _days_ago(n: int) -> datetime:
    """Midnight UTC *n* days ago."""
    start = _today_start()
    return start - timedelta(days=n)


# ---------------------------------------------------------------------------
# GET /admin — Dashboard
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    today = _today_start()
    # DAU (users who created a reading today)
    dau_result = await db.execute(
        select(func.count(func.distinct(Reading.user_id)))
        .where(Reading.created_at >= today)
    )
    dau = dau_result.scalar() or 0

    # Revenue (paid orders today)
    rev_result = await db.execute(
        select(func.coalesce(func.sum(Order.amount), 0))
        .where(
            Order.status == "paid",
            Order.paid_at >= today,
        )
    )
    revenue = float(rev_result.scalar() or 0)

    # AI calls (readings today)
    ai_result = await db.execute(
        select(func.count(Reading.id))
        .where(Reading.created_at >= today)
    )
    ai_calls = ai_result.scalar() or 0

    # Conversion rate (paid / total readings today)
    paid_result = await db.execute(
        select(func.count(Reading.id))
        .where(
            Reading.is_paid == True,  # noqa: E712
            Reading.created_at >= today,
        )
    )
    paid = paid_result.scalar() or 0
    conversion_rate = round((paid / ai_calls * 100), 1) if ai_calls else 0.0

    # Total users
    users_result = await db.execute(select(func.count(User.id)))
    total_users = users_result.scalar() or 0

    # Total orders (lifetime)
    total_orders_result = await db.execute(select(func.count(Order.id)))
    total_orders = total_orders_result.scalar() or 0

    # 7-day trend: readings per day
    trend = []
    for i in range(6, -1, -1):
        day_start = _days_ago(i)
        day_end = _days_ago(i - 1)
        cnt = await db.execute(
            select(func.count(Reading.id))
            .where(
                Reading.created_at >= day_start,
                Reading.created_at < day_end,
            )
        )
        trend.append(cnt.scalar() or 0)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "admin": admin,
            "dau": dau,
            "revenue": revenue,
            "ai_calls": ai_calls,
            "conversion_rate": conversion_rate,
            "total_users": total_users,
            "total_orders": total_orders,
            "trend": trend,
            "days": [(_days_ago(6 - i)).strftime("%m/%d") for i in range(7)],
        },
    )


# ---------------------------------------------------------------------------
# GET /admin/users — User list
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse, include_in_schema=False)
async def admin_users(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    search: str = Query("", max_length=64),
    membership: str = Query("", pattern="^(all|member|non-member)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(User)
    count_query = select(func.count(User.id))

    if search:
        pattern = f"%{search}%"
        query = query.where(
            User.nickname.ilike(pattern) | User.openid.ilike(pattern)
        )
        count_query = count_query.where(
            User.nickname.ilike(pattern) | User.openid.ilike(pattern)
        )

    if membership == "member":
        query = query.where(User.is_member == True)  # noqa: E712
        count_query = count_query.where(User.is_member == True)  # noqa: E712
    elif membership == "non-member":
        query = query.where(User.is_member == False)  # noqa: E712
        count_query = count_query.where(User.is_member == False)  # noqa: E712

    total = (await db.execute(count_query)).scalar() or 0
    total_pages = max(1, (total + per_page - 1) // per_page)

    query = (
        query
        .order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(query)).scalars().all()

    # Enrich with reading count per user
    users_data = []
    for u in rows:
        cnt = await db.execute(
            select(func.count(Reading.id)).where(Reading.user_id == u.id)
        )
        users_data.append({
            "id": u.id,
            "nickname": u.nickname or "(unnamed)",
            "openid": u.openid,
            "is_member": u.is_member,
            "member_expires_at": u.member_expires_at,
            "reading_count": cnt.scalar() or 0,
            "created_at": u.created_at,
        })

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "admin": admin,
            "users": users_data,
            "search": search,
            "membership": membership,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


# ---------------------------------------------------------------------------
# GET /admin/readings — Reading records
# ---------------------------------------------------------------------------

@router.get("/readings", response_class=HTMLResponse, include_in_schema=False)
async def admin_readings(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    count_q = select(func.count(Reading.id))
    total = (await db.execute(count_q)).scalar() or 0
    total_pages = max(1, (total + per_page - 1) // per_page)

    query = (
        select(Reading)
        .options(selectinload(Reading.user))
        .order_by(Reading.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(query)).scalars().all()

    # Prepend a short AI-quality preview (first 120 chars of interpretation)
    readings_data = []
    for r in rows:
        preview = (r.interpretation or "")[:120]
        if r.interpretation and len(r.interpretation) > 120:
            preview += "…"
        readings_data.append({
            "id": r.id,
            "user_nickname": r.user.nickname if r.user else "(deleted)",
            "user_id": r.user_id,
            "spread_type": r.spread_type,
            "theme": r.theme or "-",
            "persona": r.persona or "-",
            "is_paid": r.is_paid,
            "preview": preview or "(no interpretation)",
            "created_at": r.created_at,
        })

    return templates.TemplateResponse(
        "admin/readings.html",
        {
            "request": request,
            "admin": admin,
            "readings": readings_data,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


# ---------------------------------------------------------------------------
# GET /admin/orders — Order history
# ---------------------------------------------------------------------------

@router.get("/orders", response_class=HTMLResponse, include_in_schema=False)
async def admin_orders(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    # Revenue summary
    rev_result = await db.execute(
        select(
            func.coalesce(func.sum(Order.amount), 0).label("total_revenue"),
            func.count(Order.id).label("total_orders"),
            func.sum(case((Order.status == "paid", 1), else_=0)).label("paid_count"),
        )
    )
    rev = rev_result.one()
    total_revenue = float(rev.total_revenue) if rev.total_revenue else 0.0
    total_orders = rev.total_orders or 0
    paid_count = rev.paid_count or 0

    count_q = select(func.count(Order.id))
    total = (await db.execute(count_q)).scalar() or 0
    total_pages = max(1, (total + per_page - 1) // per_page)

    query = (
        select(Order)
        .options(selectinload(Order.user))
        .order_by(Order.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(query)).scalars().all()

    orders_data = []
    for o in rows:
        orders_data.append({
            "id": o.id,
            "order_no": o.order_no,
            "user_nickname": o.user.nickname if o.user else "(deleted)",
            "product_type": o.product_type,
            "amount": float(o.amount),
            "status": o.status,
            "paid_at": o.paid_at,
            "created_at": o.created_at,
        })

    return templates.TemplateResponse(
        "admin/orders.html",
        {
            "request": request,
            "admin": admin,
            "orders": orders_data,
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "paid_count": paid_count,
            "page": page,
            "total_pages": total_pages,
        },
    )


# ---------------------------------------------------------------------------
# GET /admin/content — Card content management (simple CMS)
# ---------------------------------------------------------------------------

@router.get("/content", response_class=HTMLResponse, include_in_schema=False)
async def admin_content(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    arcana: str = Query("", pattern="^(all|major|minor)$"),
):
    query = select(TarotCard)
    count_q = select(func.count(TarotCard.id))

    if arcana == "major":
        query = query.where(TarotCard.arcana == "major")
        count_q = count_q.where(TarotCard.arcana == "major")
    elif arcana == "minor":
        query = query.where(TarotCard.arcana == "minor")
        count_q = count_q.where(TarotCard.arcana == "minor")

    total = (await db.execute(count_q)).scalar() or 0
    total_pages = max(1, (total + per_page - 1) // per_page)

    query = (
        query
        .order_by(TarotCard.card_number.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(query)).scalars().all()

    cards_data = []
    for c in rows:
        cards_data.append({
            "id": c.id,
            "name_zh": c.name_zh,
            "name_en": c.name_en,
            "card_number": c.card_number,
            "arcana": c.arcana,
            "suit": c.suit or "-",
            "element": c.element or "-",
            "keywords_upright": c.keywords_upright[:80] + "…" if len(c.keywords_upright) > 80 else c.keywords_upright,
            "meaning_upright": c.meaning_upright[:80] + "…" if len(c.meaning_upright) > 80 else c.meaning_upright,
            "meaning_reversed": c.meaning_reversed[:80] + "…" if len(c.meaning_reversed) > 80 else c.meaning_reversed,
        })

    return templates.TemplateResponse(
        "admin/content.html",
        {
            "request": request,
            "admin": admin,
            "cards": cards_data,
            "arcana": arcana,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


# ---------------------------------------------------------------------------
# POST /admin/content/{card_id} — Update card content (AJAX)
# ---------------------------------------------------------------------------

@router.post("/content/{card_id:int}", include_in_schema=False)
async def admin_update_card(
    request: Request,
    card_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    result = await db.execute(select(TarotCard).where(TarotCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    updatable_fields = {
        "name_zh", "name_en", "keywords_upright", "keywords_reversed",
        "meaning_upright", "meaning_reversed", "image_description",
        "love_upright", "love_reversed", "career_upright", "career_reversed",
        "finance_upright", "finance_reversed", "health_upright", "health_reversed",
    }
    for field in updatable_fields:
        if field in data:
            setattr(card, field, str(data[field]))
    await db.flush()
    return {"ok": True, "card_id": card_id}
