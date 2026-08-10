"""
星尘 / 星阶服务。

星尘（stardust_total）是用户通过签到等行为累积的货币型积分；
星阶（star_tier）由星尘总量按 STAR_TIERS 阈值推导，用于名片展示与权益划分。
"""

# 星阶阈值：(达到该星尘数, 星阶名称)，按阈值升序
STAR_TIERS = [
    (0, "微光"),
    (7, "星光"),
    (30, "星辉"),
    (100, "星冠"),
]

_STAR_TIER_MAX = len(STAR_TIERS) - 1


def tier_for(stardust: int) -> int:
    """根据星尘总量返回星阶索引（0 起）。

    返回最后一个阈值 <= stardust 的星阶；低于 0 视为 0，超出最高阈值封顶。
    """
    if stardust <= 0:
        return 0
    tier = 0
    for idx, (threshold, _name) in enumerate(STAR_TIERS):
        if stardust >= threshold:
            tier = idx
    return tier


def tier_name(tier: int) -> str:
    """根据星阶索引返回星阶名称；越界时回退到最近合法星阶。"""
    idx = max(0, min(tier, _STAR_TIER_MAX))
    return STAR_TIERS[idx][1]
