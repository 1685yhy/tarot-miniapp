"""
本命星盘 API（星光映照 · 开发 05）— 三要素计算 + 深度报告付费。

- GET  /user/birthchart          – 三要素（太阳/月亮/上升），AI 文案生成一次并缓存
- POST /user/birthchart/report   – 深度报告（会员免费；非会员需 birthchart_report 商品付费）
                                   结果缓存，重新生成需再付费或会员

安全：get_current_user 鉴权 + 全局限流中间件覆盖 + 输入校验。
红线：报告 prompt 遵守（不预测 / 不恐吓 / 不诊断 / 不引用日记）。
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.services.birthchart import (
    birth_fingerprint,
    compute_birthchart,
    fallback_report,
    generate_deep_report,
    generate_elements_text,
)
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user/birthchart", tags=["本命星盘"])


async def _chart_with_text(user: User, db: AsyncSession) -> dict:
    """计算三要素：优先 AI 文案（生成一次缓存到 birthchart_json，失败用模板）。"""
    fingerprint = birth_fingerprint(user.birth_date, user.birth_time, user.birth_city)

    ai_text: dict | None = None
    ai_attempted = False
    cached: dict | None = None
    if user.birthchart_json:
        try:
            cached = json.loads(user.birthchart_json)
        except (json.JSONDecodeError, TypeError):
            cached = None
        if cached and cached.get("fingerprint") == fingerprint:
            ai_text = cached.get("ai_text")
            ai_attempted = bool(cached.get("ai_attempted"))

    chart = compute_birthchart(
        birth_date=user.birth_date,
        birth_time=user.birth_time,
        birth_city=user.birth_city,
        ai_text=ai_text,
    )

    if chart["missing"] == [] and not ai_attempted:
        # 出生信息完整且从未生成过 → AI 生成一次（失败回退模板；ai_attempted 防重复调用）
        sun_key = chart["sun"]["zodiac"]
        moon_key = chart["moon"]["zodiac"]
        rising_key = chart["rising"]["zodiac"] if chart["rising"] else None
        generated = await generate_elements_text(sun_key, moon_key, rising_key)
        if generated:
            chart = compute_birthchart(
                birth_date=user.birth_date,
                birth_time=user.birth_time,
                birth_city=user.birth_city,
                ai_text=generated,
            )
            ai_text = generated
        ai_attempted = True

    # 落缓存（含指纹；出生信息变化时指纹失配自动重算）
    payload = {
        "fingerprint": fingerprint,
        "birth": chart["birth"],
        "sun": chart["sun"],
        "moon": chart["moon"],
        "rising": chart["rising"],
        "missing": chart["missing"],
        "message": chart["message"],
        "ai_text": ai_text,
        "ai_attempted": ai_attempted,
    }
    if user.birthchart_json != json.dumps(payload, ensure_ascii=False):
        user.birthchart_json = json.dumps(payload, ensure_ascii=False)
        await db.flush()

    return {
        "birth": chart["birth"],
        "sun": chart["sun"],
        "moon": chart["moon"],
        "rising": chart["rising"],
        "missing": chart["missing"],
        "message": chart["message"],
    }


@router.get("")
async def get_birthchart(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """三要素（太阳/月亮/上升）+ 缺失提示；出生信息不完整时返回部分字段。"""
    return await _chart_with_text(user, db)


@router.post("/report")
async def create_birthchart_report(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """深度报告：会员免费，非会员需 birthchart_paid（19.9 商品权益）。"""
    if not (user.is_member or user.birthchart_paid):
        raise HTTPException(
            status_code=402,
            detail="深度星图报告需会员或单次解锁（19.9 元）后使用",
        )

    if not user.birth_date:
        raise HTTPException(
            status_code=400,
            detail="请先完善出生信息（日期）再生成深度报告",
        )

    # ── 缓存：首次生成后复用（重新生成需再付费或会员）──
    if user.birthchart_report:
        try:
            cached = json.loads(user.birthchart_report)
            if cached and cached.get("birth_fingerprint") == birth_fingerprint(
                user.birth_date, user.birth_time, user.birth_city
            ):
                return {**cached, "cached": True}
        except (json.JSONDecodeError, TypeError):
            pass

    # ── 三要素（复用/重新计算，含 AI 文案缓存）──
    chart = await _chart_with_text(user, db)

    # ── 生成报告（AI → 模板兜底）──
    report = await generate_deep_report(chart) or fallback_report(chart)

    payload = {
        "birth_fingerprint": birth_fingerprint(user.birth_date, user.birth_time, user.birth_city),
        "character": report["character"],
        "relation": report["relation"],
        "annual_theme": report["annual_theme"],
        "card_advice": report["card_advice"],
        "fallback": bool(report.get("fallback")),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    user.birthchart_report = json.dumps(payload, ensure_ascii=False)
    await db.flush()

    return {k: v for k, v in payload.items()} | {"cached": False}
