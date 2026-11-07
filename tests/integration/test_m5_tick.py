from datetime import UTC, datetime, timedelta

import pytest

from budgetcare.db.tables import JobLockTable
from budgetcare.db.uow import uow_factory
from budgetcare.services.goals import create_goal_from_wizard
from budgetcare.services.tick import run_tick
from budgetcare.services.users import get_or_create_user


@pytest.mark.asyncio
async def test_tick_closes_due_periods_and_records_run_in_database():
    test_tg_id = 999005
    test_chat_id = 888005

    # 1. Ensure tick lock exists and is unlocked in database
    async with uow_factory() as uow:
        lock = await uow.session.get(JobLockTable, "tick")
        if not lock:
            uow.session.add(
                JobLockTable(
                    name="tick",
                    locked_until=datetime.fromtimestamp(0, tz=UTC),
                )
            )
        else:
            lock.locked_until = datetime.fromtimestamp(0, tz=UTC)
            lock.locked_by = None
        await uow.session.flush()

        # 2. Setup user with timezone
        user, _ = await get_or_create_user(uow, test_tg_id, test_chat_id)
        user.timezone = "Asia/Jakarta"
        await uow.session.flush()

        # Clean old test goals
        existing = await uow.goals.list_active_by_user(user.id)
        for g in existing:
            await uow.session.delete(g)
        await uow.session.flush()

        # 3. Create goal
        now = datetime.now(UTC)
        draft = {
            "name": "M5 Tick Test Goal",
            "target_cents": 1000,
            "period_days": 3,
            "frequency": "daily",
            "species": "hamster",
            "pet_name": "Peanut",
            "notifications_enabled": True,
            "reminder_weekday": None,
            "reminder_dom": None,
            "reminder_on_last": False,
        }
        goal = await create_goal_from_wizard(uow, user, draft, now)
        goal_id = goal.id

        # 4. Artificially backdate period 0 cutoff to 10 minutes in the past
        periods = await uow.periods.list_by_goal(goal_id)
        assert len(periods) == 3
        p0 = periods[0]
        p0.cutoff_at = now - timedelta(minutes=10)
        await uow.session.flush()

    # 5. Execute tick
    stats = await run_tick(now=now)

    assert stats.skipped is None
    assert stats.periods_closed >= 1
    assert stats.periods_missed >= 1

    # 6. Verify period 0 is marked missed in database
    async with uow_factory() as uow:
        p0_updated = await uow.periods.get_period(goal_id, 0)
        assert p0_updated is not None
        assert p0_updated.status == "missed"
        assert p0_updated.closed_at is not None
