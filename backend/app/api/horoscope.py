"""
星座能量引擎 API — GET /horoscope/daily + 用户星座/出生信息。

安全：所有接口 get_current_user 鉴权；限流中间件默认覆盖；
zodiac 限 12 个合法 key（兼容中文名输入）。
文案红线：summary/tip 由规则模板生成（不预测 / 不恐吓）。
"""

from datetime import date as date_cls
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.card import TarotCard
from app.models.diary import DiaryEntry
from app.models.horoscope import HoroscopeHistory
from app.models.user import User
from app.schemas.horoscope import (
    AstralInfo,
    BirthUpdate,
    DailyHoroscopeResponse,
    Factor,
    ProfileUpdateResponse,
    TarotBrief,
    ZodiacUpdate,
)
from app.services.daily_card import pick_daily_card
from app.services.energy_engine import compute_energy
from app.utils.auth import get_current_user

router = APIRouter(prefix="/horoscope", tags=["星座能量"])
profile_router = APIRouter(prefix="/user", tags=["用户资料"])

# 12 星座合法 key（与前端 miniapp/utils/energy.js ZODIACS 一致）
ZODIAC_KEYS = {
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
}
ZODIAC_NAME_TO_KEY = {
    "白羊座": "aries", "金牛座": "taurus", "双子座": "gemini", "巨蟹座": "cancer",
    "狮子座": "leo", "处女座": "virgo", "天秤座": "libra", "天蝎座": "scorpio",
    "射手座": "sagittarius", "摩羯座": "capricorn", "水瓶座": "aquarius", "双鱼座": "pisces",
}

# 卡牌图片 CDN 路径（与前端 utils/cards.js computeImagePath 同算法）
CARD_IMAGE_BASE = "https://xingxiang.chat/images/cards_full"
_RANK_MAP = {
    "ace": 0, "two": 1, "three": 2, "four": 3, "five": 4,
    "six": 5, "seven": 6, "eight": 7, "nine": 8, "ten": 9,
    "page": 10, "knight": 11, "queen": 12, "king": 13,
}


def normalize_zodiac(raw: str) -> str:
    """兼容 key 与中文名（如 'leo' / '狮子座'），非法值返回 None。"""
    value = (raw or "").strip().lower()
    if value in ZODIAC_KEYS:
        return value
    if value in ZODIAC_NAME_TO_KEY:
        return ZODIAC_NAME_TO_KEY[value]
    return ""


def card_image_url(card: TarotCard) -> str:
    """与前端 computeImagePath 相同算法生成卡牌图片 URL。"""
    en_snake = (card.name_en or "").lower().replace(" ", "_")
    if card.arcana == "major":
        return f"{CARD_IMAGE_BASE}/major_{card.card_number:02d}_{en_snake}.webp"
    first_word = en_snake.split("_")[0]
    rank = _RANK_MAP.get(first_word, 0)
    return f"{CARD_IMAGE_BASE}/{card.suit}_{rank:02d}_{en_snake}.webp"


@router.get("/daily", response_model=DailyHoroscopeResponse)
async def daily_horoscope(
    date: str | None = Query(None, description="目标日期 YYYY-MM-DD，默认今天（供测试与回填）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    今日星座能量：确定性规则引擎（同日同人恒定），返回 4 维能量 + 解释链 factors。

    平滑约束：与昨日历史值差 ≤ 15（无昨日记录则不受限）。
    """
    # ── 目标日期 ──
    if date:
        try:
            target = date_cls.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    else:
        target = date_cls.today()
    if target < date_cls(2000, 1, 1) or target > date_cls(2100, 12, 31):
        raise HTTPException(status_code=400, detail="日期超出支持范围")

    # ── 出生日期：优先 user.birth_date，否则 user.created_at 近似 ──
    if user.birth_date:
        try:
            birth_date = date_cls.fromisoformat(user.birth_date)
        except ValueError:
            birth_date = user.created_at.date()
    else:
        birth_date = user.created_at.date()

    # ── 今日塔罗牌（与 /cards/daily 同一确定性选牌逻辑）──
    card_result = await db.execute(select(TarotCard).order_by(TarotCard.id))
    cards = card_result.scalars().all()
    tarot_card = pick_daily_card(list(cards), user.id, target) if cards else None

    # ── 近 7 天日记 reflection（含目标日）──
    diary_result = await db.execute(
        select(DiaryEntry.reflection).where(
            DiaryEntry.user_id == user.id,
            DiaryEntry.entry_date >= target - timedelta(days=6),
            DiaryEntry.entry_date <= target,
        )
    )
    diary_texts = [r for (r,) in diary_result.all() if r]

    # ── 昨日能量历史（平滑约束用）──
    yesterday = None
    y_result = await db.execute(
        select(HoroscopeHistory).where(
            HoroscopeHistory.user_id == user.id,
            HoroscopeHistory.date == target - timedelta(days=1),
        )
    )
    y_row = y_result.scalar_one_or_none()
    if y_row and y_row.energy:
        yesterday = y_row.energy

    # ── 引擎计算（纯函数，确定性）──
    result = compute_energy(
        target_date=target,
        birth_date=birth_date,
        zodiac=user.zodiac or None,
        tarot_card=tarot_card,
        diary_texts=diary_texts,
        yesterday=yesterday,
    )

    # ── 历史 upsert（唯一约束 user+date）──
    hist_result = await db.execute(
        select(HoroscopeHistory).where(
            HoroscopeHistory.user_id == user.id,
            HoroscopeHistory.date == target,
        )
    )
    hist = hist_result.scalar_one_or_none()
    if hist:
        hist.energy = result["energy"]
        hist.factors = result["factors"]
        hist.astral = result["astral"]
        hist.summary = result["summary"]
        hist.tip = result["tip"]
    else:
        db.add(HoroscopeHistory(
            user_id=user.id,
            date=target,
            energy=result["energy"],
            factors=result["factors"],
            astral=result["astral"],
            summary=result["summary"],
            tip=result["tip"],
        ))

    return DailyHoroscopeResponse(
        date=target.isoformat(),
        zodiac=user.zodiac,
        energy=result["energy"],
        factors={dim: [Factor(**f) for f in result["factors"][dim]] for dim in result["factors"]},
        astral=AstralInfo(**result["astral"]),
        tarot=TarotBrief(
            name=tarot_card.name_zh,
            name_en=tarot_card.name_en,
            image=card_image_url(tarot_card),
        ) if tarot_card else None,
        summary=result["summary"],
        tip=result["tip"],
    )


@profile_router.post("/zodiac", response_model=ProfileUpdateResponse)
async def update_zodiac(
    body: ZodiacUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存用户星座（12 个合法值，兼容中文名）。"""
    key = normalize_zodiac(body.zodiac)
    if not key:
        raise HTTPException(status_code=400, detail="无效的星座，可选值：" + "、".join(sorted(ZODIAC_KEYS)))
    user.zodiac = key
    return ProfileUpdateResponse(zodiac=user.zodiac)


@profile_router.post("/birth", response_model=ProfileUpdateResponse)
async def update_birth(
    body: BirthUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存出生信息（二期星盘计算用，先存储；birth_date 需 YYYY-MM-DD 且为过去日期）。"""
    if body.birth_date:
        try:
            bd = date_cls.fromisoformat(body.birth_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="birth_date 格式应为 YYYY-MM-DD")
        if bd >= date_cls.today():
            raise HTTPException(status_code=400, detail="birth_date 应为过去日期")
        user.birth_date = body.birth_date
    if body.birth_time is not None:
        user.birth_time = body.birth_time
    if body.birth_city is not None:
        user.birth_city = body.birth_city
    return ProfileUpdateResponse(
        birth_date=user.birth_date,
        birth_time=user.birth_time,
        birth_city=user.birth_city,
    )
