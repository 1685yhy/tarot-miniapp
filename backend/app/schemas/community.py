from datetime import date, datetime
from pydantic import BaseModel, Field


class TopicResponse(BaseModel):
    id: int
    date: str
    title: str
    description: str
    card_id: int | None = None

    class Config:
        from_attributes = True


class PostResponse(BaseModel):
    id: int
    topic_id: int
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class PostCreate(BaseModel):
    topic_id: int = Field(..., description="Topic to post under")
    content: str = Field(..., min_length=1, max_length=500, description="Anonymous post content")


class CommunityTodayResponse(BaseModel):
    topic: TopicResponse
    post_count: int = 0


class PostListResponse(BaseModel):
    posts: list[PostResponse]
    page: int
    total: int
    has_more: bool
