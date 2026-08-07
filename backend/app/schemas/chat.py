from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    """A single actionable suggestion extracted from the AI response."""

    id: str
    content: str
    category: str  # love / career / general


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=5000, description="追问内容，最长 5000 字")


class ChatResponse(BaseModel):
    reply: str
    remaining_free: int
    action_items: list[ActionItem] = []
