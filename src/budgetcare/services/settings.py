from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from budgetcare.db.tables import FeedingPeriodTable, GoalTable, NotificationTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.domain.models import GoalFrequency, PlannedPeriod
from budgetcare.domain.notifications import plan_notifications
from budgetcare.domain.timeutil import (
    get_user_tz,
    goal_start_date_and_instant,
    local_midnight_to_utc,
)


def _replan_notifications_for_goal(
    goal: GoalTable,
    open_periods: list[FeedingPeriodTable],
    tz: ZoneInfo,
    now: datetime,
) -> list[NotificationTable]:
    planned_periods = [
        PlannedPeriod(
            idx=p.idx,
            start_date=p.start_date,
            end_date=p.end_date,
            cutoff_at=p.cutoff_at,
            nominal_cents=p.nominal_cents or 0,
        )
        for p in open_periods
    ]
    planned = plan_notifications(
        frequency=GoalFrequency(goal.frequency),
        periods=planned_periods,
        tz=tz,
        now=now,
        notifications_enabled=goal.notifications_enabled,
        reminder_weekday=goal.reminder_weekday,
        reminder_dom=goal.reminder_dom,
        reminder_on_last=goal.reminder_on_last,
    )
    return [
        NotificationTable(
            goal_id=goal.id,
            period_idx=pn.period_idx,
            kind=pn.kind.value,
            due_at=pn.due_at,
            status="pending",
        )
        for pn in planned
    ]


async def change_user_timezone(
    uow: UnitOfWork,
    user_id: int,
    new_tz_str: str,
    now: datetime | None = None,
) -> None:
    """Apply timezone change going forward (SDD 6.8 & F8)."""
    now_dt = now or datetime.now(UTC)
    user = await uow.users.get_by_id(user_id)
    if not user:
        return

    user.timezone = new_tz_str
    new_tz = get_user_tz(new_tz_str)
    today_local = now_dt.astimezone(new_tz).date()
    min_cutoff = local_midnight_to_utc(today_local + timedelta(days=1), new_tz)

    active_goals = await uow.goals.list_active_by_user(user_id)
    for goal in active_goals:
        periods = await uow.periods.list_by_goal(goal.id)
        open_periods = [p for p in periods if p.status == "open"]

        # Recompute cutoff_at for open periods
        for i, p in enumerate(open_periods):
            recomputed = local_midnight_to_utc(p.end_date, new_tz)
            if i == 0:
                p.cutoff_at = max(recomputed, min_cutoff)
            else:
                p.cutoff_at = recomputed

        # Recompute start_at if goal has not started yet
        if now_dt < goal.start_at:
            _, new_start_at = goal_start_date_and_instant(goal.created_at, new_tz)
            goal.start_at = new_start_at

        # Re-plan pending notifications
        await uow.notifications.delete_pending_by_goal(goal.id)
        if goal.notifications_enabled:
            notif_tables = _replan_notifications_for_goal(
                goal=goal,
                open_periods=open_periods,
                tz=new_tz,
                now=now_dt,
            )
            uow.notifications.add_all(notif_tables)

    uow.events.record(
        name="timezone_set",
        user_id=user_id,
        props={"timezone": new_tz_str},
    )


async def toggle_goal_notifications(
    uow: UnitOfWork,
    goal_id: int,
    enabled: bool,
    now: datetime | None = None,
) -> bool:
    """Toggle notification setting for a goal and re-plan or cancel outbox."""
    now_dt = now or datetime.now(UTC)
    goal = await uow.goals.get_by_id(goal_id)
    if not goal:
        return False

    goal.notifications_enabled = enabled
    await uow.notifications.delete_pending_by_goal(goal.id)

    if enabled:
        user = await uow.users.get_by_id(goal.user_id)
        tz = get_user_tz(user.timezone if user else None)
        periods = await uow.periods.list_by_goal(goal.id)
        open_periods = [p for p in periods if p.status == "open"]

        notif_tables = _replan_notifications_for_goal(
            goal=goal,
            open_periods=open_periods,
            tz=tz,
            now=now_dt,
        )
        uow.notifications.add_all(notif_tables)

    return True


async def update_goal_reminder_time(
    uow: UnitOfWork,
    goal_id: int,
    reminder_weekday: int | None = None,
    reminder_dom: int | None = None,
    reminder_on_last: bool = False,
    now: datetime | None = None,
) -> bool:
    """Update reminder day/date for a goal and re-plan notifications."""
    now_dt = now or datetime.now(UTC)
    goal = await uow.goals.get_by_id(goal_id)
    if not goal:
        return False

    goal.reminder_weekday = reminder_weekday
    goal.reminder_dom = reminder_dom
    goal.reminder_on_last = reminder_on_last

    await uow.notifications.delete_pending_by_goal(goal.id)

    if goal.notifications_enabled:
        user = await uow.users.get_by_id(goal.user_id)
        tz = get_user_tz(user.timezone if user else None)
        periods = await uow.periods.list_by_goal(goal.id)
        open_periods = [p for p in periods if p.status == "open"]

        notif_tables = _replan_notifications_for_goal(
            goal=goal,
            open_periods=open_periods,
            tz=tz,
            now=now_dt,
        )
        uow.notifications.add_all(notif_tables)

    return True


async def delete_single_goal(uow: UnitOfWork, user_id: int, goal_id: int) -> bool:
    """Delete a goal and cascade to periods, entries, and notifications (SDD 9.4 & F7)."""
    goal = await uow.goals.get_by_id(goal_id)
    if not goal or goal.user_id != user_id:
        return False

    await uow.goals.delete_goal(goal_id)
    uow.events.record(name="goal_deleted", user_id=user_id, goal_id=None, props={})
    return True


async def wipe_all_user_data(uow: UnitOfWork, user_id: int) -> bool:
    """Delete entire user and cascade delete all related goals, entries, events (SDD 9.4 & F7)."""
    user = await uow.users.get_by_id(user_id)
    if not user:
        return False

    await uow.session.delete(user)
    return True
