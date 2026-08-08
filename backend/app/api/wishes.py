"""
新月许愿 + 满月复盘 API（开发 04 · 星光记录为主角的「我的流」）。

包含三组路由：
- GET  /moon/phase            月相查询（确定性天文算法，无第三方库）
- /wishes CRUD                许愿列表 / 许愿 / 状态更新 / 删除 / AI 一句温柔回应
- GET|POST /reviews/moon      满月复盘（聚合 15 天愿望 + 近两周日记 → AI 温柔复盘，
                              当天结果缓存，避免重复 AI 调用）

安全与红线：
- 全部接口 get_current_user 鉴权；全局限流中间件覆盖。
- 输入校验：愿望 1~100 字；status 仅 active|grown|answered；属主才能改/删。
- AI 文案红线：不预测、不恐吓、不引用日记具体内容（日记只感知情绪倾向）；
  愿望是用户主动写下的，可引用愿望内容。
"""

import json
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.review import MoonReview
from app.models.user import User
from app.models.wish import Wish
from app.schemas.wish import (
    MAX_ACTIVE_WISHES,
    WISH_CONTENT_MAX,
    WISH_STATUSES,
    MoonPhaseResponse,
    MoonReviewResponse,
    MoonReviewWishItem,
    WishBlessResponse,
    WishCreate,
    WishListResponse,
    WishResponse,
    WishUpdate,
)
from app.services.moon import moon_phase_on
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wishes", tags=["新月许愿"])
moon_router = APIRouter(prefix="/moon", tags=["月相"])
review_router = APIRouter(prefix="/reviews", tags=["满月复盘"])

# ── 满月复盘聚合窗口 ──
WISH_WINDOW_DAYS = 15   # 愿望窗口：覆盖最近一个新月→满月的半个周期
DIARY_WINDOW_DAYS = 15  # 日记窗口：近两周

# ── AI 客户端（与 diary.py 同款）──


def _get_ai_client() -> AsyncOpenAI | None:
    if not settings.DEEPSEEK_API_KEY:
        return None
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


# ── AI 红线块（复盘/祝福共用）：不预测、不恐吓、感知不引用 ──
_AI_RED_LINE = (
    "\n\n【输出红线】必须无条件遵守：\n"
    "1. 禁止预测愿望结果或承诺实现：不说「一定会实现」「马上就能」「这个月就会」"
    "等确定性断言，也不对时间窗口下判断。用「星光会一直陪着你的愿望」这类陪伴式"
    "表达替代「愿望一定会实现」。\n"
    "2. 禁止恐吓或制造焦虑：不用「再不努力就来不及了」之类的表达。\n"
    "3. 禁止命运定性、人格评判、健康或财务建议。\n"
    "4. 愿望内容由用户主动写下，可以逐字引用或意译；但用户日记只能感知情绪倾向"
    "（如「最近似乎有些起伏」），绝不引用、暗示或提及日记的任何具体内容。\n"
    "5. 语气温柔、克制、疗愈，像一位了解用户的老朋友。"
)


# ══════════════════════════════════════════════════════════════
# 月相
# ══════════════════════════════════════════════════════════════


@moon_router.get("/phase", response_model=MoonPhaseResponse)
async def get_moon_phase(user: User = Depends(get_current_user)):
    """当前月相 + 最近新月/满月日期（确定性天文算法，无第三方库）。"""
    return moon_phase_on(date.today())


# ══════════════════════════════════════════════════════════════
# 愿望 CRUD
# ══════════════════════════════════════════════════════════════


@router.get("", response_model=WishListResponse)
async def list_wishes(
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """我的愿望列表（按许愿时间倒序）。status 可选过滤。"""
    if status is not None and status not in WISH_STATUSES:
        raise HTTPException(status_code=400, detail="愿望状态不合法")

    query = select(Wish).where(Wish.user_id == user.id)
    if status is not None:
        query = query.where(Wish.status == status)
    query = query.order_by(Wish.created_at.desc())
    result = await db.execute(query)
    wishes = list(result.scalars().all())

    count_result = await db.execute(
        select(func.count(Wish.id)).where(
            Wish.user_id == user.id, Wish.status == "active"
        )
    )
    active_count = int(count_result.scalar() or 0)

    return WishListResponse(
        wishes=[WishResponse.model_validate(w) for w in wishes],
        total=len(wishes),
        active_count=active_count,
    )


@router.post("", response_model=WishResponse, status_code=201)
async def create_wish(
    body: WishCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写下愿望（交给月光保管）。

    - 内容 1~100 字（去除首尾空白后校验）。
    - 新月前后 3 天允许「许愿」，其他时间也允许（宽松策略，只记录月相）。
    - 同时「生长中」的愿望最多 10 条。
    """
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="愿望不能为空")
    if len(content) > WISH_CONTENT_MAX:
        raise HTTPException(status_code=400, detail=f"愿望最长 {WISH_CONTENT_MAX} 字")

    active_result = await db.execute(
        select(func.count(Wish.id)).where(
            Wish.user_id == user.id, Wish.status == "active"
        )
    )
    if int(active_result.scalar() or 0) >= MAX_ACTIVE_WISHES:
        raise HTTPException(
            status_code=400,
            detail=f"同时生长的愿望最多 {MAX_ACTIVE_WISHES} 条，先把旧愿望交给满月吧",
        )

    phase = moon_phase_on(date.today())
    wish = Wish(
        user_id=user.id,
        content=content,
        status="active",
        moon_phase=phase["phase"],
    )
    db.add(wish)
    await db.flush()
    return WishResponse.model_validate(wish)


@router.put("/{wish_id}", response_model=WishResponse)
async def update_wish(
    wish_id: str,
    body: WishUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新愿望状态（满月复盘时由 AI 判断后更新；属主可改）。"""
    result = await db.execute(
        select(Wish).where(Wish.id == wish_id, Wish.user_id == user.id)
    )
    wish = result.scalar_one_or_none()
    if not wish:
        raise HTTPException(status_code=404, detail="愿望不存在")
    wish.status = body.status
    await db.flush()
    return WishResponse.model_validate(wish)


@router.delete("/{wish_id}")
async def delete_wish(
    wish_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除愿望（属主可删）。"""
    result = await db.execute(
        select(Wish).where(Wish.id == wish_id, Wish.user_id == user.id)
    )
    wish = result.scalar_one_or_none()
    if not wish:
        raise HTTPException(status_code=404, detail="愿望不存在")
    await db.delete(wish)
    return {"ok": True}


# ── AI 联动：许愿后一句温柔回应 ──
_WISH_BLESS_TEMPLATES = {
    "new_moon": "星光会一直陪着你的愿望——新月听了，就会记得。",
    "full_moon": "月光正满，你的愿望被月亮好好收着。",
    "first_quarter": "星星替你看着，愿望会慢慢长出形状。",
    "last_quarter": "月亮记得你的话，星光一直在。",
    "waxing": "你的愿望和月亮一起，正在一天天变圆。",
    "waning": "星光会一直陪着你的愿望。",
}


@router.post("/{wish_id}/bless", response_model=WishBlessResponse)
async def bless_wish(
    wish_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 给许愿一句温柔回应（守红线：不预测结果，只陪伴）。

    AI 不可用时降级为本地温柔模板，接口永不失败。
    """
    result = await db.execute(
        select(Wish).where(Wish.id == wish_id, Wish.user_id == user.id)
    )
    wish = result.scalar_one_or_none()
    if not wish:
        raise HTTPException(status_code=404, detail="愿望不存在")

    phase = moon_phase_on(date.today())
    fallback = _WISH_BLESS_TEMPLATES.get(phase["phase"], _WISH_BLESS_TEMPLATES["waning"])

    client = _get_ai_client()
    if not client:
        return WishBlessResponse(id=wish.id, blessing=fallback)

    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=120,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是星光映照的月光保管者。用户刚在新月前后写下了一个愿望，"
                        "请给一句温柔简短的回应（40 字以内），像月光轻轻落下来。"
                        "只返回回应本身，不要引号、不要前缀。"
                        + _AI_RED_LINE
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"用户的愿望：「{wish.content[:60]}」\n"
                        f"当前月相：{phase['label']}（{phase['emoji']}）"
                    ),
                },
            ],
            timeout=30.0,
        )
        raw = (response.choices[0].message.content or "").strip().strip('"').strip("'")
        if raw:
            return WishBlessResponse(id=wish.id, blessing=raw[:60])
    except Exception as exc:
        logger.warning("wish bless AI 调用失败，降级本地模板: %s", exc)

    return WishBlessResponse(id=wish.id, blessing=fallback)


# ══════════════════════════════════════════════════════════════
# 满月复盘
# ══════════════════════════════════════════════════════════════

# 心情标签（与 diary.py MOOD_LABEL_MAP 一致，仅取标签做情绪倾向）
_MOOD_LABEL_MAP = {
    "happy": "开心", "calm": "平静", "excited": "兴奋",
    "anxious": "焦虑", "sad": "低落", "thoughtful": "思考",
}

# AI 失败/无 AI 时的本地温柔降级文案（守红线：不预测）
_FALLBACK_REVIEW = (
    "月亮没有辜负任何人。它只是用半个月，把愿望筛成了更真实的形状——"
    "你放下的，本就不属于你；你留下的，正在长成你。"
)
_FALLBACK_TIPS = [
    "给最在意的那个愿望安排一件明天就能做的小事",
    "把还没动静的愿望轻声读一遍——在意，就是改变的开始",
    "满月之后是新芽，留一点安静的时间给自己",
]
_FALLBACK_NOTE = {
    "active": "它还在路上——像月亮一样，慢慢变圆。",
    "grown": "它已经在你生活里长出了痕迹。",
    "answered": "月亮收下了它。等它变成你真正需要的形状。",
}


def _format_date(d: date) -> str:
    return f"{d.month}.{d.day}"


async def _build_review(
    user: User,
    db: AsyncSession,
    today: date,
) -> MoonReviewResponse:
    """聚合愿望 + 近两周日记 → AI 温柔复盘（失败时本地降级）。"""
    wish_cutoff = today - timedelta(days=WISH_WINDOW_DAYS)
    diary_cutoff = today - timedelta(days=DIARY_WINDOW_DAYS)
    date_range = f"{_format_date(wish_cutoff)} → {_format_date(today)}"

    # ── 愿望（窗口内全部，含已生长/已回应）──
    wish_result = await db.execute(
        select(Wish)
        .where(Wish.user_id == user.id, Wish.created_at >= wish_cutoff)
        .order_by(Wish.created_at.asc())
    )
    wishes = list(wish_result.scalars().all())

    # ── 近两周日记（只取日期 + 情绪标签 → 感知不引用）──
    from app.models.diary import DiaryEntry
    diary_result = await db.execute(
        select(DiaryEntry)
        .where(
            DiaryEntry.user_id == user.id,
            DiaryEntry.entry_date >= diary_cutoff,
        )
        .order_by(DiaryEntry.entry_date.asc())
    )
    diary_entries = list(diary_result.scalars().all())

    has_data = bool(wishes) or bool(diary_entries)
    if not has_data:
        return MoonReviewResponse(
            date=today.isoformat(),
            date_range=date_range,
            wishes=[],
            review="",
            tips=[],
            has_data=False,
            cached=False,
        )

    # ── 喂给 AI 的数据 ──
    wishes_text = "\n".join(
        f"- 「{w.content}」（当前状态：{'生长中' if w.status=='active' else '已生长' if w.status=='grown' else '待回应'}）"
        for w in wishes
    ) or "（本月还没有许愿）"

    mood_tendency = "、".join(
        _MOOD_LABEL_MAP.get(e.mood, "平静") for e in diary_entries if e.mood
    )[:80] or "整体平稳"

    client = _get_ai_client()
    if client:
        try:
            response = await client.chat.completions.create(
                model=settings.DEEPSEEK_MODEL,
                max_tokens=900,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是星光映照的满月复盘者，温柔、克制、有洞察力。"
                            "满月之夜，请帮用户回望新月许下的愿望，并对照近两周的"
                            "星光日记情绪倾向，写一份治愈的复盘。\n\n"
                            "要求：\n"
                            "1. 对每个愿望写一句 30 字以内的「回望注脚」（note），"
                            "语气像懂他的老朋友，平静而温暖。\n"
                            "2. 总体复盘（review）80~150 字，把愿望与情绪倾向温柔地"
                            "编织在一起。\n"
                            "3. 给出 3 条 tips，每条 25 字以内，具体、可执行、不评判。\n"
                            "4. 愿望内容可以引用；日记只能以「最近似乎…」的方式感知，"
                            "绝不引用日记内容。\n"
                            "5. 严格输出纯 JSON：\n"
                            "{\"wishes\":[{\"content\":\"原文\",\"status\":\"active|grown|answered\",\"note\":\"...\"}],"
                            "\"review\":\"...\",\"tips\":[\"...\",\"...\",\"...\"]}\n"
                            "wishes 数组包含用户全部愿望（原样返回 content 与 status）。"
                            + _AI_RED_LINE
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"复盘窗口：{date_range}\n"
                            f"新月以来的愿望：\n{wishes_text}\n\n"
                            f"近两周日记情绪倾向：{mood_tendency}"
                        ),
                    },
                ],
                timeout=60.0,
            )
            content = response.choices[0].message.content
            if content:
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = "\n".join(
                        line for line in cleaned.split("\n")
                        if not line.strip().startswith("```")
                    ).strip()
                ai_data = json.loads(cleaned)
                items: list[MoonReviewWishItem] = []
                for w_item in ai_data.get("wishes") or []:
                    content_text = str(w_item.get("content") or "").strip()
                    # 只保留用户真实写下的愿望，防 AI 幻觉编造
                    match = next((w for w in wishes if w.content == content_text), None)
                    if match:
                        items.append(
                            MoonReviewWishItem(
                                content=content_text,
                                status=str(w_item.get("status") or match.status),
                                note=str(w_item.get("note") or "").strip()[:60],
                            )
                        )
                review_text = str(ai_data.get("review") or "").strip()
                tips = [str(t).strip()[:30] for t in (ai_data.get("tips") or []) if str(t).strip()]
                if items or review_text:
                    return MoonReviewResponse(
                        date=today.isoformat(),
                        date_range=date_range,
                        wishes=items or [
                            MoonReviewWishItem(
                                content=w.content,
                                status=w.status,
                                note=_FALLBACK_NOTE.get(w.status, ""),
                            )
                            for w in wishes
                        ],
                        review=review_text or _FALLBACK_REVIEW,
                        tips=tips or _FALLBACK_TIPS,
                        has_data=True,
                        cached=False,
                    )
        except Exception as exc:
            logger.warning("满月复盘 AI 生成失败，降级本地文案: %s", exc)

    # ── 本地降级（无 AI 或解析失败）──
    return MoonReviewResponse(
        date=today.isoformat(),
        date_range=date_range,
        wishes=[
            MoonReviewWishItem(
                content=w.content,
                status=w.status,
                note=_FALLBACK_NOTE.get(w.status, ""),
            )
            for w in wishes
        ],
        review=_FALLBACK_REVIEW,
        tips=list(_FALLBACK_TIPS),
        has_data=True,
        cached=False,
    )


@review_router.get("/moon", response_model=MoonReviewResponse)
async def get_moon_review(
    force: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """满月复盘（当天缓存：每人每天一份，避免重复 AI 调用）。"""
    today = date.today()

    if not force:
        cached_result = await db.execute(
            select(MoonReview).where(
                MoonReview.user_id == user.id,
                MoonReview.review_date == today,
            )
        )
        cached = cached_result.scalar_one_or_none()
        if cached:
            try:
                data = json.loads(cached.data)
            except (ValueError, TypeError):
                data = None
            if data is not None:
                return MoonReviewResponse(
                    date=data.get("date", today.isoformat()),
                    date_range=data.get("date_range", ""),
                    wishes=[
                        MoonReviewWishItem(**w) for w in data.get("wishes", [])
                    ],
                    review=data.get("review", ""),
                    tips=data.get("tips", []),
                    has_data=data.get("has_data", False),
                    cached=True,
                )

    review = await _build_review(user, db, today)

    # ── 有数据才缓存（空态每次都算，成本极低）──
    if review.has_data:
        existing_result = await db.execute(
            select(MoonReview).where(
                MoonReview.user_id == user.id,
                MoonReview.review_date == today,
            )
        )
        existing = existing_result.scalar_one_or_none()
        payload = json.dumps(
            {
                "date": review.date,
                "date_range": review.date_range,
                "wishes": [w.model_dump() for w in review.wishes],
                "review": review.review,
                "tips": review.tips,
                "has_data": True,
            },
            ensure_ascii=False,
        )
        if existing:
            existing.data = payload
        else:
            db.add(MoonReview(user_id=user.id, review_date=today, data=payload))

    return review


@review_router.post("/moon", response_model=MoonReviewResponse)
async def regenerate_moon_review(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动重新生成满月复盘（覆盖当天缓存）。"""
    return await get_moon_review(force=True, user=user, db=db)
