# app/utils/time_utils.py
# Full path: WebChurchMan/app/utils/time_utils.py
# File name: time_utils.py
# Brief, detailed purpose: Timezone-aware datetime helpers.
# Uses your existing get_settings() loader.
# All DB timestamps should be stored in UTC.
# SAFE FALLBACK: If zoneinfo/tzdata is missing (common on Windows), falls back to fixed Central Time (UTC-6, no DST).
# Default church timezone is now hard-coded to Central Time to get the app running immediately.

from datetime import datetime, timezone, timedelta
from flask import current_app
from app.models.settings import get_settings  # Matches your current loader

# Fixed timezones (used when zoneinfo is unavailable)
UTC_TZ = timezone.utc
CENTRAL_TZ_FIXED = timezone(timedelta(hours=-6))  # Central Standard Time – matches your 6-hour offset issue

def get_church_tz():
    """
    Returns the church's configured timezone.
    Tries zoneinfo first (proper DST support if tzdata installed).
    Falls back to fixed Central Time (UTC-6) if zoneinfo fails or tz not found.
    Defaults to Central Time if not set in DB (gets app running immediately).
    """
    settings = get_settings()
    tz_name = (settings.get('timezone') or 'America/Chicago').strip()

    # Try proper IANA zoneinfo (best case – handles DST automatically)
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception as e:
        current_app.logger.warning(
            f"ZoneInfo failed (likely missing tzdata package on Windows): {e}. "
            "Falling back to fixed Central Time (UTC-6)."
        )
        return CENTRAL_TZ_FIXED


def utc_now() -> datetime:
    """Current time in UTC (aware). Use this when saving to DB."""
    return datetime.now(UTC_TZ)


def now_church() -> datetime:
    """Current time in church timezone (aware)."""
    return datetime.now(get_church_tz())


def to_utc(dt: datetime) -> datetime:
    """Convert to UTC aware. If naive, assume it was entered in church local time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_church_tz())
    return dt.astimezone(UTC_TZ)


def to_church_local(dt: datetime) -> datetime:
    """Convert UTC (from DB) to church local time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(get_church_tz())


def format_church(dt: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Format in church local time."""
    return to_church_local(dt).strftime(fmt)


def format_church_full(dt: datetime) -> str:
    """Friendly long format."""
    local = to_church_local(dt)
    tz_name = local.tzname() or 'CST'
    return local.strftime(f"%B %d, %Y %I:%M %p {tz_name}")