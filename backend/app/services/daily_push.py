"""
21:00 晚间推送 — 每日一牌定时推送（Co-Star 模式，限量制造期待）。

- 每天 21:00（北京时间 UTC+8，中国无夏令时用固定偏移）向所有已订阅
  TEMPLATE_DAILY_CARD 的用户推送「今晚之牌」：当天每日一牌的牌名 + 一句牌语。
- 牌面按「用户 id + 日期」hash 确定性选取（与 /cards/daily 同一逻辑，
  见 services/daily_card.py），保证用户收到的就是当天白天看到的那张牌。
- 月相事件优先（开发 04）：新月前 1 天推送「明日新月，准备好愿望了吗 ✦」
  （页面 pages/wish/wish）；满月当天推送「满月之夜，来复盘你的愿望 ✦」
  （页面 pages/review/review）。复用同一订阅列表与模板。
- 模板 ID 从 settings（WX_TEMPLATE_DAILY_CARD）读取；未配置时记 error 日志
  并跳过（服务不崩溃，也不向微信发请求）。
- 已发送日期记在内存 + data/daily_push_state.json（best-effort 持久化，
  服务重启后不会重复发送）。

main.py 启动时挂后台任务：run_daily_push_loop()，每 5 分钟检查一次。
"""

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import async_session
from app.models.card import TarotCard
from app.models.push_subscription import PushSubscription
from app.services.daily_card import pick_daily_card
from app.services.push import (
    TEMPLATE_DAILY_CARD,
    build_daily_card_data,
    is_template_configured,
    resolve_template_id,
    send_subscribe_message,
)

logger = logging.getLogger(__name__)

# 北京时间 = UTC+8（中国无夏令时，固定偏移即可）
BEIJING_TZ = timezone(timedelta(hours=8))
PUSH_HOUR = 21

_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "daily_push_state.json",
)

# 内存态：'YYYY-MM-DD'（北京时间）
_last_sent_date: str | None = None
# 模板未配置的日志去重（每天只记一次 error，避免每 5 分钟刷屏）
_last_config_error_date: str | None = None


def _load_state() -> None:
    global _last_sent_date
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            _last_sent_date = data.get("last_sent_date") or None
    except (OSError, ValueError, json.JSONDecodeError):
        _last_sent_date = None


def _save_state() -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_sent_date": _last_sent_date}, f)
    except OSError:
        pass  # best-effort：内存态仍有效，仅重启后会重复一次


def _first_keyword(card: TarotCard) -> str:
    """从卡牌关键词（JSON 数组字符串或纯文本）中取第一句作为牌语。"""
    raw = card.keywords_upright or ""
    if not raw:
        return "查看今日指引"
    try:
        kws = json.loads(raw)
        if isinstance(kws, list) and kws:
            return str(kws[0])[:20]
    except (ValueError, TypeError):
        pass
    first = raw.split("，")[0].split(",")[0].strip()
    return first[:20] or "查看今日指引"


def get_moon_push_event(today: date) -> dict | None:
    """返回今天的月相推送事件（开发 04），无事件返回 None。

    - 新月前 1 天（明天是新月日）→ 「明日新月，准备好愿望了吗 ✦」→ pages/wish/wish
    - 满月当天 → 「满月之夜，来复盘你的愿望 ✦」→ pages/review/review
    - 其他日期 → None（走常规每日一牌）

    月相判定与 /moon/phase 同一确定性算法（services/moon.py），
    推送、页面展示、许愿记录完全同源。
    """
    from app.services.moon import moon_phase_on, next_new_moon_after

    phase = moon_phase_on(today)["phase"]
    if phase == "full_moon":
        return {
            "kind": "full_moon",
            "title": "满月复盘",
            "content": "满月之夜，来复盘你的愿望 ✦",
            "page": "pages/review/review",
        }
    if next_new_moon_after(today) == today + timedelta(days=1):
        return {
            "kind": "new_moon_eve",
            "title": "新月许愿",
            "content": "明日新月，准备好愿望了吗 ✦",
            "page": "pages/wish/wish",
        }
    return None


def build_moon_push_data(event: dict, today: date) -> dict[str, dict[str, str]]:
    """构建月相事件的模板数据（复用每日一牌模板字段：thing1/thing2/date3/thing4）。"""
    return {
        "thing1": {"value": _truncate_str(event["title"], 20)},
        "thing2": {"value": _truncate_str(event["content"], 20)},
        "date3": {"value": today.strftime("%Y.%m.%d")},
        "thing4": {"value": "点击开启 ✦"},
    }


def _truncate_str(value: str, max_len: int = 20) -> str:
    return value if len(value) <= max_len else value[:max_len]


async def send_daily_push_if_due(db: AsyncSession, now: datetime | None = None) -> dict:
    """到 21:00（北京时间）且今天未发送时，向订阅用户推送「今晚之牌」。

    Parameters
    ----------
    db : AsyncSession
        数据库会话。
    now : datetime, optional
        注入的当前时间（测试用），默认取系统时间并换算为北京时间。

    Returns
    -------
    dict
        - {"status": "skipped_config"}  模板未配置（记 error 日志，不崩溃）
        - {"status": "not_due"}         未到 21:00，或今天已发送过
        - {"status": "no_subscribers"}  无订阅用户 / 卡牌数据为空
        - {"status": "sent", "sent": n, "failed": m}  发送完成
    """
    global _last_sent_date, _last_config_error_date
    if _last_sent_date is None:
        _load_state()

    now = (now or datetime.now(BEIJING_TZ)).astimezone(BEIJING_TZ)
    today_str = now.date().isoformat()

    # ── 模板未配置：记 error 日志并跳过（每天只记一次）──
    if not is_template_configured(TEMPLATE_DAILY_CARD):
        if _last_config_error_date != today_str:
            logger.error(
                "21:00 每日推送跳过：WX_TEMPLATE_DAILY_CARD 未配置"
                "（请在 .env 配置真实模板 ID 后重启服务）"
            )
            _last_config_error_date = today_str
        return {"status": "skipped_config"}

    # ── 时间与去重 ──
    if now.hour < PUSH_HOUR:
        return {"status": "not_due"}
    if _last_sent_date == today_str:
        return {"status": "not_due"}

    # ── 订阅用户（每日一牌模板）──
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.template_id == TEMPLATE_DAILY_CARD,
            PushSubscription.subscribed.is_(True),
        )
    )
    subs = list(result.scalars().all())
    if not subs:
        logger.info("21:00 每日推送：今日无订阅用户，跳过")
        _last_sent_date = today_str
        _save_state()
        return {"status": "no_subscribers"}

    # ── 一次性加载完整牌库，按用户逐人确定性选牌 ──
    card_result = await db.execute(select(TarotCard).order_by(TarotCard.id))
    cards = list(card_result.scalars().all())
    if not cards:
        logger.error("21:00 每日推送：卡牌数据为空，跳过")
        return {"status": "no_subscribers"}

    template_id = resolve_template_id(TEMPLATE_DAILY_CARD)

    # ── 月相事件优先（开发 04）：新月前夜 / 满月之夜 ──
    moon_event = get_moon_push_event(now.date())

    sent = 0
    failed = 0
    for sub in subs[:1000]:  # 微信单模板每小时上限 1000 条
        try:
            if moon_event:
                data = build_moon_push_data(moon_event, now.date())
                page = moon_event["page"]
            else:
                card = pick_daily_card(cards, sub.user_id)
                data = build_daily_card_data(
                    card_name=card.name_zh,
                    keyword=_first_keyword(card),
                    date_str=today_str.replace("-", "."),
                    hint="今晚之牌 · 点击查看牌面详解",
                )
                page = "pages/daily-card/daily-card"
            resp = await send_subscribe_message(
                openid=sub.openid,
                template_id=template_id,
                data=data,
                page=page,
            )
            if resp.get("errcode") == 0:
                sent += 1
            else:
                failed += 1
        except Exception:
            logger.exception("21:00 每日推送失败：user=%s", sub.user_id)
            failed += 1

    _last_sent_date = today_str
    _save_state()
    logger.info("21:00 每日推送完成：sent=%d failed=%d", sent, failed)
    return {"status": "sent", "sent": sent, "failed": failed}


async def run_daily_push_loop(
    interval_seconds: int = 300,
    stop_event: asyncio.Event | None = None,
) -> None:
    """后台任务：每 5 分钟检查一次是否到 21:00 且今天未发送。

    模板未配置时直接退出（记 error 日志），不空转。异常被捕获并记录，
    循环继续，保证推送任务永不崩溃整个服务。
    """
    if not is_template_configured(TEMPLATE_DAILY_CARD):
        logger.error(
            "21:00 每日推送定时任务未启动：WX_TEMPLATE_DAILY_CARD 未配置"
            "（请在 .env 配置真实模板 ID 后重启服务）"
        )
        return

    while True:
        try:
            async with async_session() as db:
                await send_daily_push_if_due(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("21:00 每日推送循环异常")

        for _ in range(interval_seconds):
            if stop_event is not None and stop_event.is_set():
                return
            await asyncio.sleep(1)
