"""
每日一牌 — 确定性选牌逻辑（P1-8）。

/cards/daily 与 21:00 晚间推送共用同一实现，保证同一用户同一天
看到/收到的是同一张牌：

    seed = f"{user_id}:{YYYY-MM-DD}"
    idx  = int(sha256(seed).digest()[:8]) % len(cards)
"""

import hashlib
from datetime import date

from app.models.card import TarotCard


def pick_daily_card(cards: list[TarotCard], user_id: str, day: date | None = None) -> TarotCard:
    """按「用户 + 日期」从 78 张牌中确定性选牌。

    Same user on the same calendar date always gets the same card (and a
    different one the next day), with no storage needed.

    Parameters
    ----------
    cards : list[TarotCard]
        完整牌库（order by id，与 /cards/daily 一致）。
    user_id : str
        用户 ID。
    day : date, optional
        目标日期，默认今天（服务器本地日期，与 /cards/daily 一致）。

    Returns
    -------
    TarotCard
        确定性选中的牌。
    """
    day = day or date.today()
    seed_str = f"{user_id}:{day.isoformat()}"
    digest = hashlib.sha256(seed_str.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:8], "big") % len(cards)
    return cards[idx]
