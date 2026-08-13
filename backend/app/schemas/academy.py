"""星灵学堂 schema（SDD P2 阶段3 · T6-1/2/4）：学习 / 复习 / 里程碑 / 学习卡页 / 学习计划 / 概览 / 陪学对话。"""

from typing import Literal

from pydantic import BaseModel, Field


class LearnedRequest(BaseModel):
    card_id: int


class MilestoneInfo(BaseModel):
    key: str
    title: str
    stardust_gained: int
    wallpaper_granted: bool


class LearnedResponse(BaseModel):
    ok: bool
    learned: bool
    review_count: int
    milestone: MilestoneInfo | None = None


class ReviewRequest(BaseModel):
    card_id: int


class ReviewResponse(BaseModel):
    ok: bool
    review_count: int


class LessonCard(BaseModel):
    id: int
    name_zh: str
    arcana: str
    suit: str | None
    card_number: int
    image_url: str


class LessonTeaching(BaseModel):
    symbols: list[dict]
    story: str
    keywords_learning: list[str]
    life_connection: str
    element_association: str


class MyProgress(BaseModel):
    learned: bool
    review_count: int


class LessonResponse(BaseModel):
    card: LessonCard
    teaching: LessonTeaching
    my: MyProgress | None = None


# ── T6-2 学习计划 / 下一张 / 学堂概览 ──────────────────────────────────

PlanPath = Literal["major", "minor", "random", "related"]
CardsPerDay = Literal[0, 1, 3, 5]


class PlanRequest(BaseModel):
    """学习计划写入：cards_per_day 只允许 0|1|3|5（0=关闭）；path 四选一；
    reminder_on 默认关闭（学习提醒默认关）。"""

    cards_per_day: CardsPerDay
    reminder_on: bool = False
    path: PlanPath


class PlanResponse(BaseModel):
    """学习计划回显（GET 无 quota_warning；无行默认 {0, false, "major", 0}）。"""

    cards_per_day: int
    reminder_on: bool
    path: str
    cursor_pos: int


class PlanSetResponse(PlanResponse):
    """POST /academy/plan 回显 + quota_warning（提醒开启但无订阅额度时 true，
    仅引导授权不硬拦）。"""

    quota_warning: bool


class NextLessonResponse(BaseModel):
    """路径内下一张：card + 推进后的游标 + done（越界/无未学 → done=true 回 0）。"""

    card_id: int
    name_zh: str
    path: str
    next_pos: int
    done: bool


class PathStat(BaseModel):
    """单路径进度（random/related 无固定总数 → total=null）。"""

    learned: int
    total: int | None = None


class PathsStats(BaseModel):
    major: PathStat
    minor: PathStat
    random: PathStat
    related: PathStat


class TodayCard(BaseModel):
    """今日学习卡（计划路径派生：random 按日确定性；related 按历史抽牌 TOP）。"""

    card_id: int
    name_zh: str
    reason: str


class OverviewResponse(BaseModel):
    """学堂主页：总进度 + 四路径进度 + 已获称号 + 今日学习卡。"""

    total: int
    learned: int
    percent: int
    paths: PathsStats
    titles: list[str]
    today_card: TodayCard | None = None


# ── T6-4 陪学小星 AI 对话 ──────────────────────────────────────────────


class ChatRequest(BaseModel):
    """陪学提问：card_id + message（message 空 → 422）。

    message 只做长度下限校验（min_length=1），与 community/wish 文案字段同款；
    超长由 max_length 拦截（教学上下文对话，500 字足够）。
    """

    card_id: int
    message: str = Field(..., min_length=1, max_length=500)


class ChatResponse(BaseModel):
    """陪学回答：reply + remaining（会员 None）+ degraded（AI 失败降级标记）。

    remaining = 当日剩余免费陪学次数（含本次）：非会员 3→2→1 递减；会员不限
    （None）。degraded=true 时 reply 为固定降级文案（不空屏、不消耗配额）。
    """

    reply: str
    remaining: int | None
    degraded: bool
