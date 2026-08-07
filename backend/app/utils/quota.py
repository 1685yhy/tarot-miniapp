"""Daily AI-extras quota helpers (reinterpret / diary AI)."""

from datetime import datetime, timezone

from app.models.user import User


def reset_ai_quota_if_new_day(user: User) -> None:
    """Reset the daily AI-extras counters when the calendar day changes.

    ``quota_reset_date`` records the last day the counters were reset; the
    counters are zeroed whenever it is not today. Call before enforcing any
    AI-extras quota so a user can never inherit yesterday's usage.
    """
    today = datetime.now(timezone.utc).date()
    if user.quota_reset_date != today:
        user.quota_reset_date = today
        user.reinterpret_count_today = 0
        user.diary_ai_count_today = 0
