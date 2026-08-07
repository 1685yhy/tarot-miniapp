import random
import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.models.community import Topic, Post
from app.models.card import TarotCard
from app.models.user import User
from app.schemas.community import (
    CommunityTodayResponse,
    TopicResponse,
    PostResponse,
    PostCreate,
    PostListResponse,
)
from app.services.msg_check import msg_sec_check
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/community", tags=["社区"])


# ── Reflective questions (rotated daily by index) ──
_REFLECTIVE_QUESTIONS = [
    "在今天的喧嚣中，你是否听到内心真实的声音？是什么在呼唤你？",
    "你最近一次感受到纯粹喜悦是什么时候？那是什么样的场景？",
    "你内心有没有一个一直想说、却从未说出口的秘密或感受？",
    "你最近在为什么事情感到迷茫？如果可以抛开顾虑，你真正想要的是什么？",
    "有没有一件小事，一直在你心里挥之不去？试着把它写下来。",
    "如果可以给陌生人一句真诚的祝福，你会说什么？",
    "你最近一次与他人产生温暖的连接是什么时候？那让你感受到什么？",
    "你内心深处最柔软的地方，是什么？",
    "你希望未来的自己，能比现在多拥有什么？少背负什么？",
    "你最近有没有对自己说过「没关系」？如果没有，现在对自己说一次。",
    "如果宇宙现在可以为你实现一个愿望，你会许什么愿？",
    "你深夜失眠时，最多在想什么？如果把它说出来，会是什么？",
]


async def _ensure_today_topic(db: AsyncSession) -> Topic:
    """Get today's topic, auto-creating one if none exists."""
    today = date.today()

    # Check if topic already exists for today
    result = await db.execute(
        select(Topic).where(Topic.date == today)
    )
    topic = result.scalar_one_or_none()
    if topic:
        return topic

    # Pick a random tarot card for inspiration
    card_result = await db.execute(
        select(TarotCard).order_by(func.random()).limit(1)
    )
    card = card_result.scalar_one_or_none()

    card_name = card.name_zh if card else "命运之轮"
    title = f"今天的塔罗启示：{card_name}"

    # Deterministic question index based on day-of-year
    day_index = today.timetuple().tm_yday % len(_REFLECTIVE_QUESTIONS)
    question = _REFLECTIVE_QUESTIONS[day_index]
    description = f"今日之牌：{card_name}。{question}"

    topic = Topic(
        date=today,
        title=title,
        description=description,
        card_id=card.id if card else None,
    )
    db.add(topic)
    await db.flush()
    return topic


@router.get("/today", response_model=CommunityTodayResponse)
async def get_today_topic(
    db: AsyncSession = Depends(get_db),
):
    """Return today's topic. Auto-creates one if none exists for today."""
    topic = await _ensure_today_topic(db)

    # Count posts for today's topic
    count_result = await db.execute(
        select(func.count(Post.id)).where(Post.topic_id == topic.id)
    )
    post_count = count_result.scalar() or 0

    return CommunityTodayResponse(
        topic=TopicResponse(
            id=topic.id,
            date=str(topic.date),
            title=topic.title,
            description=topic.description,
            card_id=topic.card_id,
        ),
        post_count=post_count,
    )


@router.get("/posts", response_model=PostListResponse)
async def list_posts(
    topic_id: int = Query(..., description="Topic ID"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Paginated posts for a topic, newest first."""
    offset = (page - 1) * limit

    # Verify topic exists
    topic_result = await db.execute(
        select(Topic).where(Topic.id == topic_id)
    )
    if not topic_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="话题不存在")

    # Count total
    count_result = await db.execute(
        select(func.count(Post.id)).where(Post.topic_id == topic_id)
    )
    total = count_result.scalar() or 0

    # Fetch page
    result = await db.execute(
        select(Post)
        .where(Post.topic_id == topic_id)
        .order_by(Post.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    posts = result.scalars().all()

    return PostListResponse(
        posts=[
            PostResponse(
                id=p.id,
                topic_id=p.topic_id,
                content=p.content,
                created_at=p.created_at,
            )
            for p in posts
        ],
        page=page,
        total=total,
        has_more=(offset + len(posts)) < total,
    )


@router.post("/posts", response_model=PostResponse, status_code=201)
async def create_post(
    body: PostCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a post on a daily topic. Posts display anonymously, but the
    author is tracked (user_id) for moderation / account deletion."""
    # Content safety — local keyword gate + WeChat msgSecCheck (fail-open)
    check = await msg_sec_check(body.content, user.openid)
    if not check["safe"]:
        raise HTTPException(status_code=400, detail="内容包含违规信息，请修改后再发布")

    # Verify topic exists
    topic_result = await db.execute(
        select(Topic).where(Topic.id == body.topic_id)
    )
    if not topic_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="话题不存在")

    post = Post(
        topic_id=body.topic_id,
        user_id=user.id,
        content=body.content,
    )
    db.add(post)
    await db.flush()

    return PostResponse(
        id=post.id,
        topic_id=post.topic_id,
        content=post.content,
        created_at=post.created_at,
    )
