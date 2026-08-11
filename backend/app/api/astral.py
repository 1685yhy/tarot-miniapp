"""
星空时刻表（SDD P1 · T3-1）API — 星象日历 / 日详情 / 节点内容。

三端点（全部 get_current_user 鉴权，全局限流中间件覆盖）：
- GET /astral/calendar?year=&month=      月视图（每日月相小字 + 事件 + 逆行标记）
- GET /astral/events/{date}              日详情（事件 note + 宜忌 + 活动形态）
- GET /astral/event/{type}               节点打卡内容（wish/review 的 wish_counts 接 db）

业务逻辑全部在 services/astral_calendar.py（纯函数），本模块只是薄封装。
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.models.wish import Wish
from app.schemas.astral import DayDetailResponse, MonthViewResponse, NodeContentResponse
from app.services.astral_calendar import (
    DEFAULT_NODE_TYPE,
    NODE_TYPE_BY_EVENT,
    day_detail,
    month_view,
    node_content,
)
from app.services.energy_engine import ASTRAL_TYPE_FACTOR_NAME
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/astral", tags=["星空时刻表"])


async def _wish_counts(db: AsyncSession, user_id: str) -> dict[str, int]:
    """用户愿望状态计数（active/grown/answered），供 wish/review 节点使用。"""
    result = await db.execute(
        select(Wish.status, func.count(Wish.id))
        .where(Wish.user_id == user_id)
        .group_by(Wish.status)
    )
    counts = {"active": 0, "grown": 0, "answered": 0}
    for status, count in result.all():
        counts[status] = int(count)
    return counts


@router.get("/calendar", response_model=MonthViewResponse)
async def get_calendar(
    year: int = Query(..., ge=1970, le=2100, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份 1-12"),
    user: User = Depends(get_current_user),
):
    """星象月历：每日月相小字 + 天文事件（区间事件展开到每一天）+ 下一节点倒计时。"""
    return month_view(year, month, today=date.today())


@router.get("/events/{target_date}", response_model=DayDetailResponse)
async def get_day_events(
    target_date: date,
    user: User = Depends(get_current_user),
):
    """某日星象详情：事件卡片（note 文案）+ 星象宜忌 + 节点活动形态。"""
    return day_detail(target_date)


@router.get(
    "/event/{event_type}",
    response_model=NodeContentResponse,
    response_model_exclude_none=True,
)
async def get_event_node(
    event_type: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """节点打卡内容：事件类型 → 许愿之夜 / 复盘之夜 / 慢行期 / 资讯。

    wish / review 节点的 wish_counts（active/grown/answered）实时接愿望表。
    """
    if event_type not in ASTRAL_TYPE_FACTOR_NAME:
        raise HTTPException(status_code=400, detail="未知的天象事件类型")
    node_type = NODE_TYPE_BY_EVENT.get(event_type, DEFAULT_NODE_TYPE)
    wish_counts = (
        await _wish_counts(db, user.id) if node_type in ("wish", "review") else None
    )
    return node_content(node_type, date.today(), wish_counts)
