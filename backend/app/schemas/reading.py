from datetime import datetime

from pydantic import BaseModel


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Request ──────────────────────────────────────────────────────────


class CreateReadingRequest(BaseModel):
    question: str | None = None
    theme: str | None = None  # love / career / finance / general


# ── Response ─────────────────────────────────────────────────────────


class DrawnCardResponse(BaseModel):
    id: int
    card_id: int
    card_name: str
    position: int
    position_name: str
    is_reversed: bool


class ReadingResponse(BaseModel):
    id: str
    spread_type: str
    question: str | None
    theme: str | None
    interpretation: str | None
    is_paid: bool
    created_at: datetime
    drawn_cards: list[DrawnCardResponse]
    chat_messages: list[ChatMessageResponse] = []

    class Config:
        from_attributes = True


class ReadingHistoryItem(BaseModel):
    id: str
    spread_type: str
    question: str | None
    theme: str | None
    interpretation: str | None
    is_paid: bool
    created_at: datetime
    # First card summary so the list view has something to show
    first_card_name: str | None = None
    first_card_is_reversed: bool | None = None

    class Config:
        from_attributes = True


class ReadingHistoryResponse(BaseModel):
    total: int
    items: list[ReadingHistoryItem]
