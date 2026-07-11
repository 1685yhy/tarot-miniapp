from datetime import datetime

from pydantic import BaseModel


# ── Request ──────────────────────────────────────────────────────────


class CreateReadingRequest(BaseModel):
    spread_type: str  # daily / three_card / triangle / career / etc.
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
    readings: list[ReadingHistoryItem]
