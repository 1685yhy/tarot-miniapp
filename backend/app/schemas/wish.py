"""新月许愿 + 满月复盘 的请求/响应模型。"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

# 愿望状态枚举（与 models/wish.py 一致）
WISH_STATUS_ACTIVE = "active"
WISH_STATUS_GROWN = "grown"
WISH_STATUS_ANSWERED = "answered"
WISH_STATUSES = {WISH_STATUS_ACTIVE, WISH_STATUS_GROWN, WISH_STATUS_ANSWERED}

# 每个用户同时「生长中」的愿望上限
MAX_ACTIVE_WISHES = 10
# 愿望内容长度上限
WISH_CONTENT_MAX = 100


class WishCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=WISH_CONTENT_MAX, description="愿望内容，1~100 字")


class WishUpdate(BaseModel):
    status: Literal["active", "grown", "answered"]


class WishResponse(BaseModel):
    id: str
    content: str
    status: str
    moon_phase: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class WishListResponse(BaseModel):
    wishes: list[WishResponse]
    total: int
    active_count: int


class WishBlessResponse(BaseModel):
    id: str
    blessing: str


class MoonPhaseResponse(BaseModel):
    date: str
    phase: str
    emoji: str
    label: str
    age_days: float
    next_new_moon: str
    next_full_moon: str


class MoonReviewWishItem(BaseModel):
    content: str
    status: str
    note: str


class MoonReviewResponse(BaseModel):
    date: str
    date_range: str
    wishes: list[MoonReviewWishItem] = []
    review: str = ""
    tips: list[str] = []
    has_data: bool = False
    cached: bool = False
