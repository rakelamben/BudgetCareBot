import sys
from datetime import UTC, date, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import unittest

# Mock third-party dependencies if not installed
for mod in [
    "aiogram",
    "aiogram.filters",
    "aiogram.types",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
    "pydantic",
    "pydantic_settings",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from budgetcare.bot.routers.goals import _get_goal_feed_status_and_cutoff


class DummyPeriod:
    def __init__(self, idx: int, cutoff_at: datetime, status: str = "open"):
        self.idx = idx
        self.cutoff_at = cutoff_at
        self.status = status


class DummyEntry:
    def __init__(self, period_idx: int, is_feeding: bool = True, undone_at: datetime | None = None):
        self.period_idx = period_idx
        self.is_feeding = is_feeding
        self.undone_at = undone_at


class TestGoalsCutoff(unittest.TestCase):
    def setUp(self):
        self.tz = UTC
        self.periods = [
            DummyPeriod(idx=0, cutoff_at=datetime(2026, 11, 8, 23, 59, tzinfo=UTC), status="open"),
            DummyPeriod(idx=1, cutoff_at=datetime(2026, 11, 9, 23, 59, tzinfo=UTC), status="open"),
            DummyPeriod(idx=2, cutoff_at=datetime(2026, 11, 10, 23, 59, tzinfo=UTC), status="open"),
        ]

    def test_unfed_period_shows_current_cutoff(self):
        entries = []
        status, cutoff, remaining = _get_goal_feed_status_and_cutoff(self.periods, entries, self.tz)

        self.assertEqual(status, "Hungry today 🥣")
        self.assertEqual(cutoff, "Sun, 08 Nov 23:59")
        self.assertEqual(remaining, 3)

    def test_fed_period_shows_next_period_cutoff(self):
        entries = [DummyEntry(period_idx=0, is_feeding=True)]
        status, cutoff, remaining = _get_goal_feed_status_and_cutoff(self.periods, entries, self.tz)

        self.assertEqual(status, "Fed today ✅")
        # Next cut-off MUST show period 1 (next day/week/month), NOT period 0!
        self.assertEqual(cutoff, "Mon, 09 Nov 23:59")
        self.assertEqual(remaining, 2)

    def test_undone_feeding_reverts_to_current_cutoff(self):
        entries = [DummyEntry(period_idx=0, is_feeding=True, undone_at=datetime.now(UTC))]
        status, cutoff, remaining = _get_goal_feed_status_and_cutoff(self.periods, entries, self.tz)

        self.assertEqual(status, "Hungry today 🥣")
        self.assertEqual(cutoff, "Sun, 08 Nov 23:59")
        self.assertEqual(remaining, 3)

    def test_final_period_fed_shows_completed(self):
        single_period = [DummyPeriod(idx=0, cutoff_at=datetime(2026, 11, 8, 23, 59, tzinfo=UTC), status="open")]
        entries = [DummyEntry(period_idx=0, is_feeding=True)]

        status, cutoff, remaining = _get_goal_feed_status_and_cutoff(single_period, entries, self.tz)
        self.assertEqual(status, "Fed today ✅")
        self.assertEqual(cutoff, "All feedings completed 🎉")
        self.assertEqual(remaining, 0)

    def test_all_periods_closed_awaiting_tick(self):
        closed_periods = [
            DummyPeriod(idx=0, cutoff_at=datetime(2026, 11, 8, 23, 59, tzinfo=UTC), status="fed"),
        ]
        status, cutoff, remaining = _get_goal_feed_status_and_cutoff(closed_periods, [], self.tz)
        self.assertEqual(status, "Awaiting tick ⏳")
        self.assertEqual(cutoff, "Finalized")
        self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()
