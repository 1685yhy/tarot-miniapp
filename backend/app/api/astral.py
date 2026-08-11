"""
星空时刻表（SDD P1 · T3-1）API — 星象日历 / 日详情 / 节点内容 / 节点打卡。

五端点（全部 get_current_user 鉴权，全局限流中间件覆盖）：
- GET  /astral/calendar?year=&month=      月视图（每日月相小字 + 事件 + 逆行标记）
- GET  /astral/events/{date}              日详情（事件 note + 宜忌 + 活动形态）
- GET  /astral/event/{type}               节点打卡内容（wish/review 的 wish_counts 接 db）
- POST /astral/activity                   节点打卡：事件当天 +1 星尘（幂等，T3-3）
- GET  /astral/activity/summary?month=    某月打卡汇总（我的页星阶区，T3-3）

业务逻辑全部在 services/astral_calendar.py（纯函数），本模块只是薄封装。
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.astral_activity_log import AstralActivityLog
from app.models.user import User
from app.models.wish import Wish
from app.schemas.astral import (
    ActivityCheckInRequest,
    ActivityCheckInResponse,
    ActivitySummaryResponse,
    DayDetailResponse,
    MonthViewResponse,
    NodeContentResponse,
)
from app.services.astral_calendar import (
    DEFAULT_NODE_TYPE,
    NODE_TYPE_BY_EVENT,
    day_detail,
    month_view,
    node_content,
)
from app.services.energy_engine import ASTRAL_TYPE_FACTOR_NAME, astral_events_on
from app.services.stardust import tier_for
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/astral", tags=["星空时刻表"])

# 节点活动形态 → 所需天象事件类型（T3-3 打卡「事件当天」判定依据）
ACTIVITY_TO_EVENT_TYPE = {v: k for k, v in NODE_TYPE_BY_EVENT.items()}
# {"wish": "new_moon", "review": "full_moon", "mercury_guide": "mercury_retrograde"}
VALID_ACTIVITY_KEYS = frozenset(ACTIVITY_TO_EVENT_TYPE)


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


# ── 节点活动打卡（SDD P1 · T3-3）：事件当天 +1 星尘，幂等 ───────────────


def _event_type_from_key(event_key: str) -> str:
    """从落库 event_key（{事件类型}-{YYYY-MM-DD}）还原事件类型。

    日期部分含 2 个连字符（YYYY-MM-DD），从右拆 3 段后剩余即事件类型。
    """
    return event_key.rsplit("-", 3)[0]


@router.post("/activity", response_model=ActivityCheckInResponse)
async def check_in_activity(
    payload: ActivityCheckInRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """节点打卡：事件当天首次 +1 星尘，star_tier 随 tier_for 同步。

    - event_key 仅限 wish | review | mercury_guide（非法 400）
    - 仅允许在对应天象事件当天打卡（astral_events_on 判定，非节点日 400）
    - 落库 event_key = {事件类型}-{日期}（如 new_moon-2026-08-12），
      UNIQUE(user_id, event_key, event_date) 幂等：重复 → rewarded=false 不重复加
    - 与签到（tasks.py checkin）同款星尘加法：stardust_total += 1; star_tier = tier_for(...)
    """
    today = date.today()
    if payload.event_key not in VALID_ACTIVITY_KEYS:
        raise HTTPException(status_code=400, detail="未知的节点活动类型")
    event_type = ACTIVITY_TO_EVENT_TYPE[payload.event_key]
    if not any(ev["type"] == event_type for ev in astral_events_on(today)):
        raise HTTPException(status_code=400, detail="今天不是该节点活动日")
    event_key = f"{event_type}-{today.isoformat()}"

    existing = await db.execute(
        select(AstralActivityLog).where(
            AstralActivityLog.user_id == user.id,
            AstralActivityLog.event_key == event_key,
        )
    )
    if existing.scalar_one_or_none():
        # 当天已打卡（顺序重复）→ 幂等返回，不重复加
        return ActivityCheckInResponse(
            ok=True, rewarded=False, stardust_total=user.stardust_total or 0
        )

    db.add(AstralActivityLog(user_id=user.id, event_key=event_key, event_date=today))
    user.stardust_total = (user.stardust_total or 0) + 1
    user.star_tier = tier_for(user.stardust_total)
    try:
        await db.flush()
    except IntegrityError:
        # 并发重复打卡 → 唯一约束兜底：回滚后按已打卡返回（不重复 +1）
        await db.rollback()
        return ActivityCheckInResponse(
            ok=True, rewarded=False, stardust_total=user.stardust_total or 0
        )
    return ActivityCheckInResponse(
        ok=True, rewarded=True, stardust_total=user.stardust_total
    )


@router.get("/activity/summary", response_model=ActivitySummaryResponse)
async def activity_summary(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="月份 YYYY-MM"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """我的页星阶区：某月节点打卡汇总。

    completed=该月打卡次数；keys=去重后的活动形态（wish/review/mercury_guide）。
    """
    year, mon = month.split("-")
    try:
        start = date(int(year), int(mon), 1)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的月份")
    end = (
        date(start.year + 1, 1, 1)
        if start.month == 12
        else date(start.year, start.month + 1, 1)
    )
    result = await db.execute(
        select(AstralActivityLog).where(
            AstralActivityLog.user_id == user.id,
            AstralActivityLog.event_date >= start,
            AstralActivityLog.event_date < end,
        )
    )
    logs = result.scalars().all()
    keys = sorted(
        {
            NODE_TYPE_BY_EVENT.get(_event_type_from_key(log.event_key), "info")
            for log in logs
        }
    )
    return ActivitySummaryResponse(month=month, completed=len(logs), keys=keys)
