from datetime import date
from pydantic import BaseModel, ConfigDict


class DiaryCreate(BaseModel):
    mood: str | None = None
    reflection: str | None = None


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

    model_config = ConfigDict(from_attributes=True)


class DiaryEntryBrief(BaseModel):
    id: str
    date: str
    mood: str | None
    card: DiaryCardBrief | None = None
    reflection: str | None

    model_config = ConfigDict(from_attributes=True)


class DiaryListResponse(BaseModel):
    entries: list[DiaryEntryBrief]
    page: int
