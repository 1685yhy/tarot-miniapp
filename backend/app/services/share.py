"""
Share / viral-tracking service.

Provides reward logic when a user shares content from the app.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.share_log import ShareLog
from app.models.user import User


async def record_share(
    db: AsyncSession,
    sharer_id: str | None = None,
    channel: str | None = None,
    share_type: str | None = None,
    ref_id: str | None = None,
) -> dict:
    """
    Log a share event and reward the sharer if identifiable.

    Reward: decrement ``free_readings_today`` by 1 (i.e. give one free reading
    back), floored at 0 so the counter never goes negative.

    Returns a dict summarising what happened.
    """
    rewarded = False
    free_readings_remaining = None

    if sharer_id:
        result = await db.execute(select(User).where(User.id == sharer_id))
        sharer = result.scalar_one_or_none()
        if sharer:
            # Give one free reading back (floor at 0)
            sharer.free_readings_today = max(0, sharer.free_readings_today - 1)
            free_readings_remaining = sharer.free_readings_today
            rewarded = True

    # Always persist a share log for analytics.
    log = ShareLog(
        sharer_id=sharer_id,
        channel=channel,
        share_type=share_type,
        ref_id=ref_id,
    )
    db.add(log)

    return {
        "rewarded": rewarded,
        "free_readings_remaining": free_readings_remaining,
        "log_id": log.id,
    }


async def get_share_stats(
    db: AsyncSession,
    sharer_id: str | None = None,
    days: int = 7,
) -> dict:
    """
    Return basic share-analytics stats.

    If *sharer_id* is provided, results are scoped to that user; otherwise
    they cover all users.
    """
    from sqlalchemy import func

    query = select(func.count(ShareLog.id))

    if sharer_id:
        query = query.where(ShareLog.sharer_id == sharer_id)

    result = await db.execute(query)
    total_shares = result.scalar_one()

    # Channel breakdown (top 5)
    from sqlalchemy import select as sel

    channel_query = (
        sel(ShareLog.channel, func.count(ShareLog.id).label("cnt"))
        .group_by(ShareLog.channel)
        .order_by(func.count(ShareLog.id).desc())
        .limit(5)
    )
    if sharer_id:
        channel_query = channel_query.where(ShareLog.sharer_id == sharer_id)

    channel_result = await db.execute(channel_query)
    channels = {row.channel or "unknown": row.cnt for row in channel_result}

    return {
        "total_shares": total_shares,
        "channels": channels,
    }
