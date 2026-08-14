"""星象月报 schemas（SDD P2 · T7-1 周报 + T7-2 月报端点）。"""

from typing import Union

from pydantic import BaseModel, Field

WEEK_PERIOD_PATTERN = r"^\d{4}-W\d{2}$"
MONTH_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class WeekCurvePoint(BaseModel):
    """星运曲线单日点（无记录日 total=None）。"""

    date: str
    total: int | None


class WeekStardust(BaseModel):
    """本周星尘行为统计（估算口径：签到天数 + 节点活动事件数）。"""

    checkin_days: int
    activity_events: int
    total: int


class WeekCardCount(BaseModel):
    """牌运单牌统计。"""

    name: str
    count: int


class WeekCardStat(WeekCardCount):
    """最常牌（含关键词）。"""

    keywords: list[str] = Field(default_factory=list)


class WeekCards(BaseModel):
    """牌运回顾。"""

    readings_count: int
    most_card: WeekCardStat | None
    card_list: list[WeekCardCount]


class WeekColorBand(BaseModel):
    """星光色带单日色点。"""

    date: str
    star_color: str


class WeekReport(BaseModel):
    """周报全文（会员）。"""

    curve: list[WeekCurvePoint]
    stardust: WeekStardust
    cards: WeekCards
    color_band: list[WeekColorBand]
    note: str


class WeekPreview(BaseModel):
    """周报预览（非会员）：曲线 + 1 段寄语。"""

    curve: list[WeekCurvePoint]
    note: str


class WeekReportResponse(BaseModel):
    """GET /report/week 响应。"""

    period: str
    week_range: list[str]
    report: Union[WeekReport, WeekPreview]
    locked: bool
    preview: bool
    cached: bool
    source: str | None


# ═══════════════════════════════════════════════════════════════════════
# 月报（T7-2）
# ═══════════════════════════════════════════════════════════════════════


class MonthAstralEvent(BaseModel):
    """月度天象事件（日历事实，零 AI）。"""

    type: str
    label: str
    date: str


class MonthJournal(BaseModel):
    """星光手账汇总（直接引用 star_monthly_reviews 缓存）。"""

    active_days: int
    bright_ratio: float
    trend: str


class MonthCards(BaseModel):
    """牌运回顾：月度占卜次数 + TOP3 牌。"""

    readings_count: int
    top3: list[WeekCardCount]


class MonthStardust(BaseModel):
    """星尘与星阶：当月行为可得星尘（估算口径）+ 当前星阶名。"""

    estimated: int
    tier_name: str


class MonthOutlookEvent(BaseModel):
    """下月展望单事件（仅真实天象日期）。"""

    type: str
    label: str
    date: str


class MonthOutlook(BaseModel):
    """下月展望（活动预告非运势预测）。"""

    first_new_moon: MonthOutlookEvent | None
    first_full_moon: MonthOutlookEvent | None
    first_retrograde: MonthOutlookEvent | None
    tips: list[str]


class MonthReport(BaseModel):
    """月报全文（会员）。"""

    astral_events: list[MonthAstralEvent]
    journal: MonthJournal | None
    cards: MonthCards
    stardust: MonthStardust
    outlook: MonthOutlook
    note: str


class MonthPreview(BaseModel):
    """月报预览（非会员）：天象目录（封面+目录）+ 1 段总评。"""

    astral_events: list[MonthAstralEvent]
    note: str


class MonthReportResponse(BaseModel):
    """GET /report/month 响应。"""

    period: str
    month_range: list[str]
    report: Union[MonthReport, MonthPreview]
    locked: bool
    preview: bool
    cached: bool
    source: str | None


class MonthPosterCoreNumbers(BaseModel):
    """海报 3 核心数字（脱敏：无原文统计明细）。"""

    active_days: int
    readings_count: int
    stardust_estimated: int


class MonthPosterResponse(BaseModel):
    """GET /report/month/poster 响应（T7-4 · 脱敏海报数据）。

    报告期 + 星阶名 + 3 核心数字 + AI 寄语一句（截断 40 字）+ 固定分享文案；
    无昵称、无原文统计明细、无手账内容。
    """

    period: str
    tier_name: str
    core_numbers: MonthPosterCoreNumbers
    ai_sentence: str
    share_text: str
    disclaimer: str
