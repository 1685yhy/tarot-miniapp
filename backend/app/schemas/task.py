from pydantic import BaseModel
from typing import Optional


class CheckInResponse(BaseModel):
    signed_in: bool
    streak: int
    reward: str
    reward_type: str = ""
    reward_days: int = 0


class LevelInfo(BaseModel):
    current_level: str
    next_level: str
    days_needed: int
    progress: int  # days remaining to next level


class TaskStatusResponse(BaseModel):
    checked_in_today: bool
    streak: int
    level: LevelInfo
    daily_card_drawn: bool
    reading_done_today: bool
    shared_today: bool
    tasks_completed: int
    tasks_total: int
