from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from budgetcare.domain.models import (
    GoalFrequency,
    OfferedFrequency,
    PlannedPeriod,
    SchedulePlan,
)
from budgetcare.domain.timeutil import (
    cutoff_instant_utc,
    goal_start_date_and_instant,
    last_day_of_month,
)


def plan_schedule(
    created_at: datetime,
    tz: ZoneInfo,
    period_days: int,
    frequency: GoalFrequency,
    target_cents: int,
    min_nominal_cents: int = 100,
) -> SchedulePlan | None:
    """Compute feeding periods and nominal amounts for a goal.

    Returns SchedulePlan if valid (n >= 2 and nominal >= min_nominal_cents), else None.
    """
    if period_days < 2 or period_days > 365 or target_cents <= 0:
        return None

    start_date, start_at = goal_start_date_and_instant(created_at, tz)
    end_date = start_date + timedelta(days=period_days - 1)

    cutoff_dates: list[date] = []

    if frequency == GoalFrequency.DAILY:
        curr = start_date
        while curr <= end_date:
            cutoff_dates.append(curr)
            curr += timedelta(days=1)

    elif frequency == GoalFrequency.WEEKLY:
        curr = start_date
        while curr <= end_date:
            # Sunday is weekday() == 6 in Python
            if curr.weekday() == 6:
                cutoff_dates.append(curr)
            curr += timedelta(days=1)

    elif frequency == GoalFrequency.MONTHLY:
        curr = start_date
        while curr <= end_date:
            month_end = last_day_of_month(curr.year, curr.month)
            if month_end <= end_date and month_end not in cutoff_dates:
                cutoff_dates.append(month_end)
            # Advance to next month
            if curr.month == 12:
                curr = date(curr.year + 1, 1, 1)
            else:
                curr = date(curr.year, curr.month + 1, 1)

    # The goal's end date is always a final cut-off, even if not a regular due date
    if not cutoff_dates or cutoff_dates[-1] != end_date:
        cutoff_dates.append(end_date)

    n = len(cutoff_dates)
    if n < 2:
        return None

    nominal = target_cents // n
    if nominal < min_nominal_cents:
        return None

    last_nominal = target_cents - nominal * (n - 1)

    periods: list[PlannedPeriod] = []
    p_start = start_date
    for idx, c_date in enumerate(cutoff_dates):
        p_nominal = last_nominal if idx == n - 1 else nominal
        p_cutoff_at = cutoff_instant_utc(c_date, tz)
        periods.append(
            PlannedPeriod(
                idx=idx,
                start_date=p_start,
                end_date=c_date,
                cutoff_at=p_cutoff_at,
                nominal_cents=p_nominal,
            )
        )
        p_start = c_date + timedelta(days=1)

    return SchedulePlan(
        frequency=frequency,
        periods=periods,
        total_feedings=n,
        nominal_cents=nominal,
        last_nominal_cents=last_nominal,
        start_date=start_date,
        end_date=end_date,
        start_at=start_at,
    )


def offered_frequencies(
    created_at: datetime,
    tz: ZoneInfo,
    period_days: int,
    target_cents: int,
    min_nominal_cents: int = 100,
) -> list[OfferedFrequency]:
    """Return all valid frequencies and their schedule plans."""
    offered: list[OfferedFrequency] = []
    for freq in [GoalFrequency.DAILY, GoalFrequency.WEEKLY, GoalFrequency.MONTHLY]:
        plan = plan_schedule(
            created_at,
            tz,
            period_days,
            freq,
            target_cents,
            min_nominal_cents=min_nominal_cents,
        )
        if plan is not None:
            offered.append(OfferedFrequency(frequency=freq, plan=plan))
    return offered
