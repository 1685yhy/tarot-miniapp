"""星灵学堂 schema（SDD P2 阶段3 · T6-1）：学习 / 复习 / 里程碑 / 学习卡页。"""

from pydantic import BaseModel


class LearnedRequest(BaseModel):
    card_id: int


class MilestoneInfo(BaseModel):
    key: str
    title: str
    stardust_gained: int
    wallpaper_granted: bool


class LearnedResponse(BaseModel):
    ok: bool
    learned: bool
    review_count: int
    milestone: MilestoneInfo | None = None


class ReviewRequest(BaseModel):
    card_id: int


class ReviewResponse(BaseModel):
    ok: bool
    review_count: int


class LessonCard(BaseModel):
    id: int
    name_zh: str
    arcana: str
    suit: str | None
    card_number: int
    image_url: str


class LessonTeaching(BaseModel):
    symbols: list[dict]
    story: str
    keywords_learning: list[str]
    life_connection: str
    element_association: str


class MyProgress(BaseModel):
    learned: bool
    review_count: int


class LessonResponse(BaseModel):
    card: LessonCard
    teaching: LessonTeaching
    my: MyProgress | None = None
