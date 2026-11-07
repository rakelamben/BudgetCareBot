import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from budgetcare.domain.models import GoalFrequency, NotifKind, PlannedNotification, PlannedPeriod
from budgetcare.domain.timeutil import last_day_of_month


def _to_utc(local_d: date, local_t: time, tz: ZoneInfo, jitter_s: int) -> datetime:
    dt = datetime.combine(local_d, local_t, tzinfo=tz)
    return dt.astimezone(ZoneInfo("UTC")) + timedelta(seconds=jitter_s)


def plan_notifications_for_period(
    frequency: GoalFrequency,
    period: PlannedPeriod,
    tz: ZoneInfo,
    now: datetime,
    reminder_weekday: int | None = None,
    reminder_dom: int | None = None,
    reminder_on_last: bool = False,
    jitter_fn=None,
) -> list[PlannedNotification]:
    """Plan reminder, follow-up, or early-warning notifications for a single period."""
    if jitter_fn is None:
        jitter_fn = lambda: random.randint(0, 299)

    p_start = period.start_date
    p_end = period.end_date

    # 1. Determine the reminder local date
    if frequency == GoalFrequency.DAILY:
        rem_date = p_end
    elif frequency == GoalFrequency.WEEKLY:
        target_wd = reminder_weekday if reminder_weekday is not None else 6  # default Sunday
        # Find date in [p_start, p_end] matching target_wd
        curr = p_start
        matched = None
        while curr <= p_end:
            if curr.weekday() == target_wd:
                matched = curr
                break
            curr += timedelta(days=1)
        if matched is None:
            # Clamping rule: before first day -> first day, after last day -> last day
            rem_date = p_end
        else:
            rem_date = matched
    elif frequency == GoalFrequency.MONTHLY:
        if reminder_on_last:
            rem_date = last_day_of_month(p_end.year, p_end.month)
        elif reminder_dom is not None:
            try:
                rem_date = date(p_end.year, p_end.month, reminder_dom)
            except ValueError:
                rem_date = last_day_of_month(p_end.year, p_end.month)
        else:
            rem_date = p_end
        # Clamp to period boundaries
        if rem_date < p_start:
            rem_date = p_start
        elif rem_date > p_end:
            rem_date = p_end

    # Reminder time is always 10:00 local
    rem_utc = _to_utc(rem_date, time(10, 0), tz, jitter_fn())

    # 2. Determine Follow-up vs Early Warning (Edge Rule)
    # Edge condition: reminder date is cutoff date, or follow-up date lands after cutoff date
    is_edge = False
    followup_date: date | None = None
    followup_time: time | None = None

    if frequency == GoalFrequency.DAILY:
        # Daily: follow-up is 19:00 same day (which is the cutoff day)
        followup_date = rem_date
        followup_time = time(19, 0)
    elif frequency == GoalFrequency.WEEKLY:
        # Weekly: follow-up is 10:00 next day
        cand = rem_date + timedelta(days=1)
        if rem_date == p_end or cand > p_end:
            is_edge = True
        else:
            followup_date = cand
            followup_time = time(10, 0)
    elif frequency == GoalFrequency.MONTHLY:
        # Monthly: follow-up is 19:00 next day
        cand = rem_date + timedelta(days=1)
        if rem_date == p_end or cand > p_end:
            is_edge = True
        else:
            followup_date = cand
            followup_time = time(19, 0)

    planned: list[PlannedNotification] = []

    # Add reminder if not in the past
    if rem_utc > now:
        planned.append(
            PlannedNotification(
                period_idx=period.idx,
                kind=NotifKind.REMINDER,
                due_at=rem_utc,
            )
        )

    # Add second notification (Early Warning or Follow-up)
    if is_edge:
        # Early warning at 19:00 the day before cutoff date
        ew_date = p_end - timedelta(days=1)
        # Omitted when that day is before the period's first day
        if ew_date >= p_start:
            ew_utc = _to_utc(ew_date, time(19, 0), tz, jitter_fn())
            if ew_utc > now:
                planned.append(
                    PlannedNotification(
                        period_idx=period.idx,
                        kind=NotifKind.EARLY_WARNING,
                        due_at=ew_utc,
                    )
                )
    else:
        if followup_date is not None and followup_time is not None:
            fu_utc = _to_utc(followup_date, followup_time, tz, jitter_fn())
            if fu_utc > now:
                planned.append(
                    PlannedNotification(
                        period_idx=period.idx,
                        kind=NotifKind.FOLLOW_UP,
                        due_at=fu_utc,
                    )
                )

    return planned


def plan_notifications(
    frequency: GoalFrequency,
    periods: list[PlannedPeriod],
    tz: ZoneInfo,
    now: datetime,
    notifications_enabled: bool = True,
    reminder_weekday: int | None = None,
    reminder_dom: int | None = None,
    reminder_on_last: bool = False,
    jitter_fn=None,
) -> list[PlannedNotification]:
    """Plan notifications for all given open periods."""
    if not notifications_enabled:
        return []

    all_planned: list[PlannedNotification] = []
    for period in periods:
        period_notifs = plan_notifications_for_period(
            frequency=frequency,
            period=period,
            tz=tz,
            now=now,
            reminder_weekday=reminder_weekday,
            reminder_dom=reminder_dom,
            reminder_on_last=reminder_on_last,
            jitter_fn=jitter_fn,
        )
        all_planned.extend(period_notifs)

    return all_planned
