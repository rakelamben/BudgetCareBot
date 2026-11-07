from datetime import datetime
from typing import Any

from budgetcare.config import settings
from budgetcare.db.tables import FeedingPeriodTable, GoalTable, NotificationTable, UserTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.domain.models import GoalFrequency
from budgetcare.domain.notifications import plan_notifications
from budgetcare.domain.schedule import plan_schedule
from budgetcare.domain.timeutil import get_user_tz


async def create_goal_from_wizard(
    uow: UnitOfWork,
    user: UserTable,
    draft: dict[str, Any],
    now: datetime,
) -> GoalTable:
    if not user.timezone:
        raise ValueError("User timezone is not set.")

    tz = get_user_tz(user.timezone)

    # 1. Technical cap check (SDD Section 13)
    active_count = await uow.goals.count_active_by_user(user.id)
    if active_count >= settings.MAX_ACTIVE_GOALS_PER_USER:
        raise ValueError(f"Limit of {settings.MAX_ACTIVE_GOALS_PER_USER} active goals reached.")

    # 2. Re-confirm rule: recompute plan_schedule with current time
    frequency = GoalFrequency(draft["frequency"])
    plan = plan_schedule(
        created_at=now,
        tz=tz,
        period_days=int(draft["period_days"]),
        frequency=frequency,
        target_cents=int(draft["target_cents"]),
        min_nominal_cents=settings.MIN_NOMINAL_CENTS,
    )
    if plan is None:
        raise ValueError("Schedule could not be computed from draft.")

    # 3. Create Goal
    goal = GoalTable(
        user_id=user.id,
        name=draft["name"],
        target_cents=draft["target_cents"],
        period_days=draft["period_days"],
        frequency=frequency.value,
        start_date=plan.start_date,
        end_date=plan.end_date,
        start_at=plan.start_at,
        total_feedings=plan.total_feedings,
        nominal_cents=plan.nominal_cents,
        last_nominal_cents=plan.last_nominal_cents,
        notifications_enabled=draft.get("notifications_enabled", True),
        reminder_weekday=draft.get("reminder_weekday"),
        reminder_dom=draft.get("reminder_dom"),
        reminder_on_last=draft.get("reminder_on_last", False),
        species=draft["species"],
        pet_name=draft["pet_name"],
        status="active",
    )
    uow.goals.add(goal)
    await uow.session.flush()

    # 4. Create Feeding Periods
    period_tables = [
        FeedingPeriodTable(
            goal_id=goal.id,
            idx=p.idx,
            start_date=p.start_date,
            end_date=p.end_date,
            cutoff_at=p.cutoff_at,
            nominal_cents=p.nominal_cents,
            status="open",
        )
        for p in plan.periods
    ]
    uow.periods.add_all(period_tables)
    await uow.session.flush()

    # 5. Plan and Create Notifications
    if goal.notifications_enabled:
        planned_notifs = plan_notifications(
            frequency=frequency,
            periods=plan.periods,
            tz=tz,
            now=now,
            notifications_enabled=True,
            reminder_weekday=goal.reminder_weekday,
            reminder_dom=goal.reminder_dom,
            reminder_on_last=goal.reminder_on_last,
        )
        notif_tables = [
            NotificationTable(
                goal_id=goal.id,
                period_idx=np.period_idx,
                kind=np.kind.value,
                due_at=np.due_at,
                status="pending",
            )
            for np in planned_notifs
        ]
        uow.notifications.add_all(notif_tables)
        await uow.session.flush()

    # 6. Clear conversation draft
    await uow.conversations.delete(user.id)

    # 7. Record Analytics Event
    uow.events.record(
        name="goal_created",
        user_id=user.id,
        goal_id=goal.id,
        props={
            "frequency": goal.frequency,
            "period_days": goal.period_days,
            "target_cents": goal.target_cents,
            "notifications": goal.notifications_enabled,
        },
    )

    return goal
