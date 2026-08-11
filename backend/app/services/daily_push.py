"""
星光晨讯（7:37） + 睡前星语（21:00）— 两个定时推送共用 run_daily_push_loop。

【7:37 星光晨讯（Task 5，按额度消费）】
- 每天 7:37（北京时间 UTC+8，固定偏移）向「有订阅额度、槽位偏好 morning、
  且今天未发过」的用户推送「今日星光」：今日星光一句话（能量+星光数）+
  星象宜忌 + 星光色 + 日期。
- 额度来源：微信一次性订阅授权（POST /notify/subscribe-grant → quota+1）；
  发送成功后 quota-1、记 last_sent_date（同日最多 1 条）。
- 失败退避（最终审查 F-2）：微信 errcode!=0 / 异常时认领回退照旧（不扣额度），
  但每用户当日失败次数达 _MAX_ATTEMPTS（3）次后，本日不再尝试该
  用户——避免微信持续故障时每 5 分钟循环全天重试烧配额刷日志；
  计数按日存储（user_id → (日期, 次数)），次日日期变化自动重置。
- 并发安全（原子认领）：发送前对每个用户执行
  `UPDATE subscribe_quotas SET last_sent_date=:today WHERE user_id=:id
  AND (last_sent_date IS NULL OR last_sent_date != :today)`，rowcount==1
  才算认领成功；成功后逐条 commit（额度减扣与 last_sent_date 同事务），
  崩溃/并发交错时同用户同日最多发 1 条。发送失败不扣额度，认领回退为
  NULL（允许下一轮循环重试）；批标记 _morning_sent_date 仅作内存级第二道防线，
  且仅在整批无失败时置位（有失败则保留空，让 5 分钟循环补发失败用户）。
- 内容与今日星光卡同源：build_today_guidance（星光色/数/宜忌）+ 能量
  （优先今日 HoroscopeHistory，无则轻量 compute_energy）。
- 时间配置：settings.SEND_TIME（默认 "07:37"）。

【21:00 睡前星语（T4-3：额度制 + 槽位偏好分流）】
- 每天 21:00 向「有订阅额度、槽位偏好 night、且今天未发过」的用户推送
  睡前星语（T4-2 star_words：AI 优先 + 短句库兜底 + 同日缓存），点击直达
  pages/moon-card/moon-card（月光卡）。
- 与晨讯共用 SubscribeQuota 的 last_sent_date 原子认领：两槽位共享每日
  最多 1 条硬上限；失败认领回退不扣额度；星语槽位独立当日失败计数
  _night_fail_counts（同 _MAX_ATTEMPTS=3 语义）。
- 月相事件优先（开发 04 + T4-3）：新月前 1 天 / 满月当天，21:00 向**全部**
  有额度未发用户（不分槽位偏好）推送节点版（build_moon_push_data +
  pages/wish/wish 或 pages/review/review），当日不发星语——节点召回不因
  槽位偏好丢失。
- 存量兼容：PushSubscription（TEMPLATE_DAILY_CARD）不再作为 21:00 发送
  依据，仅作设置页「推送开关」展示数据源；未授权新额度的老用户晚间不再推送。

通用约定：
- 模板 ID 从 settings（WX_TEMPLATE_DAILY_CARD）读取；未配置时记 error 日志
  并跳过（服务不崩溃，也不向微信发请求）。
- 批标记记在内存 + data/daily_push_state.json（best-effort 持久化，
  服务重启后不会重复发送）。

main.py 启动时挂后台任务：run_daily_push_loop()，每 5 分钟检查一次。
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import async_session
from app.models.horoscope import HoroscopeHistory
from app.models.subscribe_quota import SubscribeQuota
from app.models.user import User
from app.services.energy_engine import DIM_NAMES_ZH, build_today_guidance, compute_energy
from app.services.push import (
    TEMPLATE_DAILY_CARD,
    is_template_configured,
    resolve_template_id,
    send_subscribe_message,
)
from app.services.star_words import build_star_word_data, get_today_star_word

logger = logging.getLogger(__name__)

# 北京时间 = UTC+8（中国无夏令时，固定偏移即可）
BEIJING_TZ = timezone(timedelta(hours=8))
PUSH_HOUR = 21
# 星光晨讯目标页（今日星光卡在首页）
MORNING_PAGE = "pages/index/index"
# 睡前星语目标页（月光卡最小可用版，T4-3）
NIGHT_PAGE = "pages/moon-card/moon-card"

_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "daily_push_state.json",
)

# 内存态：'YYYY-MM-DD'（北京时间）
# _last_sent_date：21:00 睡前星语批标记（内存级第二道防线，逐人去重靠
#   SubscribeQuota.last_sent_date 原子认领；仅整批无失败时置位）
# _morning_sent_date：7:37 星光晨讯批标记（同上模式）
_last_sent_date: str | None = None
_morning_sent_date: str | None = None
# 模板未配置的日志去重（每天只记一次 error，避免每 5 分钟刷屏）
_last_config_error_date: str | None = None

@dataclass(frozen=True)
class _UserSnapshot:
    """推送循环前的用户纯值快照（T1-8 闭环，Fix round 2）。

    不持有 ORM 对象：循环内可能发生 rollback（get_today_star_word →
    _save_cache 并发首写撞 uq_user_word_date 唯一约束；_release_claim
    异常路径）——``db.rollback()`` 无条件过期会话内**所有** ORM 对象
    （``expire_on_commit=False`` 只影响 commit 不影响 rollback），async 下
    惰性加载抛 MissingGreenlet。快照只含纯值，回滚后依然可用；循环体内
    零 ORM 属性访问，认领/扣减/回退全部用纯值参数。
    """

    id: str  # user_id（与 quota.user_id 同值）
    openid: str
    zodiac: str | None
    birth_date: str | None
    created_at: datetime | None
    quota_available: int


# ── 失败退避（最终审查 F-2 + T4-3）：各槽位当日每用户重试上限 ──
# 内存计数：user_id -> (失败日期'YYYY-MM-DD', 当日失败次数)。
# 日期不等于今天时视为新的一天，自然重置；仅内存、不持久化（重启后
# 重新计数，最多多试 3 次，无副作用）。晨讯与星语槽位计数相互独立。
_MAX_ATTEMPTS = 3
_morning_fail_counts: dict[str, tuple[str, int]] = {}
_night_fail_counts: dict[str, tuple[str, int]] = {}


def _is_attempt_exhausted(
    fail_counts: dict[str, tuple[str, int]], user_id: str, today_str: str
) -> bool:
    """当日失败次数已达上限 → 本日不再尝试该用户。"""
    entry = fail_counts.get(user_id)
    return entry is not None and entry[0] == today_str and entry[1] >= _MAX_ATTEMPTS


def _record_failure(
    fail_counts: dict[str, tuple[str, int]], user_id: str, today_str: str
) -> None:
    """记录一次发送失败（按用户当日计数；跨日自动重置）。"""
    entry = fail_counts.get(user_id)
    if entry is None or entry[0] != today_str:
        fail_counts[user_id] = (today_str, 1)
    else:
        fail_counts[user_id] = (today_str, entry[1] + 1)


def _load_state() -> None:
    global _last_sent_date, _morning_sent_date
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            _last_sent_date = data.get("last_sent_date") or None
            _morning_sent_date = data.get("morning_sent_date") or None
    except (OSError, ValueError, json.JSONDecodeError):
        _last_sent_date = None
        _morning_sent_date = None


def _save_state() -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "last_sent_date": _last_sent_date,
                    "morning_sent_date": _morning_sent_date,
                },
                f,
            )
    except OSError:
        pass  # best-effort：内存态仍有效，仅重启后会重复一次


def _parse_send_time(value: str | None) -> tuple[int, int]:
    """解析 SEND_TIME（"07:37"）→ (hour, minute)；配置异常时回退默认 07:37。"""
    try:
        hour_s, minute_s = (value or "07:37").strip().split(":")
        return int(hour_s), int(minute_s)
    except (ValueError, AttributeError):
        return 7, 37


def get_moon_push_event(today: date) -> dict | None:
    """返回今天的月相推送事件（开发 04），无事件返回 None。

    - 新月前 1 天（明天是新月日）→ 「明日新月，准备好愿望了吗 ✦」→ pages/wish/wish
    - 满月当天 → 「满月之夜，来复盘你的愿望 ✦」→ pages/review/review
    - 其他日期 → None（普通日走 7:37 星光晨讯 / 21:00 睡前星语常规推送）

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


# ---------------------------------------------------------------------------
# 7:37 星光晨讯（Task 5 · 订阅额度消费制）
# ---------------------------------------------------------------------------


def build_starlight_morning_data(
    today: date,
    guidance: dict,
    energy: dict | None = None,
) -> dict[str, dict[str, str]]:
    """
    构建「今日星光」晨讯模板数据（复用每日一牌模板字段 thing1/thing2/date3/thing4）。

    字段映射（微信 thing 字段 20 字符上限）:
      - thing1: 今日星光一句话（星光数 + 能量）→ "今日星光7 · 能量爱情81"
      - thing2: 星象宜忌 → "宜·表达心意 / 忌·独自纠结"
      - date3:  日期 → "2026.08.10"
      - thing4: 星光色 + 提示 → "星光色 #A98B5F · 点击查看今日星光"
    """
    star_number = guidance.get("star_number", "")
    star_color = guidance.get("star_color", "")
    advice_do = guidance.get("advice_do", "")
    advice_dont = guidance.get("advice_dont", "")
    if energy:
        top_dim = max(energy, key=lambda d: energy[d])
        energy_text = f"能量{DIM_NAMES_ZH.get(top_dim, top_dim)}{energy[top_dim]}"
    else:
        energy_text = "点击查看今日星光"
    return {
        "thing1": {"value": _truncate_str(f"今日星光{star_number} · {energy_text}", 20)},
        "thing2": {"value": _truncate_str(f"{advice_do} / {advice_dont}", 20)},
        "date3": {"value": today.strftime("%Y.%m.%d")},
        "thing4": {"value": _truncate_str(f"星光色 {star_color} · 点击查看今日星光", 20)},
    }


async def _today_energy(db: AsyncSession, user: User, today: date) -> dict:
    """今日能量：优先今日已生成的 HoroscopeHistory（与 App 展示一致），
    无则用纯确定性轻量计算（无塔罗/日记修正，仅星座+生物节律+天象）。"""
    hist_result = await db.execute(
        select(HoroscopeHistory).where(
            HoroscopeHistory.user_id == user.id,
            HoroscopeHistory.date == today,
        )
    )
    hist = hist_result.scalar_one_or_none()
    if hist and hist.energy:
        return hist.energy
    if user.birth_date:
        try:
            birth_date = date.fromisoformat(user.birth_date)
        except ValueError:
            birth_date = (user.created_at or datetime.now(timezone.utc)).date()
    else:
        birth_date = (user.created_at or datetime.now(timezone.utc)).date()
    result = compute_energy(
        target_date=today,
        birth_date=birth_date,
        zodiac=user.zodiac or None,
    )
    return result["energy"]


async def _release_claim(db: AsyncSession, user_id: str, today: date) -> None:
    """发送失败 → 回退认领（last_sent_date 置回 NULL），不扣额度，允许下次重试。

    认领（last_sent_date=today）与发送在同一事务内：失败时把 today 回退为
    NULL 并 commit，微信临时故障不会烧掉用户的一次性授权。
    晨讯与睡前星语两槽位共用（双槽位共享每日 1 条硬上限的认领/回退）。
    """
    try:
        await db.execute(
            update(SubscribeQuota)
            .where(
                SubscribeQuota.user_id == user_id,
                SubscribeQuota.last_sent_date == today,
            )
            .values(last_sent_date=None)
        )
        await db.commit()
    except Exception:
        logger.exception("推送认领回退失败：user=%s", user_id)
        await db.rollback()


async def send_starlight_morning_if_due(
    db: AsyncSession, now: datetime | None = None
) -> dict:
    """7:37 星光晨讯：向「有额度且今天未发过」的用户发送，成功后 quota-1、记 last_sent_date。

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
        - {"status": "not_due"}         未到 7:37，或今天已批量发送过
        - {"status": "no_subscribers"}  无有额度的用户
        - {"status": "sent", "sent": n, "failed": m}  发送完成
    """
    global _morning_sent_date, _last_config_error_date
    if _last_sent_date is None or _morning_sent_date is None:
        _load_state()

    now = (now or datetime.now(BEIJING_TZ)).astimezone(BEIJING_TZ)
    today = now.date()
    today_str = today.isoformat()

    # ── 模板未配置：记 error 日志并跳过（每天只记一次）──
    if not is_template_configured(TEMPLATE_DAILY_CARD):
        if _last_config_error_date != today_str:
            logger.error(
                "7:37 星光晨讯跳过：WX_TEMPLATE_DAILY_CARD 未配置"
                "（请在 .env 配置真实模板 ID 后重启服务）"
            )
            _last_config_error_date = today_str
        return {"status": "skipped_config"}

    # ── 时间与去重 ──
    send_hour, send_minute = _parse_send_time(settings.SEND_TIME)
    if (now.hour, now.minute) < (send_hour, send_minute):
        return {"status": "not_due"}
    if _morning_sent_date == today_str:
        return {"status": "not_due"}

    # ── 有额度、偏好 morning、且今天未发过（last_sent_date IS NULL 或 != 今天）
    #    的用户（T4-3：7:37 只发晨星用户，night 用户留给 21:00 星语）──
    result = await db.execute(
        select(SubscribeQuota, User)
        .join(User, User.id == SubscribeQuota.user_id)
        .where(
            SubscribeQuota.quota_available > 0,
            SubscribeQuota.slot_preference == "morning",
            or_(
                SubscribeQuota.last_sent_date.is_(None),
                SubscribeQuota.last_sent_date != today,
            ),
        )
        .limit(1000)  # 微信单模板每小时上限 1000 条
    )
    rows = list(result.all())
    # ── 失败退避（F-2）：当日已失败 _MAX_ATTEMPTS 次的用户本日不再尝试。
    #    全部用户均达上限时 rows 为空 → 落入 no_subscribers 分支并置批标记，
    #    循环自然停止，直到次日日期变化重置计数。──
    rows = [
        row for row in rows
        if not _is_attempt_exhausted(_morning_fail_counts, row[0].user_id, today_str)
    ]
    if not rows:
        logger.info("7:37 星光晨讯：今日无有额度的用户（或均已达当日重试上限），跳过")
        _morning_sent_date = today_str
        _save_state()
        return {"status": "no_subscribers"}

    template_id = resolve_template_id(TEMPLATE_DAILY_CARD)

    # ── 同类一并修（T1-8 闭环）：晨讯路径与 night 路径同构——循环内
    #    _release_claim 异常路径有 db.rollback() 源，回滚无条件过期会话内
    #    ORM 对象；循环前物化纯值快照，循环体内零 ORM 属性访问。──
    targets = [
        _UserSnapshot(
            id=quota.user_id,
            openid=user.openid,
            zodiac=user.zodiac,
            birth_date=user.birth_date,
            created_at=user.created_at,
            quota_available=quota.quota_available,
        )
        for quota, user in rows
    ]

    sent = 0
    failed = 0
    for target in targets:
        # ── 原子认领（I-1）：并发/崩溃安全。同一用户同一天只可能被一个发送者
        #    认领成功；rowcount==1 才继续发送，否则（已被并发认领/同日已发）
        #    跳过——admin 端点与 7:37 定时任务交错也不会双发。──
        claim = await db.execute(
            update(SubscribeQuota)
            .where(
                SubscribeQuota.user_id == target.id,
                or_(
                    SubscribeQuota.last_sent_date.is_(None),
                    SubscribeQuota.last_sent_date != today,
                ),
            )
            .values(last_sent_date=today)
        )
        if claim.rowcount != 1:
            continue
        try:
            guidance = build_today_guidance(today, target.zodiac or None)
            energy = await _today_energy(db, target, today)
            data = build_starlight_morning_data(today, guidance, energy)
            resp = await send_subscribe_message(
                openid=target.openid,
                template_id=template_id,
                data=data,
                page=MORNING_PAGE,
            )
            if resp.get("errcode") == 0:
                sent += 1
                # 成功：额度减扣与 last_sent_date（认领已置 today）同一事务提交。
                # 逐条 commit —— 中途崩溃只会丢弃未提交的认领，不会整批重发。
                await db.execute(
                    update(SubscribeQuota)
                    .where(
                        SubscribeQuota.user_id == target.id,
                        SubscribeQuota.quota_available > 0,
                    )
                    .values(quota_available=SubscribeQuota.quota_available - 1)
                )
                await db.commit()
            else:
                # 微信 errcode!=0：不扣额度，认领回退为 NULL（允许下次重试），
                # 但记录失败次数——当日达上限后不再尝试（F-2）
                failed += 1
                await _release_claim(db, target.id, today)
                _record_failure(_morning_fail_counts, target.id, today_str)
        except Exception:
            logger.exception("7:37 星光晨讯发送失败：user=%s", target.id)
            failed += 1
            await _release_claim(db, target.id, today)
            _record_failure(_morning_fail_counts, target.id, today_str)

    # 批标记仅作内存级第二道防线：整批无失败才置位（当天不再重扫）；
    # 有失败则保持空，下一轮 5 分钟循环补发失败用户（原子认领保证不重复发送；
    # 失败退避 F-2：当日达 3 次上限的用户会从下一轮选中集中剔除）。
    if failed:
        _morning_sent_date = None
    else:
        _morning_sent_date = today_str
    _save_state()
    logger.info("7:37 星光晨讯完成：sent=%d failed=%d", sent, failed)
    return {"status": "sent", "sent": sent, "failed": failed}


async def send_daily_push_if_due(db: AsyncSession, now: datetime | None = None) -> dict:
    """21:00 睡前星语（T4-3 额度制 + 槽位偏好分流）。

    - 扫描「有额度且今天未发过」的用户：普通日仅 slot_preference==night，
      月相事件日（新月前 1 天 / 满月当天）发**全部**有额度未发用户。
    - 内容：普通日 = 睡前星语（get_today_star_word 写同日缓存 →
      build_star_word_data，page=月光卡）；节点日 = 月相节点文案优先。
    - 与晨讯共用 SubscribeQuota.last_sent_date 原子认领：双槽位共享每日
      最多 1 条硬上限；成功 quota-1 同事务 commit；失败认领回退 + 当日
      失败计数（_night_fail_counts，达 _MAX_ATTEMPTS 次后本日不再尝试）。
    - PushSubscription 不再作为发送依据（存量兼容：仅设置页开关展示数据源）。

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
        - {"status": "not_due"}         未到 21:00，或今天已批量发送过
        - {"status": "no_subscribers"}  无符合条件的用户（或均已达当日重试上限）
        - {"status": "sent", "sent": n, "failed": m}  发送完成
    """
    global _last_sent_date, _last_config_error_date
    if _last_sent_date is None:
        _load_state()

    now = (now or datetime.now(BEIJING_TZ)).astimezone(BEIJING_TZ)
    today = now.date()
    today_str = today.isoformat()

    # ── 模板未配置：记 error 日志并跳过（每天只记一次）──
    if not is_template_configured(TEMPLATE_DAILY_CARD):
        if _last_config_error_date != today_str:
            logger.error(
                "21:00 睡前星语跳过：WX_TEMPLATE_DAILY_CARD 未配置"
                "（请在 .env 配置真实模板 ID 后重启服务）"
            )
            _last_config_error_date = today_str
        return {"status": "skipped_config"}

    # ── 时间与批标记去重 ──
    if now.hour < PUSH_HOUR:
        return {"status": "not_due"}
    if _last_sent_date == today_str:
        return {"status": "not_due"}

    # ── 月相事件优先（开发 04 + T4-3）：命中日节点内容发给全部有额度用户，
    #    节点召回不因槽位偏好丢失；普通日只发 night 偏好用户（星语）。──
    moon_event = get_moon_push_event(today)

    # ── 候选：有额度且今天未发过（last_sent_date IS NULL 或 != 今天）──
    result = await db.execute(
        select(SubscribeQuota, User)
        .join(User, User.id == SubscribeQuota.user_id)
        .where(
            SubscribeQuota.quota_available > 0,
            or_(
                SubscribeQuota.last_sent_date.is_(None),
                SubscribeQuota.last_sent_date != today,
            ),
        )
        .limit(1000)  # 微信单模板每小时上限 1000 条
    )
    rows = list(result.all())
    if moon_event is None:
        # 普通日：21:00 星语只发 night 偏好用户（morning 用户留给 7:37 晨讯）
        rows = [row for row in rows if row[0].slot_preference == "night"]
    # ── 失败退避（F-2）：当日已失败 _MAX_ATTEMPTS 次的用户本日不再尝试。
    #    全部用户均达上限时 rows 为空 → 落入 no_subscribers 分支并置批标记，
    #    循环自然停止，直到次日日期变化重置计数。──
    rows = [
        row for row in rows
        if not _is_attempt_exhausted(_night_fail_counts, row[0].user_id, today_str)
    ]
    if not rows:
        logger.info("21:00 睡前星语：今日无符合条件的用户（或均已达当日重试上限），跳过")
        _last_sent_date = today_str
        _save_state()
        return {"status": "no_subscribers"}

    template_id = resolve_template_id(TEMPLATE_DAILY_CARD)

    # ── T1-8 闭环（方案 b）：循环前把循环内会访问的 ORM 字段物化为纯值快照。
    #    get_today_star_word → _save_cache 并发首写撞 uq_user_word_date 唯一
    #    约束会 db.rollback()，无条件过期会话内所有 ORM 对象（expire_on_commit
    #    =False 只影响 commit 不影响 rollback），async 下惰性加载抛
    #    MissingGreenlet（实证：daily_push.py:544 user.zodiac / 566 user.openid
    #    / 524 quota.user_id）。快照只含纯值，回滚后依然可用；循环体内零 ORM
    #    属性访问，认领/扣减/回退全部用纯值参数。──
    targets = [
        _UserSnapshot(
            id=quota.user_id,
            openid=user.openid,
            zodiac=user.zodiac,
            birth_date=user.birth_date,
            created_at=user.created_at,
            quota_available=quota.quota_available,
        )
        for quota, user in rows
    ]

    sent = 0
    failed = 0
    for target in targets:
        user_id = target.id
        try:
            if moon_event:
                # 节点日：节点文案优先，不发星语（无落库副作用，认领后即可）
                data = build_moon_push_data(moon_event, today)
                page = moon_event["page"]
            else:
                # 星语日：AI 优先 → 短句库兜底 → 同日缓存（写缓存即落库）
                # ── T1-8 认领竞态修复（方案 B）：取星语必须在认领 UPDATE
                #    之前。get_today_star_word 内部 _save_cache 会自行
                #    db.commit()；若在认领之后调用，并发首写撞
                #    uq_user_word_date 唯一约束时 _save_cache 的
                #    db.rollback() 会连带撤销同事务内已写入的
                #    last_sent_date=today（认领被静默回滚）→ 发送成功后
                #    quota-1 但 last_sent_date 仍 NULL → 下轮循环同日
                #    二次推送（quota≥2 时破坏 1 条/天硬上限）。
                #    先取星语（纯 SELECT/缓存优先；AI 全挂有短句库兜底，
                #    star_words 保证总有返回），其 commit/rollback 只作用于
                #    星语缓存事务；缓存落库完成后再开启认领事务，互不影响。
                #    传快照而非 ORM user：其 rollback 即使令 ORM 对象过期，
                #    快照纯值不受影响（Fix round 2）。──
                star = await get_today_star_word(db, target, today)
                guidance = build_today_guidance(today, target.zodiac or None)
                energy = await _today_energy(db, target, today)
                data = build_star_word_data(today, guidance, energy, star["phrase"])
                page = NIGHT_PAGE

            # ── 原子认领（I-1）：与晨讯同款。并发/崩溃交错时同用户同日最多
            #    发 1 条（双槽位共用 last_sent_date —— 已收晨讯者此处 rowcount==0
            #    跳过，两槽位共享每日 1 条硬上限）。──
            claim = await db.execute(
                update(SubscribeQuota)
                .where(
                    SubscribeQuota.user_id == user_id,
                    or_(
                        SubscribeQuota.last_sent_date.is_(None),
                        SubscribeQuota.last_sent_date != today,
                    ),
                )
                .values(last_sent_date=today)
            )
            if claim.rowcount != 1:
                continue
            resp = await send_subscribe_message(
                openid=target.openid,
                template_id=template_id,
                data=data,
                page=page,
            )
            if resp.get("errcode") == 0:
                sent += 1
                # 成功：额度减扣与 last_sent_date（认领已置 today）同一事务提交。
                # 逐条 commit —— 中途崩溃只会丢弃未提交的认领，不会整批重发。
                await db.execute(
                    update(SubscribeQuota)
                    .where(
                        SubscribeQuota.user_id == user_id,
                        SubscribeQuota.quota_available > 0,
                    )
                    .values(quota_available=SubscribeQuota.quota_available - 1)
                )
                await db.commit()
            else:
                # 微信 errcode!=0：不扣额度，认领回退为 NULL（允许下次重试），
                # 但记录失败次数——当日达上限后不再尝试（F-2）
                failed += 1
                await _release_claim(db, user_id, today)
                _record_failure(_night_fail_counts, user_id, today_str)
        except Exception:
            logger.exception("21:00 睡前星语发送失败：user=%s", user_id)
            failed += 1
            await _release_claim(db, user_id, today)
            _record_failure(_night_fail_counts, user_id, today_str)

    # 批标记仅作内存级第二道防线：整批无失败才置位（当天不再重扫）；
    # 有失败则保持空，下一轮 5 分钟循环补发失败用户（原子认领保证不重复发送；
    # 失败退避 F-2：当日达 3 次上限的用户会从下一轮选中集中剔除）。
    if failed:
        _last_sent_date = None
    else:
        _last_sent_date = today_str
    _save_state()
    logger.info("21:00 睡前星语完成：sent=%d failed=%d", sent, failed)
    return {"status": "sent", "sent": sent, "failed": failed}


async def run_daily_push_loop(
    interval_seconds: int = 300,
    stop_event: asyncio.Event | None = None,
) -> None:
    """后台任务：每 5 分钟检查一次两个推送槽位（7:37 星光晨讯 / 21:00 睡前星语）。

    模板未配置时直接退出（记 error 日志），不空转。异常被捕获并记录，
    循环继续，保证推送任务永不崩溃整个服务。
    """
    if not is_template_configured(TEMPLATE_DAILY_CARD):
        logger.error(
            "推送定时任务未启动：WX_TEMPLATE_DAILY_CARD 未配置"
            "（请在 .env 配置真实模板 ID 后重启服务）"
        )
        return

    while True:
        try:
            async with async_session() as db:
                await send_starlight_morning_if_due(db)  # 7:37 星光晨讯（按额度消费）
                await send_daily_push_if_due(db)          # 21:00 睡前星语
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("推送循环异常")

        for _ in range(interval_seconds):
            if stop_event is not None and stop_event.is_set():
                return
            await asyncio.sleep(1)
