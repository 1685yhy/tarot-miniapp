"""星象月报 schemas（SDD P2 · T7-1 周报端点）。"""

from typing import Union

from pydantic import BaseModel, Field

WEEK_PERIOD_PATTERN = r"^\d{4}-W\d{2}$"


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
