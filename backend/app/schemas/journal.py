"""星光手账（Journal）接口 schemas —— T1-1 月历聚合 + T1-2 月度复盘 + T1-3 记录。"""

from typing import Literal

from pydantic import BaseModel, Field

# 6 档情绪枚举（与 diary.py / services.journal.MOOD_BRIGHTNESS 同口径）
JournalMood = Literal["happy", "calm", "excited", "anxious", "sad", "thoughtful"]


class JournalDay(BaseModel):
    """月历上某一天（仅记录过的天；star_color 由日期确定性生成，不落库）。"""

    date: str
    mood: str | None
    brightness: int
    star_color: str
    has_reflection: bool
    card_id: int | None = None


class JournalStats(BaseModel):
    """月度统计。"""

    days_recorded: int
    bright_count: int
    dim_count: int
    current_streak: int


class JournalCalendarResponse(BaseModel):
    """GET /journal/calendar 响应。"""

    days: list[JournalDay]
    stats: JournalStats


# ── T1-2 月度星光复盘 ────────────────────────────────────────────────────

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class JournalReviewStats(BaseModel):
    """月度复盘统计（含亮暗比例；无 current_streak，口径与 /calendar 不同）。"""

    days_recorded: int
    bright_count: int
    dim_count: int
    bright_ratio: float


class JournalReviewMoodPoint(BaseModel):
    """mood_series 单点：当日情绪 + 星光亮度。"""

    date: str
    mood: str | None
    brightness: int


class JournalStarColorCount(BaseModel):
    """星光色统计（本月星空色带）。"""

    color: str
    count: int


class JournalTopCard(BaseModel):
    """当月出现最多的卡牌。"""

    name: str
    count: int


class JournalReviewResponse(BaseModel):
    """GET /journal/review 响应。

    ``cached`` 标记是否命中缓存（命中不消耗 AI 配额）；缓存内 data 另有
    ``source``（ai/fallback）字段标记生成来源，接口不对外暴露。
    """

    month: str
    stats: JournalReviewStats
    mood_series: list[JournalReviewMoodPoint]
    star_color_counts: list[JournalStarColorCount]
    top_cards: list[JournalTopCard]
    trend_summary: str
    insight: str | None = None
    next_guide: str | None = None
    cached: bool


class JournalReviewRegenerateRequest(BaseModel):
    """POST /journal/review/regenerate 请求体。"""

    month: str = Field(..., pattern=MONTH_PATTERN)


class JournalSharePreviewResponse(BaseModel):
    """GET /journal/review/share-preview 响应（脱敏：无昵称、无日记原文）。"""

    month: str
    stats: JournalReviewStats
    star_color_counts: list[JournalStarColorCount]
    summary: str


# ── T1-3 手账记录（POST /journal/entries）────────────────────────────────

class JournalEntryCreate(BaseModel):
    """POST /journal/entries 请求体。

    mood 必填（6 档枚举，非法/缺失 422）；card_id 缺省时随机取一张。
    """

    mood: JournalMood
    reflection: str | None = Field(None, max_length=2000, description="今日感悟，最长 2000 字")
    card_id: int | None = Field(None, description="指定卡牌；缺省随机取一张")


class JournalCardBrief(BaseModel):
    """手账记录响应中的卡牌摘要。"""

    id: int
    name_zh: str
    meaning_upright: str


class JournalEntryResponse(BaseModel):
    """POST /journal/entries 响应：今日星点 + 连续记录 + 奖励标记。

    - brightness：6 档情绪 → 5 档星光亮度（services.journal 常量）
    - star_color：由日期（+星座）确定性生成，不落库
    - streak：以今天为锚的连续记录天数
    - reward：本次写入是否触发「连续 7 天」星尘奖励（+1 星尘，同周只发一次）
    """

    id: str
    date: str
    mood: str
    brightness: int
    star_color: str
    card: JournalCardBrief | None = None
    reflection: str | None = None
    streak: int
    reward: bool
