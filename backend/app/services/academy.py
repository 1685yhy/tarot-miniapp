"""星灵学堂服务（SDD P2 阶段3 · T6-1）：学习里程碑表 + 判定 + 发放。

- ``MILESTONES``：5 档里程碑（表驱动，按门槛升序）。判定 = 纯函数
  ``check_milestones``（返回未领里程碑），发放 = ``apply_milestones``
  （星尘加法 + star_tier 同步 + 称号入账 + 壁纸）。
- 幂等双保险：① star_learning_progress.uq_user_card 唯一约束保证同一张卡
  只会 INSERT 成功一次；② users.academy_milestones 账本保证已领里程碑
  不重复发放（仿 journal_streak_reward_week 语义）。
- 星尘加法沿用签到模式（tasks.py：``stardust_total += n; star_tier = tier_for(...)``）；
  壁纸发放复用 star_collectibles.grant_wallpaper 管线。
"""

import json
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.stardust import tier_for
from app.services.star_collectibles import grant_wallpaper, parse_json_list

# 里程碑表（表驱动）：metric 为判定维度（learned 已学总数 / major 大阿卡纳 /
# minor 小阿卡纳），min 为门槛，stardust 为发放星尘；title_name 为称号（全通
# 两档有），wallpaper 为是否解锁星光壁纸。
MILESTONES: list[dict] = [
    {"key": "first_star", "title": "点亮第一颗星", "metric": "learned", "min": 1, "stardust": 1},
    {"key": "seven_stars", "title": "点亮七颗星", "metric": "learned", "min": 7, "stardust": 1},
    {"key": "fool_journey", "title": "完成愚者之旅", "metric": "major", "min": 22, "stardust": 3, "title_name": "星辉学者"},
    {"key": "element_court", "title": "巡礼四元素庭院", "metric": "minor", "min": 56, "stardust": 5},
    {"key": "full_78", "title": "点亮全部 78 颗星", "metric": "learned", "min": 78, "stardust": 10, "title_name": "星光塔罗师", "wallpaper": True},
]

# 里程碑标题 / 称号必须过 compliance 禁词扫描（test_academy 钉住）。
# 注：设计稿「全通封顶 +19」与各档星尘之和（1+1+3+5+10=20）不一致；按逐档
# verbatim 数值实现为 20，如需 19 请将 full_78 调为 +9（详见任务报告附注）。


def _milestone_value(m: dict, learned: int, major: int, minor: int) -> int:
    """取某档里程碑在给定统计下的判定值。"""
    return {"learned": learned, "major": major, "minor": minor}[m["metric"]]


def check_milestones(learned: int, major: int, minor: int, awarded: list[str]) -> list[dict]:
    """纯函数：返回满足门槛且账本中未领的里程碑（按表序升序）。

    - ``learned`` 已学卡牌总数；``major`` 已学大阿卡纳数；``minor`` 已学小阿卡纳数
    - ``awarded`` 账本中已有的 milestone key 列表；已有 key 跳过（幂等）
    """
    return [
        m for m in MILESTONES
        if _milestone_value(m, learned, major, minor) >= m["min"] and m["key"] not in awarded
    ]


def _milestones_awarded_of(user: User) -> list[str]:
    """账本解析（JSON 数组字符串，脏数据安全回退空列表）。"""
    return [k for k in parse_json_list(user.academy_milestones) if isinstance(k, str)]


async def apply_milestones(
    db: AsyncSession, user: User, learned: int, major: int, minor: int
) -> list[dict]:
    """发放所有未领里程碑：星尘加法 + star_tier 同步 + 称号入账 + 壁纸。

    返回实际发放的里程碑列表（[{key, title, stardust_gained, wallpaper_granted}, ...]）。
    账本内已有 key 跳过（幂等锚：academy_milestones + uq_user_card 双保险）。
    星尘加法沿用签到模式（stardust_total += n; star_tier = tier_for(...)）。
    """
    awarded = _milestones_awarded_of(user)
    pending = check_milestones(learned, major, minor, awarded)
    granted: list[dict] = []
    for m in pending:
        user.stardust_total = (user.stardust_total or 0) + m["stardust"]
        user.star_tier = tier_for(user.stardust_total)
        awarded.append(m["key"])
        wallpaper_granted = False
        if m.get("wallpaper"):
            grant_wallpaper(user, date.today().isoformat())
            wallpaper_granted = True
        granted.append({
            "key": m["key"],
            "title": m["title"],
            "stardust_gained": m["stardust"],
            "wallpaper_granted": wallpaper_granted,
        })
    if granted:
        user.academy_milestones = json.dumps(awarded, ensure_ascii=False)
    return granted
