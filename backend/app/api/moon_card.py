"""月光卡（睡前星语）端点 — GET /moon-card/today。

数据源：``app.services.star_words.get_today_star_word``（AI 优先 + 短句库兜底 +
同用户同日缓存，source=ai|fallback）；月相/星光色/星光数均为确定性计算，
与推送（T4-3）、月光卡页面同源。

同日同人恒定由「缓存 + 确定性选择」双重保证。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.services import star_words
from app.services.energy_engine import build_today_guidance
from app.services.moon import moon_phase_on
from app.utils.auth import get_current_user

router = APIRouter(prefix="/moon-card", tags=["睡前星语"])


class MoonPhaseOut(BaseModel):
    emoji: str
    label: str


class MoonCardTodayResponse(BaseModel):
    date: str
    phase: MoonPhaseOut
    phrase: str
    star_color: str
    star_number: int
    source: str


@router.get("/today", response_model=MoonCardTodayResponse)
async def moon_card_today(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """今日月光卡数据：星语 + 月相 + 星光色/数 + 来源（ai|fallback）。

    首次调用生成并落同日缓存（AI 优先，失败降级短句库）；
    此后同日请求直接命中缓存，不再调 AI。
    """
    today = star_words.beijing_today()
    result = await star_words.get_today_star_word(db, user, today)
    guidance = build_today_guidance(today, user.zodiac or None)
    phase = moon_phase_on(today)
    return MoonCardTodayResponse(
        date=today.isoformat(),
        phase=MoonPhaseOut(emoji=phase["emoji"], label=phase["label"]),
        phrase=result["phrase"],
        star_color=guidance["star_color"],
        star_number=guidance["star_number"],
        source=result["source"],
    )
