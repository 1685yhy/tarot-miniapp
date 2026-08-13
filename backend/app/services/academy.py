"""星灵学堂服务（SDD P2 阶段3 · T6-1）：学习里程碑表 + 判定 + 发放。

- ``MILESTONES``：5 档里程碑（表驱动，按门槛升序）。判定 = 纯函数
  ``check_milestones``（返回未领里程碑），发放 = ``apply_milestones``
  （星尘加法 + star_tier 同步 + 称号入账 + 壁纸）。
- 幂等双保险：① star_learning_progress.uq_user_card 唯一约束保证同一张卡
  只会 INSERT 成功一次；② users.academy_milestones 账本保证已领里程碑
  不重复发放（仿 journal_streak_reward_week 语义）。
- 星尘加法沿用签到模式（tasks.py：``stardust_total += n; star_tier = tier_for(...)``）；
  壁纸发放复用 star_collectibles.grant_wallpaper 管线。
"""

import json
import logging
from datetime import date, datetime, timezone

from fastapi import HTTPException
from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.card import TarotCard
from app.models.card_teaching import CardTeaching
from app.models.reading import DrawnCard, Reading
from app.models.star_learning_progress import StarLearningProgress
from app.models.user import User
from app.services.ai_engine import _OUTPUT_RED_LINE
from app.services.ai_personas import get_persona_prompt_suffix
from app.services.compliance import AI_OUTPUT_BLACKLIST, find_forbidden
from app.services.daily_card import pick_daily_card
from app.services.stardust import tier_for
from app.services.star_collectibles import grant_wallpaper, parse_json_list
from app.services.star_words import _sanitize
from app.utils.quota import reset_ai_quota_if_new_day

logger = logging.getLogger(__name__)

# 里程碑表（表驱动）：metric 为判定维度（learned 已学总数 / major 大阿卡纳 /
# minor 小阿卡纳），min 为门槛，stardust 为发放星尘；title_name 为称号（全通
# 两档有），wallpaper 为是否解锁星光壁纸。
MILESTONES: list[dict] = [
    {"key": "first_star", "title": "点亮第一颗星", "metric": "learned", "min": 1, "stardust": 1},
    {"key": "seven_stars", "title": "点亮七颗星", "metric": "learned", "min": 7, "stardust": 1},
    {"key": "fool_journey", "title": "完成愚者之旅", "metric": "major", "min": 22, "stardust": 3, "title_name": "星辉学者"},
    {"key": "element_court", "title": "巡礼四元素庭院", "metric": "minor", "min": 56, "stardust": 5},
    {"key": "full_78", "title": "点亮全部 78 颗星", "metric": "learned", "min": 78, "stardust": 10, "title_name": "星光塔罗师", "wallpaper": True},
]

# 里程碑标题 / 称号必须过 compliance 禁词扫描（test_academy 钉住）。
# 注：设计稿「全通封顶 +19」与各档星尘之和（1+1+3+5+10=20）不一致；按逐档
# verbatim 数值实现为 20，如需 19 请将 full_78 调为 +9（详见任务报告附注）。


def _milestone_value(m: dict, learned: int, major: int, minor: int) -> int:
    """取某档里程碑在给定统计下的判定值。"""
    return {"learned": learned, "major": major, "minor": minor}[m["metric"]]


def check_milestones(learned: int, major: int, minor: int, awarded: list[str]) -> list[dict]:
    """纯函数：返回满足门槛且账本中未领的里程碑（按表序升序）。

    - ``learned`` 已学卡牌总数；``major`` 已学大阿卡纳数；``minor`` 已学小阿卡纳数
    - ``awarded`` 账本中已有的 milestone key 列表；已有 key 跳过（幂等）
    """
    return [
        m for m in MILESTONES
        if _milestone_value(m, learned, major, minor) >= m["min"] and m["key"] not in awarded
    ]


def _milestones_awarded_of(user: User) -> list[str]:
    """账本解析（JSON 数组字符串，脏数据安全回退空列表）。"""
    return [k for k in parse_json_list(user.academy_milestones) if isinstance(k, str)]


async def apply_milestones(
    db: AsyncSession, user: User, learned: int, major: int, minor: int
) -> list[dict]:
    """发放所有未领里程碑：星尘加法 + star_tier 同步 + 称号入账 + 壁纸。

    返回实际发放的里程碑列表（[{key, title, stardust_gained, wallpaper_granted}, ...]）。
    账本内已有 key 跳过（幂等锚：academy_milestones + uq_user_card 双保险）。
    星尘加法沿用签到模式（stardust_total += n; star_tier = tier_for(...)）。
    """
    awarded = _milestones_awarded_of(user)
    pending = check_milestones(learned, major, minor, awarded)
    granted: list[dict] = []
    for m in pending:
        user.stardust_total = (user.stardust_total or 0) + m["stardust"]
        user.star_tier = tier_for(user.stardust_total)
        awarded.append(m["key"])
        wallpaper_granted = False
        if m.get("wallpaper"):
            grant_wallpaper(user, date.today().isoformat())
            wallpaper_granted = True
        granted.append({
            "key": m["key"],
            "title": m["title"],
            "stardust_gained": m["stardust"],
            "wallpaper_granted": wallpaper_granted,
        })
    if granted:
        user.academy_milestones = json.dumps(awarded, ensure_ascii=False)
    return granted


# ── 学习计划 · 路径排序 / 下一张 / 关联推荐（SDD P2 阶段3 · T6-2）──────────

# 小阿卡纳花色顺序（suit 英文 / element 中文都兼容；牌库内 suit 为英文）
SUIT_ORDER: dict[str, int] = {
    "wands": 0, "cups": 1, "swords": 2, "pentacles": 3,
    "火": 0, "水": 1, "风": 2, "土": 3,
}

# 路径展示名（设计 1.4 星光叙事）：大阿卡纳=愚者之旅 / 小阿卡纳=四元素庭院 /
# 随机=今日之牌 / 关联=与你相遇的牌（过 compliance 禁词扫描，测试钉住）
PATH_NAMES: dict[str, str] = {
    "major": "愚者之旅",
    "minor": "四元素庭院",
    "random": "今日之牌",
    "related": "与你相遇的牌",
}

# today_card 的 reason（各路径一句话说明）
PATH_REASONS: dict[str, str] = {
    "major": "愚者之旅·按顺序学习",
    "minor": "四元素庭院·按顺序学习",
    "random": "今日之牌·随机星选",
    "related": "与你相遇的牌·按历史抽牌推荐",
}

# 牌库总数（78 张标准塔罗）
DECK_SIZE = 78
MAJOR_SIZE = 22
MINOR_SIZE = 56


def major_cards(cards: list[TarotCard]) -> list[TarotCard]:
    """大阿卡纳（card_number 0-21 升序）。"""
    return sorted((c for c in cards if c.arcana == "major"), key=lambda c: c.card_number)


def minor_cards(cards: list[TarotCard]) -> list[TarotCard]:
    """小阿卡纳（suit 火/水/风/土 + card_number 升序）。"""
    return sorted(
        (c for c in cards if c.arcana == "minor"),
        key=lambda c: (SUIT_ORDER.get(c.suit or "", 99), c.card_number),
    )


def next_card(
    path: str, cursor_pos: int, major: list[TarotCard], minor: list[TarotCard],
    user_id: str, day: date,
) -> tuple[TarotCard, int, bool]:
    """路径内下一张牌 → (card, next_pos, done)。

    - major / minor：顺序路径，cursor 推进；游标越界 → done=True 循环回 0
    - random：与每日一牌 pick_daily_card 同款确定性（同日同人恒定），忽略游标
    - related 不在本函数内（需 DB 历史频次，由 API 层组装后走 pick_related）
    """
    if path == "major":
        return _sequence_next(major, cursor_pos)
    if path == "minor":
        return _sequence_next(minor, cursor_pos)
    if path == "random":
        # 按 id 归并后与 /cards/daily 全牌库口径一致（random：pick_daily_card 同牌）
        deck = sorted(major + minor, key=lambda c: c.id)
        return pick_daily_card(deck, user_id, day), cursor_pos, False
    raise ValueError(f"不支持的路径: {path}")


def _sequence_next(cards: list[TarotCard], cursor_pos: int) -> tuple[TarotCard, int, bool]:
    if not cards:
        raise ValueError("牌库为空")
    if cursor_pos >= len(cards):
        return cards[0], 0, True  # 越界 → 完成态循环回 0
    return cards[cursor_pos], cursor_pos + 1, False


def pick_related(cards: list[TarotCard], counts: dict[int, int]) -> TarotCard | None:
    """候选牌中按历史抽牌频次 TOP 选一张（频次降序；同频 card_number 升序破平）。

    ``cards`` 为未学候选牌；``counts`` 为 {card_id: 历史抽中次数}（来自 readings）。
    从未抽过的牌频次为 0，仍参与排序（保证总有一张「下一张」）。
    """
    ordered = sorted(cards, key=lambda c: (-counts.get(c.id, 0), c.card_number))
    return ordered[0] if ordered else None


def titles_of(user: User) -> list[str]:
    """由里程碑账本（academy_milestones）推导已获称号，按 MILESTONES 表序。"""
    awarded = set(_milestones_awarded_of(user))
    return [m["title_name"] for m in MILESTONES if m.get("title_name") and m["key"] in awarded]


async def learned_card_ids(db: AsyncSession, user_id: str) -> set[int]:
    """已学卡牌 id 集合（related 路径排除用）。"""
    rows = await db.execute(
        select(StarLearningProgress.card_id).where(StarLearningProgress.user_id == user_id)
    )
    return set(rows.scalars().all())


async def reading_frequency(db: AsyncSession, user_id: str) -> dict[int, int]:
    """历史抽牌频次 {card_id: 次数}（related 路径数据源：readings → drawn_cards）。"""
    result = await db.execute(
        select(DrawnCard.card_id, func.count(DrawnCard.card_id))
        .join(Reading, Reading.id == DrawnCard.reading_id)
        .where(Reading.user_id == user_id)
        .group_by(DrawnCard.card_id)
    )
    return dict(result.all())


async def related_next_card(db: AsyncSession, user_id: str, all_cards: list[TarotCard]) -> TarotCard | None:
    """related 路径下一张：历史抽牌频次 TOP 的未学牌。

    全部已学（无候选）→ None，由调用方按「完成态循环回 0」口径回退首张大阿卡纳
    （lesson/next 置 done=True；overview 的 today_card 同口径）。
    """
    learned = await learned_card_ids(db, user_id)
    candidates = [c for c in all_cards if c.id not in learned]
    return pick_related(candidates, await reading_frequency(db, user_id))


# ── 陪学小星 AI 对话（SDD P2 阶段3 · T6-4）─────────────────────────────

# 非会员每日免费陪学对话次数：语义同 settings.FREE_CHAT_MESSAGES（=3），
# 但使用独立计数字段 academy_chat_count_today（与占卜追问 free_chats_today
# 分离互不挤占），日复位复用 quota_reset_date 日复位管线。
ACADEMY_CHAT_DAILY_LIMIT = settings.FREE_CHAT_MESSAGES

# 陪学回复 ≤200 字；同卡同人当日二次提问回前 80 字短版（不重复调 AI 控成本）
ACADEMY_CHAT_MAX_LEN = 200
ACADEMY_CHAT_SHORT_LEN = 80

# AI 失败/无 key 降级文案（不空屏；不消耗配额）
ACADEMY_CHAT_DEGRADED_REPLY = "小星在休息，先看看学习卡吧 ✦"

# 同卡同人当日短版内存缓存：{f"{user_id}:{card_id}": (短版回话, "YYYY-MM-DD")}
# key 不含日期，跨日命中需比对元组第二元素（当日命中口径——同键不同日
# 的旧短版不生效，重新调 AI）。进程级缓存，重启即失（成本控制而非持久化）。
_academy_chat_short: dict[str, tuple[str, str]] = {}


def _get_ai_client() -> AsyncOpenAI | None:
    """DeepSeek 客户端（与 star_words._get_ai_client 同款模式，本地副本）。"""
    if not settings.DEEPSEEK_API_KEY:
        return None
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


def _chat_short_cache_get(user_id: str, card_id: int, today: date) -> str | None:
    """当日短版缓存命中 → 短版回话；无缓存/跨日 → None。"""
    entry = _academy_chat_short.get(f"{user_id}:{card_id}")
    if entry and entry[1] == today.isoformat():
        return entry[0]
    return None


def _chat_short_cache_set(user_id: str, card_id: int, today: date, reply: str) -> None:
    """写入当日短版缓存（存最终 reply 的前 80 字 + 当日日期串）。"""
    _academy_chat_short[f"{user_id}:{card_id}"] = (
        reply[:ACADEMY_CHAT_SHORT_LEN],
        today.isoformat(),
    )


def _chat_remaining(user: User) -> int | None:
    """当日剩余免费陪学次数（含本次）：会员 None；非会员 FREE - 已用。"""
    if user.is_member:
        return None
    return max(0, ACADEMY_CHAT_DAILY_LIMIT - (user.academy_chat_count_today or 0))


def _degraded_chat_result(user: User) -> dict:
    """AI 失败/无 key 降级：固定文案 + 不消耗配额（remaining 按当前计数算）。"""
    return {
        "reply": ACADEMY_CHAT_DEGRADED_REPLY,
        "remaining": _chat_remaining(user),
        "degraded": True,
    }


async def academy_chat(
    db: AsyncSession, user: User, card_id: int, message: str
) -> dict:
    """陪学小星对话 → ``{reply, remaining: int | None, degraded: bool}``。

    流程：日复位（reset_ai_quota_if_new_day）→ 配额校验（非会员
    academy_chat_count_today < FREE_CHAT_MESSAGES，超限 → 402「明天再来」；
    会员不限 remaining=None）→ 读 teaching（无 → 404）→ 当日短版缓存
    （同卡同人二次提问直回前 80 字，不重复调 AI）→ persona=academy_tutor
    + _OUTPUT_RED_LINE（陪学只讲牌意/典故/生活关联，不替用户做决定）→
    AI ≤200 字 → _sanitize + find_forbidden 清洗 → 非会员计数 +1。
    AI 失败/无 key → 降级文案（不空屏、不计数、不缓存）。
    """
    reset_ai_quota_if_new_day(user)
    quota_exhausted = (
        not user.is_member
        and (user.academy_chat_count_today or 0) >= ACADEMY_CHAT_DAILY_LIMIT
    )
    if quota_exhausted:
        raise HTTPException(status_code=402, detail="今天的小星课堂结束啦，明天再来 ✦")

    teaching_result = await db.execute(
        select(CardTeaching).where(CardTeaching.card_id == card_id)
    )
    teaching = teaching_result.scalar_one_or_none()
    if not teaching:
        raise HTTPException(status_code=404, detail="教学数据不存在")

    # 与 quota 复位管线同口径（UTC 日界），保证缓存与配额同一天
    today = datetime.now(timezone.utc).date()
    short = _chat_short_cache_get(user.id, card_id, today)
    if short is not None:
        return {
            "reply": short,
            "remaining": _chat_remaining(user),
            "degraded": False,
        }

    client = _get_ai_client()
    if client is None:
        return _degraded_chat_result(user)

    system_prompt = (
        "你是一位温柔讲学的塔罗陪学伙伴「小星」。本次对话是学习场景："
        "只围绕当前这张牌讲解牌面含义、历史典故与生活关联，回答用户关于"
        "这张牌的提问；不替用户做决定、不对未来做断言——选择权留给用户。"
        "回复 200 字以内，只返回正文，不要前缀、不要解释、不要换行。"
        + get_persona_prompt_suffix("academy_tutor")
        + _OUTPUT_RED_LINE
    )
    user_prompt = (
        f"卡牌 id={card_id} 的教学资料：\n"
        f"牌面符号：{json.dumps(json.loads(teaching.symbols), ensure_ascii=False)}\n"
        f"历史典故：{teaching.story}\n"
        f"生活关联：{teaching.life_connection}\n"
        f"学习关键词：{json.dumps(json.loads(teaching.keywords_learning), ensure_ascii=False)}\n"
        f"用户提问：{message}\n"
        "请以陪学伙伴的口吻回答（200 字以内）。"
    )

    try:
        response = await client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            max_tokens=settings.AI_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=60.0,
        )
        content = response.choices[0].message.content
    except Exception as exc:
        logger.warning("academy_chat AI 调用失败: %s", exc)
        return _degraded_chat_result(user)

    if not content or not content.strip():
        logger.warning("academy_chat AI 返回空内容，走降级")
        return _degraded_chat_result(user)

    reply = content.strip().strip('"').strip("'").strip("「").strip("」").strip()
    reply = _sanitize(reply[:ACADEMY_CHAT_MAX_LEN])
    if not reply or find_forbidden(reply, AI_OUTPUT_BLACKLIST):
        # 清洗后为空 / 仍残留红线词（理论上 _sanitize 已字符级清干净）→ 降级兜底
        logger.warning("academy_chat AI 输出清洗后仍不合规，走降级")
        return _degraded_chat_result(user)

    remaining = _chat_remaining(user)  # 先算剩余（含本次），再计数
    if not user.is_member:
        user.academy_chat_count_today = (user.academy_chat_count_today or 0) + 1

    _chat_short_cache_set(user.id, card_id, today, reply)

    return {
        "reply": reply,
        "remaining": remaining,
        "degraded": False,
    }
