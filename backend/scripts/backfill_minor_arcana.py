#!/usr/bin/env python3
"""backfill_minor_arcana.py — 小阿卡纳数据补全（P1-7 审计项）

为 56 张小阿卡纳牌用「规则模板」生成合理可用的领域解读数据：

  - love / career / finance / health × 正位/逆位（8 个字段）
  - keywords_reversed（基于生成的 upright 关键词做反义/建议式转换）
  - keywords_upright（若为空，与 reversed 一起由模板生成）

规则语义：
  - 花色：权杖=事业/行动、圣杯=感情/情绪、宝剑=思考/沟通、星币=财务/健康
  - 数值：1=开始、2=选择、3=协作 … 10=完成；11-14=侍从/骑士/王后/国王

只填为空字段，绝不覆盖已有数据；不改 schema。
执行前自动备份数据库：
  - SQLite：复制文件为 <db>.bak-<时间戳>
  - MySQL ：建表 tarot_cards_backup_<时间戳>（SELECT *）

用法:
    cd backend
    python -m scripts.backfill_minor_arcana                # 读 .env 的 DATABASE_URL
    python -m scripts.backfill_minor_arcana --db sqlite:///./tarot_test.db
    python -m scripts.backfill_minor_arcana --db "mysql+pymysql://user:pwd@host/tarot_db"
    python -m scripts.backfill_minor_arcana --dry-run      # 只统计不写入
"""

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# 保证 `python -m scripts.backfill_minor_arcana` 与直接运行均可导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models.card import TarotCard  # noqa: E402

# ---------------------------------------------------------------------------
# 规则模板
# ---------------------------------------------------------------------------

# 花色 → 四个领域的解读主题短语（正位语义）
SUIT_DOMAINS = {
    "wands": {
        "love": "感情中你的热情与主动表达",
        "career": "事业上的开拓与行动",
        "finance": "财运上的主动创收与机会把握",
        "health": "活力与体能方面",
    },
    "cups": {
        "love": "感情中的情绪流动与联结",
        "career": "职场中的人际氛围与协作",
        "finance": "理财心态与情绪消费",
        "health": "情绪健康与心身平衡",
    },
    "swords": {
        "love": "感情中的理性沟通与观念磨合",
        "career": "工作上的决策与竞争",
        "finance": "财务分析与风险判断",
        "health": "神经与睡眠状态",
    },
    "pentacles": {
        "love": "感情中的务实经营与稳定",
        "career": "事业上的长期积累与稳健发展",
        "finance": "资产积累与储蓄规划",
        "health": "身体养护与规律作息",
    },
}

# 牌面主题（按花色内序号 1-14；序号 = 该花色内按 card_number 排序的位置）
NUMBER_THEMES = {
    1: ("新开始", "机会未能落地"),           # Ace 王牌
    2: ("权衡选择", "犹豫不决"),
    3: ("协作成长", "配合不畅"),
    4: ("稳固基础", "僵化停滞"),
    5: ("直面挑战", "冲突升级"),
    6: ("和谐回馈", "旧怨重提"),
    7: ("坚持评估", "退缩怀疑"),
    8: ("高效行动", "节奏迟滞"),
    9: ("积累沉淀", "临近透支"),
    10: ("圆满收束", "过载未竟"),
    11: ("学习探索", "拖延不成熟"),          # 侍从
    12: ("积极进取", "冲动失控"),            # 骑士
    13: ("成熟滋养", "过度付出"),            # 王后
    14: ("掌控全局", "固执专断"),            # 国王
}

NUMBER_KEYWORDS = {
    1: ["新开始", "开创力", "时机萌芽"],
    2: ["权衡选择", "规划权衡", "两难平衡"],
    3: ["协作成长", "团队助力", "进展初显"],
    4: ["稳固基础", "休整蓄力", "安居乐业"],
    5: ["直面挑战", "竞争压力", "突破在即"],
    6: ["和谐回馈", "修复关系", "贵人相助"],
    7: ["坚持评估", "内在力量", "独自坚守"],
    8: ["高效行动", "快速推进", "掌控节奏"],
    9: ["积累沉淀", "稳中求进", "独立深耕"],
    10: ["圆满收束", "使命完成", "阶段终结"],
    11: ["学习探索", "讯息到来", "新手心态"],
    12: ["积极进取", "追逐目标", "速度激情"],
    13: ["成熟滋养", "包容安抚", "内在从容"],
    14: ["掌控全局", "权威成就", "稳定统治"],
}

SUIT_KEYWORDS = {
    "wands": ["行动力", "事业开创", "热情"],
    "cups": ["情感联结", "人际和谐", "共情"],
    "swords": ["理性思考", "沟通表达", "洞察力"],
    "pentacles": ["务实积累", "财务稳健", "健康管理"],
}

# upright 关键词 → 逆位关键词（反义/建议式）。未覆盖的用兜底规则 f"{kw}受阻"。
ANTONYM_MAP = {
    # 数值主题
    "新开始": "开始受阻", "开创力": "动力不足", "时机萌芽": "时机未熟",
    "权衡选择": "犹豫不决", "规划权衡": "计划难定", "两难平衡": "选择失衡",
    "协作成长": "配合不畅", "团队助力": "助力不足", "进展初显": "进展缓慢",
    "稳固基础": "基础松动", "休整蓄力": "停滞不前", "安居乐业": "局面僵化",
    "直面挑战": "矛盾升级", "竞争压力": "压力倍增", "突破在即": "突破受阻",
    "和谐回馈": "失衡挑剔", "修复关系": "旧怨重现", "贵人相助": "助力缺失",
    "坚持评估": "信心动摇", "内在力量": "自我怀疑", "独自坚守": "孤立无援",
    "高效行动": "节奏迟滞", "快速推进": "进展拖延", "掌控节奏": "节奏失控",
    "积累沉淀": "临近透支", "稳中求进": "后劲不足", "独立深耕": "封闭焦虑",
    "圆满收束": "过载未竟", "使命完成": "收尾拖沓", "阶段终结": "结果未达",
    "学习探索": "经验不足", "讯息到来": "讯息延迟", "新手心态": "拖延回避",
    "积极进取": "冲动冒进", "追逐目标": "目标偏移", "速度激情": "有勇无谋",
    "成熟滋养": "过度付出", "包容安抚": "情绪泛滥", "内在从容": "情绪内耗",
    "掌控全局": "固执专断", "权威成就": "权威受挫", "稳定统治": "掌控欲过强",
    # 花色主题
    "行动力": "行动受阻", "事业开创": "事业停滞", "热情": "热情消退",
    "情感联结": "情感疏离", "人际和谐": "人际摩擦", "共情": "过度共情",
    "理性思考": "思绪混乱", "沟通表达": "词不达意", "洞察力": "判断失误",
    "务实积累": "积累不足", "财务稳健": "财务波动", "健康管理": "健康忽视",
}


def _reversed_keyword(kw: str) -> str:
    return ANTONYM_MAP.get(kw, f"{kw}受阻")


# ---------------------------------------------------------------------------
# 生成逻辑
# ---------------------------------------------------------------------------


def generate_for(card: TarotCard, pos_in_suit: int) -> dict:
    """按规则模板生成该牌缺失字段的填充值。"""
    suit = card.suit or "wands"
    domains = SUIT_DOMAINS.get(suit, SUIT_DOMAINS["wands"])
    num_up, num_rev = NUMBER_THEMES.get(pos_in_suit, NUMBER_THEMES[1])
    num_kws = NUMBER_KEYWORDS.get(pos_in_suit, NUMBER_KEYWORDS[1])
    suit_kws = SUIT_KEYWORDS.get(suit, SUIT_KEYWORDS["wands"])

    upright_keywords = num_kws[:2] + [suit_kws[0], suit_kws[1]]
    reversed_keywords = [_reversed_keyword(k) for k in upright_keywords]

    updates: dict[str, str] = {}
    for domain, up_theme in domains.items():
        # 只填空字段，绝不覆盖已有数据（幂等）
        if not (getattr(card, f"{domain}_upright") or "").strip():
            updates[f"{domain}_upright"] = (
                f"{up_theme}上，「{num_up}」的能量正在显现。"
                "宜顺势把握、主动推进，让节奏为你所用。"
            )
        if not (getattr(card, f"{domain}_reversed") or "").strip():
            updates[f"{domain}_reversed"] = (
                f"{up_theme}上，容易出现「{num_rev}」的状况。"
                "建议先调整节奏、稳住心态，再一步步落实。"
            )

    if not (card.keywords_upright or "").strip():
        updates["keywords_upright"] = json.dumps(upright_keywords, ensure_ascii=False)
    if not (card.keywords_reversed or "").strip():
        updates["keywords_reversed"] = json.dumps(reversed_keywords, ensure_ascii=False)
    return updates


# ---------------------------------------------------------------------------
# 数据库辅助
# ---------------------------------------------------------------------------


def _to_sync_url(url: str) -> str:
    """把 async 驱动的 URL 转成同步驱动 URL（aiosqlite / asyncmy → pymysql）。"""
    url = url.replace("+aiosqlite", "")
    if "+asyncmy" in url:
        url = url.replace("+asyncmy", "+pymysql")
    return url


def _backup(engine) -> str:
    """执行前备份。SQLite 复制文件；MySQL 建 tarot_cards_backup_<ts> 表。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dialect = engine.dialect.name
    if dialect == "sqlite":
        raw_url = str(engine.url)
        # sqlite:///path → path（含相对/绝对路径）
        path_str = raw_url.split("sqlite:///", 1)[1]
        src = Path(path_str).resolve()
        if not src.exists():
            raise FileNotFoundError(f"SQLite 数据库不存在: {src}")
        dst = src.with_name(f"{src.name}.bak-{ts}")
        shutil.copy2(src, dst)
        return str(dst)
    if dialect in ("mysql", "pymysql"):
        backup_table = f"tarot_cards_backup_{ts}"
        with engine.begin() as conn:
            conn.execute(
                text(f"CREATE TABLE {backup_table} AS SELECT * FROM tarot_cards")
            )
        return backup_table
    raise RuntimeError(f"不支持的数据库方言: {dialect}")


def run(url: str, dry_run: bool = False) -> dict:
    """对指定 DATABASE_URL 执行补全，返回统计信息。"""
    sync_url = _to_sync_url(url)
    try:
        engine = create_engine(sync_url)
    except ModuleNotFoundError as exc:
        if "pymysql" in str(exc):
            raise SystemExit(
                "缺少 pymysql 驱动：pip install pymysql "
                f"（用于连接 {sync_url}）"
            ) from exc
        raise

    if dry_run:
        backup_info = "（--dry-run，未备份）"
    else:
        backup_info = _backup(engine)

    stats = {
        "cards_updated": 0,
        "fields_filled": 0,
        "field_detail": {f: 0 for f in (
            "love_upright", "love_reversed",
            "career_upright", "career_reversed",
            "finance_upright", "finance_reversed",
            "health_upright", "health_reversed",
            "keywords_upright", "keywords_reversed",
        )},
    }

    with Session(engine) as session:
        cards = (
            session.execute(
                select(TarotCard)
                .where(TarotCard.arcana == "minor")
                .order_by(TarotCard.suit, TarotCard.card_number, TarotCard.id)
            )
            .scalars()
            .all()
        )

        # 按花色内排序序号确定 1-14 的位置语义
        suit_rank: dict[str, int] = {}
        for card in cards:
            suit = card.suit or "wands"
            suit_rank[suit] = suit_rank.get(suit, 0) + 1
            pos = suit_rank[suit]

            updates = generate_for(card, pos)
            if not updates:
                continue

            stats["cards_updated"] += 1
            if not dry_run:
                for field, value in updates.items():
                    setattr(card, field, value)
            for field in updates:
                stats["field_detail"][field] += 1
                stats["fields_filled"] += 1

        if not dry_run:
            session.commit()

    stats["backup"] = backup_info
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="小阿卡纳数据补全（P1-7）")
    parser.add_argument(
        "--db",
        help="数据库 URL（默认读 .env 的 DATABASE_URL；MySQL 需装 pymysql）",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只统计不写入（不备份）"
    )
    args = parser.parse_args()

    # 默认使用 .env 配置（与 settings 相同的加载逻辑）
    url = args.db
    if not url:
        from app.config import settings
        url = settings.DATABASE_URL
    print(f"目标数据库: {url}")
    print(f"（同步驱动: {_to_sync_url(url)}）")

    stats = run(url, dry_run=args.dry_run)
    print(f"\n备份: {stats['backup']}")
    print(f"补全卡牌数: {stats['cards_updated']} / 56")
    print(f"补全字段数: {stats['fields_filled']}")
    for field, count in stats["field_detail"].items():
        if count:
            print(f"  - {field}: {count}")


if __name__ == "__main__":
    main()
