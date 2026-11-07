from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from budgetcare.domain.models import GoalFrequency
from budgetcare.domain.schedule import offered_frequencies, plan_schedule


def test_plan_weekly_28_days():
    # Acceptance Criterion 8.1:
    # Given a 28-day, $70 goal starting Monday, when the user picks weekly,
    # then the bot shows 4 feedings of $17.50 with cut-offs on 4 consecutive Sundays at 23:59.
    tz = ZoneInfo("UTC")
    # created on Sunday 2026-11-08 -> starts Monday 2026-11-09
    created_at = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    plan = plan_schedule(
        created_at=created_at,
        tz=tz,
        period_days=28,
        frequency=GoalFrequency.WEEKLY,
        target_cents=7000,
    )
    assert plan is not None
    assert plan.total_feedings == 4
    assert plan.nominal_cents == 1750
    assert plan.last_nominal_cents == 1750
    assert plan.start_date == date(2026, 11, 9)
    assert plan.end_date == date(2026, 12, 6)

    # 4 Sundays: Nov 15, Nov 22, Nov 29, Dec 6
    cutoffs = [p.end_date for p in plan.periods]
    assert cutoffs == [
        date(2026, 11, 15),
        date(2026, 11, 22),
        date(2026, 11, 29),
        date(2026, 12, 6),
    ]


def test_plan_monthly_worked_examples():
    # Worked example: 10 days, monthly, starts Wed 2026-11-25, $20
    # created Tue 2026-11-24
    tz = ZoneInfo("UTC")
    created_at = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
    plan = plan_schedule(
        created_at=created_at,
        tz=tz,
        period_days=10,
        frequency=GoalFrequency.MONTHLY,
        target_cents=2000,
    )
    assert plan is not None
    assert plan.total_feedings == 2
    assert plan.nominal_cents == 1000
    assert [p.end_date for p in plan.periods] == [
        date(2026, 11, 30),
        date(2026, 12, 4),  # end date
    ]


def test_frequency_below_min_feedings_not_offered():
    # Acceptance Criterion 8.1:
    # 3 days, weekly starting Monday 2026-11-09 -> only end date Nov 11 -> n=1 -> not offered
    tz = ZoneInfo("UTC")
    created_at = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    plan = plan_schedule(
        created_at=created_at,
        tz=tz,
        period_days=3,
        frequency=GoalFrequency.WEEKLY,
        target_cents=7000,
    )
    assert plan is None

    # Check offered_frequencies
    offered = offered_frequencies(
        created_at=created_at,
        tz=tz,
        period_days=3,
        target_cents=7000,
    )
    offered_freqs = [o.frequency for o in offered]
    assert GoalFrequency.WEEKLY not in offered_freqs
    assert GoalFrequency.DAILY in offered_freqs


def test_frequency_nominal_below_dollar_not_offered():
    tz = ZoneInfo("UTC")
    created_at = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    # $1 target for 2 days daily -> nominal 50 cents (< $1) -> not offered
    plan = plan_schedule(
        created_at=created_at,
        tz=tz,
        period_days=2,
        frequency=GoalFrequency.DAILY,
        target_cents=100,
    )
    assert plan is None
