from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from budgetcare.db.tables import EntryTable, GoalTable, NotificationTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.domain.models import GoalFrequency, PlannedPeriod
from budgetcare.domain.notifications import plan_notifications
from budgetcare.domain.scoring import (
    calculate_condition,
    calculate_live_service_quality,
)
from budgetcare.domain.timeutil import get_user_tz

UNDO_WINDOW_HOURS = 24


@dataclass(frozen=True)
class UndoResult:
    success: bool
    goal: GoalTable | None
    entry: EntryTable | None = None
    reopened: bool = False
    condition_pct: int = 100
    quality_pct: int = 100
    deposited_cents: int = 0
    target_cents: int = 0
    error_code: str | None = None
    error_message: str | None = None


async def get_undo_candidate(uow: UnitOfWork, user_id: int) -> EntryTable | None:
    """Find user's most recent active entry created within 24 hours."""
    since = datetime.now(UTC) - timedelta(hours=UNDO_WINDOW_HOURS)
    return await uow.entries.get_latest_active_by_user(user_id=user_id, since=since)


async def apply_undo(
    uow: UnitOfWork,
    user_id: int,
    entry_id: int,
    now: datetime | None = None,
) -> UndoResult:
    """Revert an entry within 24 hours, adjusting metrics and reopening goal if graduated (SDD 6.7)."""
    if now is None:
        now = datetime.now(UTC)

    # 1. Fetch entry
    entry = await uow.entries.get_by_id(entry_id)
    if not entry or entry.undone_at is not None:
        return UndoResult(
            success=False,
            goal=None,
            error_code="not_found",
            error_message="Entry not found or already undone.",
        )

    # 2. Lock goal
    goal = await uow.goals.lock_goal(entry.goal_id)
    if not goal or goal.user_id != user_id:
        return UndoResult(
            success=False,
            goal=None,
            error_code="unauthorized",
            error_message="Goal does not belong to user.",
        )

    # 3. Check 24-hour window
    if now - entry.occurred_at > timedelta(hours=UNDO_WINDOW_HOURS):
        return UndoResult(
            success=False,
            goal=goal,
            entry=entry,
            error_code="expired_window",
            error_message="Entry occurred more than 24 hours ago and cannot be undone.",
        )

    # 4. Mark undone
    entry.undone_at = now
    await uow.session.flush()

    # 5. Check if goal was graduated and needs reopening
    was_graduated = goal.status == "graduated"
    reopened = False

    periods = await uow.periods.list_by_goal(goal.id)
    all_entries = await uow.entries.list_by_goal(goal.id)
    deposited_cents = sum(e.amount_cents for e in all_entries if e.undone_at is None)

    if was_graduated and deposited_cents < goal.target_cents:
        last_cutoff = periods[-1].cutoff_at if periods else now
        if last_cutoff > now:
            # Last cut-off has not passed: reopen goal!
            goal.status = "active"
            goal.graduated_at = None
            goal.closed_at = None
            goal.result = None
            reopened = True

            # Re-plan pending notifications
            if goal.notifications_enabled:
                await uow.notifications.delete_pending_by_goal(goal.id)
                user = await uow.users.get_by_id(user_id)
                tz = get_user_tz(user.timezone if user else None)
                open_planned_periods = [
                    PlannedPeriod(
                        idx=p.idx,
                        start_date=p.start_date,
                        end_date=p.end_date,
                        cutoff_at=p.cutoff_at,
                        nominal_cents=p.nominal_cents,
                    )
                    for p in periods
                    if p.status == "open"
                ]
                notifs = plan_notifications(
                    frequency=GoalFrequency(goal.frequency),
                    periods=open_planned_periods,
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
                    for np in notifs
                ]
                uow.notifications.add_all(notif_tables)

    # 6. Recompute metrics
    missed_count = sum(1 for p in periods if p.status == "missed")
    condition_pct = calculate_condition(missed_count, goal.total_feedings)

    user = await uow.users.get_by_id(user_id)
    tz = get_user_tz(user.timezone if user else None)
    today_local = now.astimezone(tz).date()
    days_elapsed = max(0, min(goal.period_days, (today_local - goal.start_date).days))
    live_quality = calculate_live_service_quality(
        deposited_cents=deposited_cents,
        target_cents=goal.target_cents,
        days_elapsed=days_elapsed,
        period_days=goal.period_days,
    )
    quality_pct = round(live_quality * 100)

    # 7. Audit event
    uow.events.record(
        name="entry_undone",
        user_id=user_id,
        goal_id=goal.id,
        props={
            "entry_id": entry.id,
            "kind": entry.kind,
            "amount_cents": entry.amount_cents,
            "reopened": reopened,
        },
    )

    return UndoResult(
        success=True,
        goal=goal,
        entry=entry,
        reopened=reopened,
        condition_pct=condition_pct,
        quality_pct=quality_pct,
        deposited_cents=deposited_cents,
        target_cents=goal.target_cents,
    )
