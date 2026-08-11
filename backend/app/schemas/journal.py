"""星光手账（Journal）接口 schemas —— T1-1 月历聚合。"""

from pydantic import BaseModel


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
