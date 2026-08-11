"""星空时刻表（SDD P1 · T3-1）的请求/响应模型。"""

from pydantic import BaseModel, Field


class PhaseInfo(BaseModel):
    """月相小字（每日本来就有）。"""

    phase: str
    emoji: str
    label: str


class DayEventBrief(BaseModel):
    """月视图中的事件简卡。"""

    type: str
    label: str
    moon_sign: str | None = None


class CalendarDay(BaseModel):
    date: str
    phase: PhaseInfo
    events: list[DayEventBrief] = Field(default_factory=list)
    is_retrograde_range: bool = False


class NextEvent(BaseModel):
    type: str
    label: str
    date: str
    days_until: int


class MonthViewResponse(BaseModel):
    year: int
    month: int
    days: list[CalendarDay]
    next_event: NextEvent | None = None


class DayEventDetail(BaseModel):
    """日详情中的事件卡。"""

    type: str
    label: str
    note: str


class Guidance(BaseModel):
    do: str
    dont: str


class DayDetailResponse(BaseModel):
    date: str
    events: list[DayEventDetail] = Field(default_factory=list)
    guidance: Guidance
    activity: str  # wish | review | mercury_guide | info


class WishCounts(BaseModel):
    active: int = 0
    grown: int = 0
    answered: int = 0


class WishWindow(BaseModel):
    start: str
    end: str
    days_left: int


class RetrogradeRange(BaseModel):
    start: str
    end: str
    days_left: int


class NodeContentResponse(BaseModel):
    """节点内容四形态共用的宽松模型（响应时剔除 None 字段）。

    - wish: type/title/window/content/target_page/wish_counts
    - review: type/title/wish_counts/target_page
    - mercury_guide: type/title/range/items/daily_sentence（range 键恒在；
      无逆行期时为空对象 {start:"", end:"", days_left:0}，见 EMPTY_RETROGRADE_RANGE）
    - info: type/notes
    """

    type: str
    title: str | None = None
    window: WishWindow | None = None
    content: str | None = None
    target_page: str | None = None
    wish_counts: WishCounts | None = None
    range: RetrogradeRange | None = None
    items: list[str] = Field(default_factory=list)
    daily_sentence: str | None = None
    notes: list[str] = Field(default_factory=list)
