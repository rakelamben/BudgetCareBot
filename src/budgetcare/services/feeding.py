from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from budgetcare.db.tables import EntryTable, GoalTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.domain.models import MoodTier
from budgetcare.domain.scoring import (
    calculate_condition,
    calculate_final_service_quality,
    calculate_live_service_quality,
    calculate_mood_tier,
    calculate_surplus,
    get_result_title,
)
from budgetcare.domain.timeutil import get_user_tz


@dataclass(frozen=True)
class FeedingResult:
    success: bool
    goal: GoalTable | None
    entry: EntryTable | None = None
    is_extra: bool = False
    is_free_food: bool = False
    is_graduated: bool = False
    condition_pct: int = 100
    quality_pct: int = 100
    deposited_cents: int = 0
    target_cents: int = 0
    mood_tier: MoodTier = MoodTier.TIER_4
    next_cutoff: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


async def feed_goal(
    uow: UnitOfWork,
    user_id: int,
    goal_id: int,
    amount_cents: int,
    occurred_at: datetime | None = None,
    source_update_id: int | None = None,
) -> FeedingResult:
    """Classify and record a feeding entry (deposit or free food) per SDD 6.3."""
    if occurred_at is None:
        occurred_at = datetime.now(UTC)

    # 1. Lock goal row
    goal = await uow.goals.lock_goal(goal_id)
    if not goal or goal.user_id != user_id:
        return FeedingResult(
            success=False,
            goal=None,
            error_code="not_found",
            error_message="Goal not found.",
        )

    # 2. Check if goal is active
    if goal.status != "active":
        return FeedingResult(
            success=False,
            goal=goal,
            error_code="goal_closed",
            error_message=f"Goal is {goal.status}.",
        )

    # 3. Fetch periods
    periods = await uow.periods.list_by_goal(goal_id)
    if not periods:
        return FeedingResult(
            success=False,
            goal=goal,
            error_code="no_periods",
            error_message="No periods found for goal.",
        )

    last_period = periods[-1]
    if occurred_at > last_period.cutoff_at:
        return FeedingResult(
            success=False,
            goal=goal,
            error_code="goal_ended",
            error_message="Goal has ended.",
        )

    # 4. Period lookup and classification (SDD 6.3)
    target_period = None
    for p in periods:
        if p.cutoff_at > occurred_at:
            target_period = p
            break
    if target_period is None:
        target_period = last_period

    is_feeding: bool
    kind: str
    is_extra: bool = False
    is_free_food: bool = amount_cents == 0

    if target_period.status != "open":
        # Period already closed by tick
        if amount_cents == 0:
            return FeedingResult(
                success=False,
                goal=goal,
                error_code="period_closed",
                error_message="Current period is already closed.",
            )
        is_feeding = False
        kind = "deposit"
        is_extra = True
    else:
        # Open period (including H+0 advance first feeding for period 0)
        already_fed = await uow.entries.has_active_feeding(goal_id, target_period.idx)
        if not already_fed:
            is_feeding = True
            kind = "free_food" if amount_cents == 0 else "deposit"
        else:
            if amount_cents == 0:
                return FeedingResult(
                    success=False,
                    goal=goal,
                    error_code="already_fed",
                    error_message="Period already fed. Free food cannot be used twice.",
                )
            is_feeding = False
            kind = "deposit"
            is_extra = True

    # 5. Insert Entry
    entry = EntryTable(
        goal_id=goal_id,
        period_idx=target_period.idx,
        kind=kind,
        amount_cents=amount_cents,
        occurred_at=occurred_at,
        is_feeding=is_feeding,
        source_update_id=source_update_id,
    )
    uow.entries.add(entry)
    await uow.session.flush()

    # 6. Recompute metrics
    all_entries = await uow.entries.list_by_goal(goal_id)
    deposited_cents = sum(e.amount_cents for e in all_entries if e.undone_at is None)
    free_food_count = sum(1 for e in all_entries if e.kind == "free_food" and e.undone_at is None)

    missed_count = sum(1 for p in periods if p.status == "missed")
    condition_pct = calculate_condition(missed_count, goal.total_feedings)
    mood_tier = calculate_mood_tier(missed_count, goal.total_feedings)

    user = await uow.users.get_by_id(user_id)
    tz = get_user_tz(user.timezone if user else None)
    today_local = occurred_at.astimezone(tz).date()
    days_elapsed = max(0, min(goal.period_days, (today_local - goal.start_date).days))
    live_quality = calculate_live_service_quality(
        deposited_cents=deposited_cents,
        target_cents=goal.target_cents,
        days_elapsed=days_elapsed,
        period_days=goal.period_days,
    )
    quality_pct = round(live_quality * 100)

    # 7. Check Graduation (SDD 6.6)
    is_graduated = False
    if deposited_cents >= goal.target_cents:
        is_graduated = True
        goal.status = "graduated"
        goal.graduated_at = occurred_at
        goal.closed_at = occurred_at

        days_taken = max(1, min(goal.period_days, (today_local - goal.start_date).days + 1))
        final_quality = calculate_final_service_quality(
            deposited_cents=deposited_cents,
            target_cents=goal.target_cents,
        )
        final_quality_pct = round(final_quality * 100)
        surplus_cents = calculate_surplus(deposited_cents, goal.target_cents)
        title = get_result_title("graduated", mood_tier)

        result_payload: dict[str, Any] = {
            "outcome": "graduated",
            "final_condition_pct": condition_pct,
            "final_quality_pct": final_quality_pct,
            "mood_tier": mood_tier.value,
            "title": title,
            "days_taken": days_taken,
            "deposited_cents": deposited_cents,
            "surplus_cents": surplus_cents,
            "free_food_count": free_food_count,
            "closed_at": occurred_at.isoformat(),
        }
        goal.result = result_payload

        # Cancel pending notifications
        await uow.notifications.cancel_pending_by_goal(goal_id)

        # Audit event
        uow.events.record(
            name="goal_graduated",
            user_id=user_id,
            goal_id=goal_id,
            props={
                "days_taken": days_taken,
                "condition_pct": condition_pct,
                "final_quality_pct": final_quality_pct,
                "surplus_cents": surplus_cents,
            },
        )

    # 8. Record feed event
    if kind == "free_food":
        event_name = "free_food_used"
    elif is_feeding:
        event_name = "feeding_logged"
    else:
        event_name = "extra_deposit"

    uow.events.record(
        name=event_name,
        user_id=user_id,
        goal_id=goal_id,
        props={"amount_cents": amount_cents, "period_idx": target_period.idx},
    )

    next_cutoff = target_period.cutoff_at if target_period.status == "open" else None

    return FeedingResult(
        success=True,
        goal=goal,
        entry=entry,
        is_extra=is_extra,
        is_free_food=is_free_food,
        is_graduated=is_graduated,
        condition_pct=condition_pct,
        quality_pct=quality_pct,
        deposited_cents=deposited_cents,
        target_cents=goal.target_cents,
        mood_tier=mood_tier,
        next_cutoff=next_cutoff,
    )
