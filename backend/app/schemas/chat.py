from pydantic import BaseModel


class ActionItem(BaseModel):
    """A single actionable suggestion extracted from the AI response."""

    id: str
    content: str
    category: str  # love / career / general


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    remaining_free: int
    action_items: list[ActionItem] = []
