from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from budgetcare.domain.timeutil import (
    cutoff_instant_utc,
    get_user_tz,
    goal_start_date_and_instant,
    last_day_of_month,
)


def test_get_user_tz():
    tz = get_user_tz("Asia/Jakarta")
    assert tz.key == "Asia/Jakarta"
    tz_invalid = get_user_tz("Invalid/Zone")
    assert tz_invalid.key == "UTC"


def test_goal_start_date_and_instant():
    tz = ZoneInfo("Asia/Jakarta")  # UTC+7
    # 2026-11-08 at 14:00 UTC is 21:00 in Jakarta
    created_at = datetime(2026, 11, 8, 14, 0, tzinfo=UTC)
    start_date, start_at = goal_start_date_and_instant(created_at, tz)

    assert start_date == date(2026, 11, 9)
    # 2026-11-09 00:00 Jakarta is 2026-11-08 17:00 UTC
    assert start_at == datetime(2026, 11, 8, 17, 0, tzinfo=UTC)


def test_cutoff_instant_utc():
    tz = ZoneInfo("Asia/Jakarta")  # UTC+7
    # Cutoff date 2026-11-15 (shown as 23:59 Jakarta)
    # is implemented as midnight 2026-11-16 00:00 Jakarta -> 2026-11-15 17:00 UTC
    cutoff_d = date(2026, 11, 15)
    cutoff_at = cutoff_instant_utc(cutoff_d, tz)
    assert cutoff_at == datetime(2026, 11, 15, 17, 0, tzinfo=UTC)


def test_last_day_of_month():
    assert last_day_of_month(2026, 2) == date(2026, 2, 28)
    assert last_day_of_month(2024, 2) == date(2024, 2, 29)  # Leap year
    assert last_day_of_month(2026, 4) == date(2026, 4, 30)
    assert last_day_of_month(2026, 12) == date(2026, 12, 31)
