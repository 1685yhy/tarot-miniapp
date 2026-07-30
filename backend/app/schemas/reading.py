from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Request ──────────────────────────────────────────────────────────


class CreateReadingRequest(BaseModel):
    question: str | None = None
    theme: str | None = None  # love / career / finance / general
    persona: str | None = None  # gentle_star / wise_moon / frank_sun
    zodiac: str | None = None  # aries / taurus / gemini / cancer / leo / virgo / libra / scorpio / sagittarius / capricorn / aquarius / pisces
    depth: str | None = "standard"  # NEW: "basic" | "standard" | "deep"


# ── Response ─────────────────────────────────────────────────────────


class ActionItem(BaseModel):
    """A single actionable suggestion extracted from the AI reading."""

    id: str
    content: str
    category: str  # love / career / general


class TeachingData(BaseModel):
    symbols: list[dict] = []
    life_connection: str = ""


class DrawnCardResponse(BaseModel):
    id: int
    card_id: int
    card_name: str
    name_en: str
    arcana: str
    suit: str | None = None
    card_number: int
    position: int
    position_name: str
    is_reversed: bool
    teaching: TeachingData | None = None


class ReadingResponse(BaseModel):
    id: str
    spread_type: str
    question: str | None
    theme: str | None
    persona: str | None = None
    interpretation: str | None
    is_paid: bool
    created_at: datetime
    drawn_cards: list[DrawnCardResponse]
    action_items: list[ActionItem] = []
    chat_messages: list[ChatMessageResponse] = []
    reflection_question: str | None = None  # NEW: AI-generated reflection question
    depth: str | None = "standard"  # NEW: reading depth (basic / standard / deep)

    model_config = ConfigDict(from_attributes=True)


class ReadingHistoryItem(BaseModel):
    id: str
    spread_type: str
    question: str | None
    theme: str | None
    persona: str | None = None
    interpretation: str | None
    is_paid: bool
    created_at: datetime
    # First card summary so the list view has something to show
    first_card_name: str | None = None
    first_card_is_reversed: bool | None = None
    depth: str | None = None
    reflection_question: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ReadingHistoryResponse(BaseModel):
    total: int
    items: list[ReadingHistoryItem]
