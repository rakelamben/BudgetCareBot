import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_user_tz(tz_name: str) -> ZoneInfo:
    """Get ZoneInfo object for user timezone string, defaulting to UTC if invalid."""
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_date_of(dt: datetime, tz: ZoneInfo) -> date:
    """Convert UTC datetime to local date in the specified timezone."""
    return dt.astimezone(tz).date()


def local_midnight_to_utc(local_d: date, tz: ZoneInfo) -> datetime:
    """Convert local midnight at the start of local_d to UTC datetime."""
    local_dt = datetime.combine(local_d, time.min, tzinfo=tz)
    return local_dt.astimezone(ZoneInfo("UTC"))


def cutoff_instant_utc(cutoff_date: date, tz: ZoneInfo) -> datetime:
    """Convert cut-off date to UTC instant.

    The cut-off is the end of cutoff_date (shown as 23:59),
    implemented as local midnight at the start of (cutoff_date + 1 day).
    """
    next_day = cutoff_date + timedelta(days=1)
    return local_midnight_to_utc(next_day, tz)


def goal_start_date_and_instant(created_at: datetime, tz: ZoneInfo) -> tuple[date, datetime]:
    """Day 1 starts at the next midnight in the user's timezone."""
    created_local_date = local_date_of(created_at, tz)
    start_date = created_local_date + timedelta(days=1)
    start_at = local_midnight_to_utc(start_date, tz)
    return start_date, start_at


def last_day_of_month(year: int, month: int) -> date:
    """Return the last date of the given month and year."""
    days_in_month = calendar.monthrange(year, month)[1]
    return date(year, month, days_in_month)
