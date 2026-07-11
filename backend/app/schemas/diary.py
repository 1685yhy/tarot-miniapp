from datetime import date
from pydantic import BaseModel


class DiaryCreate(BaseModel):
    mood: str | None = None
    reflection: str | None = None


class DiaryCardBrief(BaseModel):
    id: int
    name_zh: str
    meaning_upright: str

    class Config:
        from_attributes = True


class DiaryEntryResponse(BaseModel):
    id: str
    date: str
    mood: str | None
    card: DiaryCardBrief | None = None
    reflection: str | None

    class Config:
        from_attributes = True


class DiaryEntryBrief(BaseModel):
    id: str
    date: str
    mood: str | None
    card: DiaryCardBrief | None = None
    reflection: str | None

    class Config:
        from_attributes = True


class DiaryListResponse(BaseModel):
    entries: list[DiaryEntryBrief]
    page: int
