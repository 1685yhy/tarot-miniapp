"""星座能量接口 Schema。"""
from pydantic import BaseModel


class Factor(BaseModel):
    name: str
    delta: int


class AstralInfo(BaseModel):
    type: str
    label: str
    note: str


class TarotBrief(BaseModel):
    name: str
    name_en: str
    image: str


class DailyHoroscopeResponse(BaseModel):
    date: str
    zodiac: str | None
    energy: dict[str, int]
    factors: dict[str, list[Factor]]
    astral: AstralInfo
    tarot: TarotBrief | None
    summary: str
    tip: str


class ZodiacUpdate(BaseModel):
    zodiac: str


class BirthUpdate(BaseModel):
    birth_date: str | None = None
    birth_time: str | None = None
    birth_city: str | None = None


class ProfileUpdateResponse(BaseModel):
    ok: bool = True
    zodiac: str | None = None
    birth_date: str | None = None
    birth_time: str | None = None
    birth_city: str | None = None
