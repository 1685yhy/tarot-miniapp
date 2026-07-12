from pydantic import BaseModel, ConfigDict


class CardBrief(BaseModel):
    id: int
    name_zh: str
    name_en: str
    card_number: int
    arcana: str
    suit: str | None
    element: str | None
    keywords_upright: str | None = None
    meaning_upright: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CardDetail(CardBrief):
    image_description: str
    keywords_upright: str
    keywords_reversed: str
    meaning_upright: str
    meaning_reversed: str
    love_upright: str
    love_reversed: str
    career_upright: str
    career_reversed: str
    finance_upright: str
    finance_reversed: str
    health_upright: str
    health_reversed: str


class CardListResponse(BaseModel):
    total: int
    cards: list[CardBrief]
