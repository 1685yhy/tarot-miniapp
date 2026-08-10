from pydantic import BaseModel
from typing import Optional


class CheckInResponse(BaseModel):
    signed_in: bool
    streak: int
    reward: str
    reward_type: str = ""
    reward_days: int = 0
    # 星尘/星阶（任务2）：签到成功 stardust_total+1，star_tier 由 stardust_total 推导
    stardust_total: int = 0
    star_tier: int = 0
    star_tier_name: str = ""


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
    # 星尘/星阶（任务2）
    stardust_total: int = 0
    star_tier: int = 0
    star_tier_name: str = ""
