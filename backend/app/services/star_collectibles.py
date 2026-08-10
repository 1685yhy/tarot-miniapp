"""
星卡收藏 / 星光壁纸服务（P0-3 星尘签到收集体系 · 设计缺口 1）。

- 7 日连续签到 → 稀有星卡（正位金卡）：从 78 张塔罗牌按 user_id 确定性选取，
  同一用户永远得到同一张星卡（seed 稳定 → 不重复/不漂移）
- 30 日连续签到 → 星光壁纸（收藏品）

两者都是收藏品概念：不消耗任何额度（免费解读/会员天数据由调用方照常发放，
本服务只追加收藏记录）。存储格式为 users.star_cards / users.wallpapers 两列
Text 字段，内容为 JSON 数组字符串（可迁移可测试；脏数据解析安全回退空列表）：

    star_cards: [{"card_id": 12, "date": "2026-08-11", "tier": "gold", "orientation": "upright"}, ...]
    wallpapers: ["2026-08-11", ...]  # 达成日期

发放幂等由调用方（tasks.py 的 milestones_claimed 去重）保证；本模块内同
card_id / 同日期再追加时也做防御性去重。
"""

import hashlib
import json

from app.models.user import User

# 稀有星卡 = 正位金卡（tier 标记稀有度，orientation 标记正/逆位）
STAR_CARD_TIER = "gold"
STAR_CARD_ORIENTATION = "upright"

# 里程碑天数（与 tasks.STREAK_MILESTONES 的 7/30 对应，叠加在会员奖励之上）
STAR_CARD_MILESTONE = 7
WALLPAPER_MILESTONE = 30

# 标准塔罗牌池大小（78 张）；牌池以库内 tarot_cards 为准，兜底常数用于容错
DEFAULT_CARD_POOL = 78


# ── 确定性选牌 ──────────────────────────────────────────────


def pick_star_card_index(user_id: str, pool_size: int) -> int:
    """按 user_id 稳定 seed 选取牌池索引（0 起）。

    同一用户永远得到同一张星卡（避免重复抽到不同牌）；跨环境稳定。
    """
    digest = hashlib.md5(f"starcard:{user_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % max(1, pool_size)


# ── 存储读写（Text 列内 JSON 数组） ─────────────────────────


def parse_json_list(raw: str | None) -> list:
    """解析 JSON 数组字符串；None / 坏 JSON / 非数组一律安全回退空列表。"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def star_cards_of(user: User) -> list[dict]:
    return parse_json_list(user.star_cards)


def wallpapers_of(user: User) -> list[str]:
    return parse_json_list(user.wallpapers)


# ── 发放收藏品 ──────────────────────────────────────────────


def grant_star_card(user: User, card_id: int, date_str: str) -> dict:
    """追加一张稀有星卡记录并返回该记录（收藏品，无额度消耗）。

    同 card_id 已存在时不再重复追加（防御性幂等）。
    """
    record = {
        "card_id": card_id,
        "date": date_str,
        "tier": STAR_CARD_TIER,
        "orientation": STAR_CARD_ORIENTATION,
    }
    cards = star_cards_of(user)
    if not any(c.get("card_id") == card_id for c in cards):
        cards.append(record)
        user.star_cards = json.dumps(cards, ensure_ascii=False)
    return record


def grant_wallpaper(user: User, date_str: str) -> str:
    """追加一条星光壁纸达成记录并返回日期（收藏品，无额度消耗）。"""
    dates = wallpapers_of(user)
    if date_str not in dates:
        dates.append(date_str)
        user.wallpapers = json.dumps(dates, ensure_ascii=False)
    return date_str
