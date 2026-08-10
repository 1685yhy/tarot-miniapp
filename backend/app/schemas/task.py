from pydantic import BaseModel
from typing import Optional


class CollectibleInfo(BaseModel):
    """里程碑收藏品信息（P0-3：稀有星卡 / 星光壁纸），不消耗任何额度。"""
    card_id: Optional[int] = None
    card_name: str = ""
    card_name_en: str = ""
    date: str = ""
    tier: str = ""          # "gold" = 稀有星卡（正位金卡）
    orientation: str = ""   # "upright" 正位 / "reversed" 逆位


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
    # 收藏品里程碑（P0-3 缺口1）：collectible_type ∈ {"", "star_card", "wallpaper"}
    collectible_type: str = ""
    collectible: Optional[CollectibleInfo] = None


class LevelInfo(BaseModel):
    current_level: str
    next_level: str
    days_needed: int
    progress: int  # days remaining to next level


class StarCardItem(BaseModel):
    """我的页星卡收藏区数据（含牌名，前端直接渲染）。"""
    card_id: int
    card_name: str = ""
    card_name_en: str = ""
    date: str
    tier: str = "gold"
    orientation: str = "upright"


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
    # 星卡收藏 / 星光壁纸（P0-3 缺口1）
    star_cards: list[StarCardItem] = []
    wallpapers: list[str] = []
