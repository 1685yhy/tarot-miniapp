"""睡前星语服务（SDD P1 · T4-2）：短句库 + 确定性选择器 + AI 生成 + 同日缓存。

用户决策（2026-08-11 确认）：**直接上 AI**（个性化生成，结合当日星光/
能量维度/心情），保留短句库兜底 + 同用户同日缓存 + 生成失败重试上限。

关键设计：
- ``STAR_WORD_POOLS``：4 池 × 13 条（共 52 条），全部治愈系开放积极向、
  ≤20 字、无预测/无评断、无黑名单词（命/运/改运/注定/预测/明天一定会）。
- ``select_fallback_phrase``：纯确定性选择（date_seed + user_seed 对池取模），
  同日同人恒定——与缓存一起构成「同日同人恒定」的双重保证。
- ``generate_star_word_ai``：DeepSeek 生成 ≤20 字星语，system 含
  ``_OUTPUT_RED_LINE``；失败/无 key/输出不合规 → None；重试上限
  ``_AI_MAX_ATTEMPTS``（3 次，线性退避）后落 fallback。
- ``get_today_star_word``：缓存命中即返（不调 AI，成本控制）；否则
  AI 优先 → 失败降级短句库 → 写缓存（``star_word_daily``，source=ai|fallback）。
- ``_today_energy`` / ``_truncate_str`` 为 daily_push 同款逻辑的本地副本：
  T4-3 的推送槽位改造将反向引用本模块，本模块不反向依赖 daily_push，
  避免循环导入。
"""

import asyncio
import json
import logging
from datetime import date, datetime, timezone, timedelta

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.diary import DiaryEntry
from app.models.horoscope import HoroscopeHistory
from app.models.star_word_daily import StarWordDaily
from app.services.ai_engine import _OUTPUT_RED_LINE
from app.services.energy_engine import DIM_NAMES_ZH, build_today_guidance, compute_energy

logger = logging.getLogger(__name__)

# 北京时间 = UTC+8（中国无夏令时，固定偏移即可）
BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_today() -> date:
    """北京时间当日日期（推送/月光卡页面同口径）。"""
    return datetime.now(BEIJING_TZ).date()


# ═══════════════════════════════════════════════════════════════════════
# 短句库（T4-2 · 兜底文案）：4 池 × 13 条 = 52 条
# 全部治愈系开放积极向：只描述心情/意象/小行动，不预测、不评断、不承诺结果；
# ≤20 字；禁词扫描（命/运/改运/注定/预测/明天一定会）全合规（测试钉住）。
# ═══════════════════════════════════════════════════════════════════════

STAR_WORD_POOLS: dict[str, list[str]] = {
    "love": [
        "把今天的疲惫，交给月亮收好。",
        "温柔不必用力，安静地爱自己。",
        "心里的话，说给风听也是回应。",
        "慢一点，感情里的答案会自己浮上来。",
        "先把自己哄开心，再去爱这个世界。",
        "今晚的星光，都在替你说晚安。",
        "想念是温柔的信号，不必急着解决。",
        "心软的时候，记得也对自己心软。",
        "爱不是追赶，是并肩走路时的默契。",
        "睡前原谅今天，醒来再重新喜欢。",
        "那个重要的人，也正在被你好好记得。",
        "感受不需要理由，被理解才需要慢慢来。",
        "把未说出口的话，留给月亮保管。",
    ],
    "career": [
        "把目标拆小，今晚只走一步就好。",
        "休息不是停下，是给明天攒力气。",
        "今天的努力，都算数。",
        "允许进度慢一点，生长本来就不均匀。",
        "把担心写下来，让它在纸上待着。",
        "完成比完美重要，先给自己一个句号。",
        "走神也没关系，回来就好。",
        "把明天的第一件事定小一点。",
        "压力大的时候，先松开握紧的手。",
        "你已经走了很远，别忘了回头看看。",
        "今天解决不了的，明天可以再商量。",
        "让大脑断电，难题明天再看。",
        "方向看不清时，先点亮脚边的一步。",
    ],
    "social": [
        "想联系的人，发一句最近好吗。",
        "一段关系里，先听懂再回应。",
        "独处是充电，不是落单。",
        "让那个让你累的人，暂时休息。",
        "边界感不是冷漠，是温柔的自我保护。",
        "被人惦记的瞬间，记得说谢谢。",
        "朋友不需要多，懂你的一个就够。",
        "沉默的时候，也有人好好陪着你。",
        "把感谢说出口，关系会更暖一点。",
        "允许自己被需要，也允许自己说不。",
        "别人的情绪，不是你的责任。",
        "好的关系，是让彼此都轻松。",
        "今晚和世界保持一点点距离，明天再靠近。",
    ],
    "health": [
        "现在做三次很慢很长的呼吸。",
        "肩膀松开一点，让它在夜里休息。",
        "睡前放下手机，让眼睛看看天花板。",
        "身体累了就躺下，它值得被照顾。",
        "热水澡是今天给身体的奖励。",
        "把难过揉进枕头，明天醒来再收拾。",
        "睡个好觉，是今晚最重要的事。",
        "腿伸直，脚踝转一转，让紧绷散开。",
        "一口温水，也记得喝给身体听。",
        "酸痛是身体的提醒，听它就好。",
        "今晚提前十分钟，躺进被窝里。",
        "伸个懒腰，把白天的重量放下来。",
        "慢慢呼气，让肩膀先落地。",
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# AI 输出黑名单清洗（参照 T1-2 journal._SANITIZE 模式）
# 先短语替换，再移除残留的「命/运」字（红线兜底）；清洗后为空 → 降级
# ═══════════════════════════════════════════════════════════════════════

_SANITIZE_REPLACEMENTS = {
    "命中注定": "自有答案",
    "明天一定会": "明天会",
    "命运": "际遇",
    "命里": "日子里",
    "生命": "生活",
    "注定": "自有答案",
    "预测": "看见",
    "改运": "调整",
    "转运": "调整",
    "运势": "星光",
    "运气": "心情",
}


def _sanitize(text: str) -> str:
    """黑名单词清洗：先短语替换，再移除任何残留的「命/运」字（红线兜底）。"""
    for word, repl in _SANITIZE_REPLACEMENTS.items():
        text = text.replace(word, repl)
    return text.replace("命", "").replace("运", "")


# 情绪中文名（与 diary.py MOOD_LABEL_MAP 同口径；services 层不反向依赖 api 层）
_MOOD_LABELS = {
    "happy": "开心",
    "calm": "平静",
    "excited": "兴奋",
    "anxious": "焦虑",
    "sad": "低落",
    "thoughtful": "思考",
}

# 生成失败重试上限：同日最多 _AI_MAX_ATTEMPTS 次 AI 尝试，之后落 fallback
_AI_MAX_ATTEMPTS = 3
_AI_RETRY_BACKOFF_SECONDS = 1.0


def _truncate_str(value: str, max_len: int = 20) -> str:
    """截断到 max_len（与 daily_push._truncate_str 同款，本地副本防循环导入）。"""
    return value if len(value) <= max_len else value[:max_len]


def _get_ai_client() -> AsyncOpenAI | None:
    """DeepSeek 客户端（与 journal.py / diary.py / wishes.py 同款模式）。"""
    if not settings.DEEPSEEK_API_KEY:
        return None
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


# ═══════════════════════════════════════════════════════════════════════
# 确定性选择器（fallback 兜底）
# ═══════════════════════════════════════════════════════════════════════


def select_fallback_phrase(date_seed: int, user_seed: int, top_dim: str) -> str:
    """确定性选句：``pool[top_dim][(date_seed + user_seed) % len(pool)]``。

    同日同人（date_seed + user_seed 恒定）必得同句；跨日种子变化自然轮换。
    ``top_dim`` 为当日能量最高维度（love/career/social/health）。
    """
    pool = STAR_WORD_POOLS[top_dim]
    return pool[(date_seed + user_seed) % len(pool)]


def _date_seed(today: date) -> int:
    """日期种子：日期数字和（与 build_today_guidance 同口径，确定性）。"""
    return sum(int(ch) for ch in today.isoformat() if ch.isdigit())


def _user_seed(user_id: str) -> int:
    """用户种子：user_id 字符码和（确定性、与日期无关）。"""
    return sum(ord(ch) for ch in user_id)


def _top_dim(energy: dict) -> str:
    """当日能量最高维度；空 dict 防御性回退 love。"""
    return max(energy, key=energy.get) if energy else "love"


# ═══════════════════════════════════════════════════════════════════════
# 当日能量 / 当日心情（daily_push._today_energy 同款取数路径，本地副本）
# ═══════════════════════════════════════════════════════════════════════


async def _today_energy(db: AsyncSession, user, today: date) -> dict:
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


async def _today_mood(db: AsyncSession, user_id: str, today: date) -> str | None:
    """今日心情（DiaryEntry 今日记录，若存在）：mood key（happy/calm/...）。"""
    result = await db.execute(
        select(DiaryEntry.mood)
        .where(DiaryEntry.user_id == user_id, DiaryEntry.entry_date == today)
        .limit(1)
    )
    return result.scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════════
# AI 生成（个性化：当日星光色 / 能量维度 / 心情）
# ═══════════════════════════════════════════════════════════════════════


async def generate_star_word_ai(
    db: AsyncSession,
    user,
    today: date,
    energy: dict,
    today_mood: str | None = None,
) -> str | None:
    """调用 DeepSeek 生成一句 ≤20 字晚安星语；任何失败返回 None（走降级）。

    - system 含 ``_OUTPUT_RED_LINE``（不下确定性断言/不预测）
    - 结合当日星光色 / 能量最高维度 / 今日心情个性化
    - 输出经黑名单清洗 + 截断 20 字；清洗后为空 → None
    - 重试上限 ``_AI_MAX_ATTEMPTS``（3 次，线性退避）
    """
    client = _get_ai_client()  # 无 key → None（走降级）
    if client is None:
        return None

    if today_mood is None:
        today_mood = await _today_mood(db, user.id, today)
    guidance = build_today_guidance(today, user.zodiac or None)
    top_dim = _top_dim(energy)
    mood_label = _MOOD_LABELS.get(today_mood or "", "平静")

    system_prompt = (
        "你是一位温柔的睡前星语伙伴。为用户生成一句 20 字以内的晚安星语："
        "治愈系、积极开放向，只描述心情、意象或一句可以今晚做的事；"
        "不预测、不评断、不承诺结果、不用第二人称说教。"
        "只返回星语正文本身，不要引号、不要前缀、不要解释、不要换行。"
    ) + _OUTPUT_RED_LINE

    user_prompt = (
        f"今天是 {today}。\n"
        f"今日星光色：{guidance['star_color']}。\n"
        f"今日{DIM_NAMES_ZH.get(top_dim, top_dim)}能量最盛（{energy[top_dim]}）。\n"
        f"今日心情：{mood_label}。\n"
        "请结合以上信息，写一句 20 字以内的晚安星语。"
    )

    last_content: str | None = None
    last_exception: Exception | None = None
    for attempt in range(1, _AI_MAX_ATTEMPTS + 1):
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
            if content and content.strip():
                last_content = content
                break
            logger.warning("generate_star_word_ai attempt %d 返回空内容", attempt)
        except Exception as exc:
            last_exception = exc
            logger.warning(
                "generate_star_word_ai attempt %d/%d 失败: %s",
                attempt, _AI_MAX_ATTEMPTS, exc,
            )
        if attempt < _AI_MAX_ATTEMPTS:
            await asyncio.sleep(_AI_RETRY_BACKOFF_SECONDS * attempt)

    if last_content is None:
        logger.warning(
            "generate_star_word_ai 全部 %d 次尝试失败（最后异常: %s），走短句库兜底",
            _AI_MAX_ATTEMPTS, last_exception,
        )
        return None

    word = last_content.strip().strip('"').strip("'").strip("「").strip("」").strip()
    word = _sanitize(word)
    if not word:
        logger.warning("generate_star_word_ai 清洗后为空，走短句库兜底")
        return None
    return _truncate_str(word, 20)


# ═══════════════════════════════════════════════════════════════════════
# 同日缓存（star_word_daily：data=JSON {phrase}，source=ai|fallback）
# ═══════════════════════════════════════════════════════════════════════


async def _load_cache(db: AsyncSession, user_id: str, today: date) -> dict | None:
    """读同日缓存；无缓存或 data 损坏返回 None。"""
    result = await db.execute(
        select(StarWordDaily).where(
            StarWordDaily.user_id == user_id,
            StarWordDaily.word_date == today,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    try:
        data = json.loads(row.data)
    except (ValueError, TypeError):
        return None
    phrase = data.get("phrase") if isinstance(data, dict) else None
    if not phrase:
        return None
    return {"phrase": phrase, "source": row.source}


async def _save_cache(
    db: AsyncSession, user_id: str, today: date, phrase: str, source: str
) -> None:
    """写入/覆盖同日缓存（upsert，幂等）。"""
    result = await db.execute(
        select(StarWordDaily).where(
            StarWordDaily.user_id == user_id,
            StarWordDaily.word_date == today,
        )
    )
    row = result.scalar_one_or_none()
    payload = json.dumps({"phrase": phrase}, ensure_ascii=False)
    if row:
        row.data = payload
        row.source = source
    else:
        db.add(StarWordDaily(
            user_id=user_id, word_date=today, data=payload, source=source,
        ))
    await db.commit()


async def get_today_star_word(db: AsyncSession, user, today: date) -> dict:
    """今日星语：``{phrase, source: "ai"|"fallback"}``。

    - 缓存命中即返（不调 AI，同日同人恒定 + 成本控制）
    - 未命中：AI 优先 → 失败/无 key → 短句库确定性兜底 → 写缓存
    """
    cached = await _load_cache(db, user.id, today)
    if cached is not None:
        return cached

    energy = await _today_energy(db, user, today)
    today_mood = await _today_mood(db, user.id, today)

    phrase = await generate_star_word_ai(db, user, today, energy, today_mood)
    if phrase is None:
        top_dim = _top_dim(energy)
        phrase = select_fallback_phrase(_date_seed(today), _user_seed(user.id), top_dim)
        source = "fallback"
        logger.info("睡前星语降级短句库：user=%s date=%s dim=%s", user.id, today, top_dim)
    else:
        source = "ai"

    await _save_cache(db, user.id, today, phrase, source)
    return {"phrase": phrase, "source": source}


# ═══════════════════════════════════════════════════════════════════════
# 微信模板数据（T4-3 星语推送复用；复用每日一牌模板字段 thing1..thing4）
# ═══════════════════════════════════════════════════════════════════════


def build_star_word_data(
    today: date,
    guidance: dict,
    energy: dict,
    phrase: str,
) -> dict[str, dict[str, str]]:
    """构建睡前星语推送模板数据（thing 字段 20 字符上限）。

    - thing1: 星语（≤20 字）
    - thing2: "星光数 X · 星光色"
    - date3:  日期 "2026.08.11"
    - thing4: "点击收下你的月光卡 ✦"
    """
    star_number = guidance.get("star_number", "")
    star_color = guidance.get("star_color", "")
    return {
        "thing1": {"value": _truncate_str(phrase, 20)},
        "thing2": {"value": _truncate_str(f"星光数 {star_number} · 星光色 {star_color}", 20)},
        "date3": {"value": today.strftime("%Y.%m.%d")},
        "thing4": {"value": "点击收下你的月光卡 ✦"},
    }
