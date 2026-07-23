"""
Enhanced Annual Report API endpoint.

- GET /report/annual — generates a Spotify Wrapped-style annual report
  Returns rich structured data: stats, top cards, themes, personality,
  monthly chart, mood trends, AI summary, and new year blessing.
  Results are cached per user per calendar year (regenerate on demand).
"""

import json
import logging
from collections import Counter
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from openai import AsyncOpenAI
from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models.card import TarotCard
from app.models.diary import DiaryEntry
from app.models.reading import Reading, DrawnCard
from app.models.user import User
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["年度报告"])

_THEME_LABELS = {
    "love": "爱情",
    "career": "事业",
    "finance": "财运",
    "spiritual": "心灵成长",
    "general": "综合",
}

_THEME_ICONS = {
    "love": "heart",
    "career": "briefcase",
    "finance": "coin",
    "spiritual": "sparkles",
    "general": "star",
}

# Tarot personality archetypes — mapped from frequently drawn cards
_PERSONALITY_ARCHETYPES = {
    "愚者": {
        "archetype": "天真探索者",
        "description": "你像愚者一样，带着纯真和勇气踏上未知的旅程。你不惧怕开始新的篇章，总是怀着好奇心和乐观态度面对生活的每一个转角。",
    },
    "魔术师": {
        "archetype": "创造大师",
        "description": "你拥有魔术师般的创造力和资源整合能力。你善于运用手中的工具和才能，将想法化为现实，是真正的行动派。",
    },
    "女祭司": {
        "archetype": "直觉智者",
        "description": "你如女祭司般深沉而富有直觉。你相信内在的声音，善于聆听潜意识的低语，在静默中获取深刻的智慧。",
    },
    "女皇": {
        "archetype": "丰饶女神",
        "description": "你拥有女皇般的丰饶与温柔。你善于滋养他人，创造美好环境，在生活的方方面面都散发着母性的力量和优雅。",
    },
    "皇帝": {
        "archetype": "睿智领袖",
        "description": "你如皇帝般稳重而有权威。你重视秩序和结构，擅长制定规则和长远规划，是周围人心中的定海神针。",
    },
    "教皇": {
        "archetype": "精神导师",
        "description": "你有着教皇般的智慧和信仰。你重视传统和知识的传承，善于在精神层面引导他人找到自己的道路。",
    },
    "恋人": {
        "archetype": "心灵伴侣",
        "description": "你像恋人牌一样，重视关系与连接。你在乎选择的意义，用真心面对每一段关系，是感情世界里的真诚旅人。",
    },
    "战车": {
        "archetype": "无畏战士",
        "description": "你如战车般意志坚定，目标明确。一旦决定方向，就会全力以赴冲破障碍，你的决心和勇气令人敬佩。",
    },
    "力量": {
        "archetype": "内在勇者",
        "description": "你拥有力量牌所代表的内心坚韧。你的勇气不是外在的张扬，而是面对困境时的温柔坚持和不屈不挠。",
    },
    "隐士": {
        "archetype": "智慧追寻者",
        "description": "你如隐士般享受独处的时光。你在孤独中寻找真理，在静默中获得启示，你的智慧来自深度的内省。",
    },
    "命运之轮": {
        "archetype": "命运旅人",
        "description": "你与命运之轮同频共振。你相信生命中的每一次转折都有其意义，善于在变化中找到新的机遇和成长。",
    },
    "正义": {
        "archetype": "公正守护者",
        "description": "你如正义女神般明辨是非。你重视公平和诚实，在做决策时总是权衡各方，追求最平衡的结果。",
    },
    "倒吊人": {
        "archetype": "换位思考者",
        "description": "你像倒吊人一样拥有独特的视角。你善于从不同的角度看问题，在看似停滞的时期获得最深刻的领悟。",
    },
    "死神": {
        "archetype": "蜕变重生者",
        "description": "你与死神牌共鸣，意味着你拥有强大的蜕变能力。你懂得放下旧有，拥抱新生，每一次结束都是你重生的开始。",
    },
    "节制": {
        "archetype": "调和大师",
        "description": "你如节制牌所代表的均衡大师。你善于在中庸之道中找到最佳点，将对立的力量融合为和谐的整体。",
    },
    "恶魔": {
        "archetype": "直面阴影者",
        "description": "你敢于直视内心的欲望和阴影。你不逃避人性的复杂面，而是通过面对和接纳，将束缚转化为力量。",
    },
    "高塔": {
        "archetype": "破而后立者",
        "description": "你经历过高塔般突如其来的变化，但每次崩塌都让你重建得更强大。你懂得在混乱中找到新的秩序。",
    },
    "星星": {
        "archetype": "希望使者",
        "description": "你如星星般闪耀着希望的光芒。无论处境多么艰难，你总能保持信念，对未来充满信心和期待。",
    },
    "月亮": {
        "archetype": "梦境漫游者",
        "description": "你与月亮牌一样，游走在潜意识与梦境之间。你对未知充满好奇，在迷雾中依然相信内心的指引。",
    },
    "太阳": {
        "archetype": "阳光使者",
        "description": "你如太阳般灿烂温暖。你的积极能量感染着身边的每一个人，你用乐观和热情照亮了自己的世界。",
    },
    "审判": {
        "archetype": "觉醒召唤者",
        "description": "你经历着审判牌所代表的觉醒和召唤。你在人生的关键时刻聆听到内心的呼唤，勇敢地走向更高的使命。",
    },
    "世界": {
        "archetype": "圆满完成者",
        "description": "你如世界牌般达到了一个完整的周期。你拥有全局观，善于将各个元素整合为一体，完成伟大的目标。",
    },
    "圣杯": {"archetype": "情感探索者", "description": "你的情感世界丰富而深邃。你重视爱与关系，善于表达情感，在人际交往中展现真诚与温暖。"},
    "权杖": {"archetype": "行动先锋", "description": "你充满热情和行动力。你有明确的目标和方向，敢于冒险和探索，是永远在路上的追梦人。"},
    "宝剑": {"archetype": "思想斗士", "description": "你思维敏锐，理性而果断。你善于分析和解决问题，在挑战面前总能找到清晰的思路和策略。"},
    "星币": {"archetype": "务实建造者", "description": "你脚踏实地，重视物质世界的建设。你有耐心和毅力，善于将梦想一步步变为现实。"},
}

_MOOD_EMOJI_MAP = {
    "happy": ("😊", 4.5, "开心"),
    "calm": ("😌", 3.5, "平静"),
    "excited": ("🤩", 5, "兴奋"),
    "anxious": ("😰", 2, "焦虑"),
    "sad": ("😢", 1, "低落"),
    "thoughtful": ("🤔", 3, "思考"),
}


def _get_ai_client() -> AsyncOpenAI | None:
    if not settings.DEEPSEEK_API_KEY:
        return None
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


async def _get_readings_for_year(
    db: AsyncSession, user_id: str, year: int
) -> list[Reading]:
    """Fetch all readings for the user in the given year, with drawn cards."""
    result = await db.execute(
        select(Reading)
        .where(
            Reading.user_id == user_id,
            extract("year", Reading.created_at) == year,
        )
        .options(selectinload(Reading.drawn_cards).selectinload(DrawnCard.card))
        .order_by(Reading.created_at.asc())
    )
    return list(result.scalars().all())


async def _get_diary_entries_for_year(
    db: AsyncSession, user_id: str, year: int
) -> list[DiaryEntry]:
    """Fetch diary entries for the user in the given year."""
    result = await db.execute(
        select(DiaryEntry)
        .where(
            DiaryEntry.user_id == user_id,
            extract("year", DiaryEntry.entry_date) == year,
        )
        .order_by(DiaryEntry.entry_date.asc())
    )
    return list(result.scalars().all())


def _get_top_card(all_card_names: list[str]) -> dict:
    """Get the most drawn card from a list of card names."""
    if not all_card_names:
        return {"name": "无", "count": 0, "meaning": ""}
    counter = Counter(all_card_names)
    top_name = counter.most_common(1)[0][0]
    return {"name": top_name, "count": counter[top_name]}


def _get_top_themes(readings: list[Reading]) -> list[dict]:
    """Get top 3 themes from readings, ranked by frequency."""
    themes = [r.theme for r in readings if r.theme]
    if not themes:
        return [{"theme": "general", "label": "综合", "icon": "star", "count": 0}]
    counter = Counter(themes)
    top3 = []
    for theme, count in counter.most_common(3):
        top3.append({
            "theme": theme,
            "label": _THEME_LABELS.get(theme, theme),
            "icon": _THEME_ICONS.get(theme, "star"),
            "count": count,
        })
    return top3


def _get_monthly_chart_data(readings: list[Reading], year: int) -> list[dict]:
    """Build monthly reading count data for chart."""
    monthly = {m: 0 for m in range(1, 13)}
    for r in readings:
        if r.created_at:
            monthly[r.created_at.month] += 1
    return [
        {"month": m, "count": monthly[m], "label": f"{m}月"}
        for m in range(1, 13)
    ]


def _compute_personality(all_card_names: list[str]) -> dict:
    """Determine tarot personality archetype from most common cards."""
    if not all_card_names:
        return {
            "archetype": "星光旅人",
            "description": "你的塔罗人格还在形成中。每一次占卜都是与自己的一次对话，继续探索，你会发现自己独特的星光印记。",
        }

    counter = Counter(all_card_names)
    top_cards = [c for c, _ in counter.most_common(5)]

    # Check archetype matches in priority order: exact major arcana > suit match
    for card_name in top_cards:
        if card_name in _PERSONALITY_ARCHETYPES:
            return _PERSONALITY_ARCHETYPES[card_name]
        # Check suit-based archetype
        for suit_key, suit_meta in [
            ("圣杯", _PERSONALITY_ARCHETYPES.get("圣杯")),
            ("权杖", _PERSONALITY_ARCHETYPES.get("权杖")),
            ("宝剑", _PERSONALITY_ARCHETYPES.get("宝剑")),
            ("星币", _PERSONALITY_ARCHETYPES.get("星币")),
        ]:
            if suit_key in card_name:
                return dict(suit_meta)

    return {
        "archetype": "星光旅人",
        "description": "你的塔罗人格充满神秘感。你涉猎广泛，不拘一格，每一次占卜都在解锁你不同面向的智慧。",
    }


def _build_mood_trends(diary_entries: list[DiaryEntry]) -> list[dict]:
    """Build monthly mood average data from diary entries."""
    if not diary_entries:
        return []

    monthly_moods = {m: [] for m in range(1, 13)}
    for entry in diary_entries:
        if entry.mood and entry.entry_date:
            mood_info = _MOOD_EMOJI_MAP.get(entry.mood)
            if mood_info:
                monthly_moods[entry.entry_date.month].append(mood_info[1])

    trends = []
    for m in range(1, 13):
        scores = monthly_moods[m]
        if scores:
            avg_score = sum(scores) / len(scores)
            if avg_score >= 4:
                label = "happy"
            elif avg_score >= 3:
                label = "calm"
            elif avg_score >= 2:
                label = "gloomy"
            else:
                label = "down"
            trends.append({"month": m, "label": f"{m}月", "score": round(avg_score, 1), "mood_label": label})
        else:
            trends.append({"month": m, "label": f"{m}月", "score": None, "mood_label": None})
    return trends


@router.get("/annual")
async def get_annual_report(
    year: int | None = Query(None, description="年份，默认当前年份"),
    regenerate: bool = Query(False, description="强制重新生成"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a Spotify Wrapped-style annual tarot report.

    Returns rich structured data including:
    - Total readings, most drawn card, top themes
    - Monthly reading chart data
    - Annual theme card
    - Emotional journey from diary
    - Tarot personality profile
    - AI-generated annual summary and new year blessing
    """
    if not user.is_member:
        raise HTTPException(status_code=402, detail="年度报告仅限会员使用")

    current_year = date.today().year
    target_year = year or current_year

    # Return cached report unless regenerate is requested
    if (
        not regenerate
        and user.annual_report_year == target_year
        and user.annual_report_data
    ):
        return json.loads(user.annual_report_data)

    # ── Fetch user's actual reading data for the year ──
    readings = await _get_readings_for_year(db, user.id, target_year)
    diary_entries = await _get_diary_entries_for_year(db, user.id, target_year)

    total_readings = len(readings)

    # ── Collect all card names from drawn cards ──
    all_card_names = []
    card_details = []  # cards with full info for "年度主题牌"
    for reading in readings:
        for dc in reading.drawn_cards:
            if dc.card:
                all_card_names.append(dc.card.name_zh)
                if dc.card not in card_details:
                    card_details.append(dc.card)

    # ── Most drawn card ──
    most_drawn = _get_top_card(all_card_names)

    # Fetch meaning for most drawn card
    most_drawn_meaning = ""
    if most_drawn["name"] and most_drawn["name"] != "无":
        result = await db.execute(
            select(TarotCard).where(TarotCard.name_zh == most_drawn["name"])
        )
        card = result.scalar_one_or_none()
        if card:
            most_drawn_meaning = card.meaning_upright[:300]

    # ── Top 3 themes ──
    top_themes = _get_top_themes(readings)

    # ── Monthly chart data ──
    monthly_chart = _get_monthly_chart_data(readings, target_year)

    # ── Annual theme card (most significant card) ──
    # The card that appears most frequently in the first position of readings
    annual_theme_card = None
    if readings:
        first_card_counter = Counter()
        for reading in readings:
            if reading.drawn_cards:
                first_card = reading.drawn_cards[0]
                if first_card.card:
                    first_card_counter[first_card.card.name_zh] += 1
        if first_card_counter:
            top_theme_name = first_card_counter.most_common(1)[0][0]
            result_card = await db.execute(
                select(TarotCard).where(TarotCard.name_zh == top_theme_name)
            )
            tc = result_card.scalar_one_or_none()
            if tc:
                annual_theme_card = {
                    "name": tc.name_zh,
                    "name_en": tc.name_en,
                    "arcana": tc.arcana,
                    "suit": tc.suit,
                    "meaning": tc.meaning_upright[:400],
                    "keyword": (json.loads(tc.keywords_upright) if tc.keywords_upright else ["转变"])[0],
                }

    # ── Personality ──
    personality = _compute_personality(all_card_names)

    # ── Mood trends ──
    mood_trends = _build_mood_trends(diary_entries)

    # ── Tarot deck completion stats ──
    drawn_card_ids = set()
    for reading in readings:
        for dc in reading.drawn_cards:
            if dc.card:
                drawn_card_ids.add(dc.card.id)
    total_cards_in_deck = 78
    deck_completion_rate = round(len(drawn_card_ids) / total_cards_in_deck * 100, 1)

    # ── AI-generated content ──
    ai_summary = None
    new_year_blessing = None
    ai_personality_insight = None

    client = _get_ai_client()
    if client and total_readings > 0:
        # Build a compact prompt for AI
        top_card_name = most_drawn["name"] or "未知"
        top_theme_label = top_themes[0]["label"] if top_themes else "综合"
        personality_name = personality["archetype"]
        monthly_summary = ", ".join(
            f"{d['label']}:{d['count']}次" for d in monthly_chart if d["count"] > 0
        )
        theme_card_name = annual_theme_card["name"] if annual_theme_card else "无"
        mood_summary = ""
        if mood_trends:
            valid_moods = [m for m in mood_trends if m["mood_label"]]
            if valid_moods:
                mood_summary = "情绪趋势: " + ", ".join(
                    f"{m['label']} {m['mood_label']}" for m in valid_moods
                )

        readings_context = (
            f"总占卜次数: {total_readings}\n"
            f"最常抽到的牌: {top_card_name}\n"
            f"最关注主题: {top_theme_label}\n"
            f"年度主题牌: {theme_card_name}\n"
            f"塔罗人格: {personality_name}\n"
            f"{'月度活动: ' + monthly_summary if monthly_summary else ''}\n"
            f"{mood_summary}\n"
            f"牌库收集率: {deck_completion_rate}%"
        )

        system_prompt = (
            "你是一位温柔而富有诗意的塔罗占星师，专门为用户撰写年度回顾。"
            "你的语言风格温暖、深刻、有力量，像一位智慧的朋友在年末与用户谈心。"
            "所有输出必须使用中文。"
        )

        user_prompt = (
            f"请基于以下用户今年的塔罗占卜数据，生成一份有温度的年终回顾。\n\n"
            f"【用户年度数据】\n{readings_context}\n\n"
            f"请严格按照以下JSON格式回复，不要包含任何多余内容：\n"
            "{\n"
            '  "annual_summary": "写3段话的年度回顾。第一段概括今年的整体能量和主题；第二段深入解读关键节点和转折（提及最常抽到的牌和年度主题牌）；第三段给予肯定和鼓励，展望新的一年。语言温暖有诗意，总计300-500字。",\n'
            '  "new_year_blessing": "写一段新年寄语，60-100字。要求：优美、有力量、有画面感，像新年贺卡上的文字。可以引用星星、光、旅程等意象。",\n'
            '  "personality_insight": "基于用户的塔罗人格，写一句个性化的洞察（20-40字），说明这个特质如何在这一年帮助了用户。"\n'
            "}"
        )

        try:
            response = await client.chat.completions.create(
                model=settings.DEEPSEEK_MODEL,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=120.0,
            )
            content = response.choices[0].message.content
            if content:
                stripped = content.strip()
                if stripped.startswith("```"):
                    lines = stripped.split("\n")
                    stripped = "\n".join(
                        line for line in lines if not line.strip().startswith("```")
                    ).strip()
                try:
                    ai_data = json.loads(stripped)
                    ai_summary = ai_data.get("annual_summary")
                    new_year_blessing = ai_data.get("new_year_blessing")
                    ai_personality_insight = ai_data.get("personality_insight")
                except json.JSONDecodeError:
                    logger.warning("Failed to parse AI response JSON")
                    ai_summary = content[:500]
        except Exception as exc:
            logger.warning("AI annual report generation failed: %s", exc)

    # ── Build result ──
    result = {
        "year": target_year,
        "generated_at": str(date.today()),
        "total_readings": total_readings,
        "most_drawn_card": {
            "name": most_drawn["name"],
            "count": most_drawn["count"],
            "meaning": most_drawn_meaning,
        },
        "top_themes": top_themes,
        "annual_theme_card": annual_theme_card,
        "personality": {
            "archetype": personality["archetype"],
            "description": personality["description"],
            "ai_insight": ai_personality_insight,
        },
        "monthly_chart": monthly_chart,
        "mood_trends": mood_trends,
        "deck_completion": {
            "unique_cards_drawn": len(drawn_card_ids),
            "total_cards": total_cards_in_deck,
            "completion_rate": deck_completion_rate,
        },
        "ai_summary": ai_summary,
        "new_year_blessing": new_year_blessing,
        "has_readings": total_readings > 0,
        "has_diary": len(diary_entries) > 0,
    }

    # Cache to DB
    user.annual_report_data = json.dumps(result, ensure_ascii=False)
    user.annual_report_year = target_year
    await db.flush()

    return result
