from datetime import date
from pydantic import BaseModel, ConfigDict


class DiaryCreate(BaseModel):
    mood: str | None = None
    reflection: str | None = None
    card_id: int | None = None  # allow frontend to specify associated card
    image_url: str | None = None  # uploaded image URL for this entry


class DiaryCardBrief(BaseModel):
    id: int
    name_zh: str
    meaning_upright: str

    model_config = ConfigDict(from_attributes=True)


class DiaryEntryResponse(BaseModel):
    id: str
    date: str
    mood: str | None
    card: DiaryCardBrief | None = None
    reflection: str | None
    image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DiaryEntryBrief(BaseModel):
    id: str
    date: str
    mood: str | None
    card: DiaryCardBrief | None = None
    reflection: str | None
    image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DiaryListResponse(BaseModel):
    entries: list[DiaryEntryBrief]
    page: int


class DiarySharePreview(BaseModel):
    """Anonymized diary data for share posters.

    Contains only share-safe fields — no nickname, no user_id, no raw
    reflection beyond the 200-char excerpt.
    """

    date: str
    mood: str | None
    mood_emoji: str
    excerpt: str
    card: DiaryCardBrief | None = None


class WeeklyMoodTrend(BaseModel):
    date: str
    mood_score: float
    mood_label: str
    mood_emoji: str


class DiaryReviewResponse(BaseModel):
    period: str = "weekly"
    week_range: str | None = None
    entry_count: int = 0
    mood_trends: list[WeeklyMoodTrend] = []
    top_card_name: str | None = None
    top_card_count: int = 0
    top_card_meaning: str | None = None
    ai_insight: str | None = None
    next_week_guidance: str | None = None
    emotional_trend_summary: str | None = None
