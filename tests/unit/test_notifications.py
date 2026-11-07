from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from budgetcare.domain.models import GoalFrequency, NotifKind, PlannedPeriod
from budgetcare.domain.notifications import plan_notifications


def zero_jitter():
    return 0


def test_daily_notifications_planning():
    # Acceptance Criterion 8.4:
    # Daily goal gets 10:00 reminder and 19:00 follow-up on the period's date
    tz = ZoneInfo("UTC")
    now = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
    period = PlannedPeriod(
        idx=0,
        start_date=date(2026, 11, 9),
        end_date=date(2026, 11, 9),
        cutoff_at=datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
        nominal_cents=1000,
    )

    notifs = plan_notifications(
        frequency=GoalFrequency.DAILY,
        periods=[period],
        tz=tz,
        now=now,
        jitter_fn=zero_jitter,
    )
    assert len(notifs) == 2
    assert notifs[0].kind == NotifKind.REMINDER
    assert notifs[0].due_at == datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    assert notifs[1].kind == NotifKind.FOLLOW_UP
    assert notifs[1].due_at == datetime(2026, 11, 9, 19, 0, tzinfo=UTC)


def test_weekly_edge_rule_early_warning():
    # Acceptance Criterion 8.4 & SDD 6.5:
    # Weekly goal with Sunday picked (which is the cutoff day) triggers edge rule:
    # follow-up is replaced by 19:00 early warning on the day before (Saturday).
    tz = ZoneInfo("UTC")
    now = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
    period = PlannedPeriod(
        idx=0,
        start_date=date(2026, 11, 9),  # Monday
        end_date=date(2026, 11, 15),  # Sunday (cutoff)
        cutoff_at=datetime(2026, 11, 16, 0, 0, tzinfo=UTC),
        nominal_cents=1750,
    )

    # Sunday picked (reminder_weekday=6)
    notifs = plan_notifications(
        frequency=GoalFrequency.WEEKLY,
        periods=[period],
        tz=tz,
        now=now,
        reminder_weekday=6,
        jitter_fn=zero_jitter,
    )
    assert len(notifs) == 2
    # Reminder Sunday Nov 15 at 10:00
    assert notifs[0].kind == NotifKind.REMINDER
    assert notifs[0].due_at == datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    # Early warning Saturday Nov 14 at 19:00
    assert notifs[1].kind == NotifKind.EARLY_WARNING
    assert notifs[1].due_at == datetime(2026, 11, 14, 19, 0, tzinfo=UTC)


def test_notifications_disabled():
    tz = ZoneInfo("UTC")
    now = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
    period = PlannedPeriod(
        idx=0,
        start_date=date(2026, 11, 9),
        end_date=date(2026, 11, 9),
        cutoff_at=datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
        nominal_cents=1000,
    )

    notifs = plan_notifications(
        frequency=GoalFrequency.DAILY,
        periods=[period],
        tz=tz,
        now=now,
        notifications_enabled=False,
    )
    assert notifs == []
