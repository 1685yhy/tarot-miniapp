"""
Share / viral-tracking service.

Provides invite code generation, invite tracking with rewards for both
inviter and invitee, and tiered share rewards.
"""

import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.share_log import ShareLog, Invite
from app.utils.auth import utc_aware
from app.models.user import User

# ---------------------------------------------------------------------------
# Reward tier thresholds
# ---------------------------------------------------------------------------
REWARD_TIERS = [
    {"shares": 1,  "free_readings": 1,  "membership_days": 0},
    {"shares": 3,  "free_readings": 3,  "membership_days": 0},
    {"shares": 10, "free_readings": 0,  "membership_days": 7},
    {"shares": 30, "free_readings": 0,  "membership_days": 30},
]


def generate_invite_code() -> str:
    """Generate a short unique invite code in the format STAR-XXXX."""
    suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"STAR-{suffix}"


async def get_or_create_invite_code(
    db: AsyncSession,
    user: User,
) -> str:
    """Return the user's existing invite code, or generate a new unique one."""
    if user.invite_code:
        return user.invite_code

    # Generate a unique code (collision is astronomically unlikely but guard anyway)
    for _ in range(10):
        code = generate_invite_code()
        existing = await db.execute(select(User).where(User.invite_code == code))
        if not existing.scalar_one_or_none():
            user.invite_code = code
            return code

    # Fallback: add more entropy
    suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    code = f"STAR-{suffix}"
    user.invite_code = code
    return code


async def record_share(
    db: AsyncSession,
    sharer_id: str | None = None,
    channel: str | None = None,
    share_type: str | None = None,
    ref_id: str | None = None,
) -> dict:
    """
    Log a share event and reward the sharer if identifiable.

    Reward: increment share_count and evaluate tier rewards.
    Previously this rewarded by decrementing free_readings_today;
    now it uses share_count with tier-based rewards.
    """
    rewarded = False
    free_readings_remaining = None
    new_tier = 0

    if sharer_id:
        result = await db.execute(select(User).where(User.id == sharer_id))
        sharer = result.scalar_one_or_none()
        if sharer:
            # Record share count
            sharer.share_count = (sharer.share_count or 0) + 1
            current_shares = sharer.share_count
            current_tier = sharer.reward_tier or 0

            # Check if a new tier was reached
            for i, tier in enumerate(REWARD_TIERS):
                tier_index = i + 1  # 1-indexed
                if current_shares >= tier["shares"] and tier_index > current_tier:
                    # Grant reward for this tier
                    new_tier = tier_index
                    if tier["free_readings"] > 0:
                        sharer.free_deep_readings = (sharer.free_deep_readings or 0) + tier["free_readings"]
                    if tier["membership_days"] > 0 and not sharer.is_member:
                        # Grant temporary membership
                        from datetime import timedelta
                        now = datetime.now(timezone.utc)
                        if utc_aware(sharer.member_expires_at) and utc_aware(sharer.member_expires_at) > now:
                            sharer.member_expires_at = sharer.member_expires_at + timedelta(days=tier["membership_days"])
                        else:
                            sharer.member_expires_at = now + timedelta(days=tier["membership_days"])
                        sharer.is_member = True
                    rewarded = True

            # Update highest tier earned
            if new_tier > current_tier:
                sharer.reward_tier = new_tier

            free_readings_remaining = (sharer.free_deep_readings or 0) + (sharer.free_readings_today or 0)

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
        "share_count": sharer.share_count if sharer_id else 0,
        "reward_tier": new_tier or None,
    }


async def process_invite(
    db: AsyncSession,
    inviter_code: str,
    invitee_user: User,
) -> dict:
    """
    Process an invite: reward both inviter and invitee with +1 free deep reading.

    Returns a dict with details about what happened.
    """
    # Find the inviter by invite code
    result = await db.execute(select(User).where(User.invite_code == inviter_code))
    inviter = result.scalar_one_or_none()
    if not inviter:
        return {"success": False, "error": "无效的邀请码"}

    # Cannot invite yourself
    if inviter.id == invitee_user.id:
        return {"success": False, "error": "不能邀请自己"}

    # Check if the invitee already used an invite code
    existing_invite = await db.execute(
        select(Invite).where(Invite.invitee_id == invitee_user.id)
    )
    if existing_invite.scalar_one_or_none():
        return {"success": False, "error": "你已经接受过邀请"}

    # Create invite record
    invite = Invite(
        inviter_id=inviter.id,
        invitee_id=invitee_user.id,
        reward_granted=True,
    )
    db.add(invite)

    # Reward: +1 free deep reading for BOTH inviter and invitee
    inviter.free_deep_readings = (inviter.free_deep_readings or 0) + 1
    invitee_user.free_deep_readings = (invitee_user.free_deep_readings or 0) + 1

    return {
        "success": True,
        "inviter_reward": 1,
        "invitee_reward": 1,
        "inviter_name": inviter.nickname or "一位星光旅人",
    }


async def get_share_stats(
    db: AsyncSession,
    sharer_id: str | None = None,
    days: int = 7,
) -> dict:
    """
    Return comprehensive share-analytics stats including invite and tier info.
    """
    from sqlalchemy import func as sa_func

    # Base share count
    query = select(sa_func.count(ShareLog.id))
    if sharer_id:
        query = query.where(ShareLog.sharer_id == sharer_id)
    result = await db.execute(query)
    total_shares = result.scalar_one()

    # Channel breakdown (top 5)
    channel_query = (
        select(ShareLog.channel, sa_func.count(ShareLog.id).label("cnt"))
        .group_by(ShareLog.channel)
        .order_by(sa_func.count(ShareLog.id).desc())
        .limit(5)
    )
    if sharer_id:
        channel_query = channel_query.where(ShareLog.sharer_id == sharer_id)
    channel_result = await db.execute(channel_query)
    channels = {row.channel or "unknown": row.cnt for row in channel_result}

    # Invite stats
    total_invites = 0
    friends_joined = 0
    if sharer_id:
        invite_count = await db.execute(
            select(sa_func.count(Invite.id)).where(Invite.inviter_id == sharer_id)
        )
        total_invites = invite_count.scalar_one()
        friends_joined = total_invites  # Each invite = 1 friend joined

    # User-specific stats
    user = None
    if sharer_id:
        user_result = await db.execute(select(User).where(User.id == sharer_id))
        user = user_result.scalar_one_or_none()

    share_count = user.share_count if user else total_shares
    free_deep = user.free_deep_readings if user else 0
    reward_tier = user.reward_tier if user else 0

    # Next reward tier info
    next_tier = None
    for tier in REWARD_TIERS:
        if tier["shares"] > share_count:
            next_tier = {
                "shares_needed": tier["shares"],
                "remaining": tier["shares"] - share_count,
                "reward": tier,
            }
            break

    return {
        "total_shares": total_shares,
        "share_count": share_count,
        "channels": channels,
        "total_invites": total_invites,
        "friends_joined": friends_joined,
        "free_deep_readings": free_deep,
        "free_readings_earned": free_deep,
        "reward_tier": reward_tier,
        "next_reward_tier": next_tier,
        "invite_code": user.invite_code if user else None,
    }
