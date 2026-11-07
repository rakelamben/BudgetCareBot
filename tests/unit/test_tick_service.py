from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from budgetcare.db.tables import EntryTable, FeedingPeriodTable, GoalTable
from budgetcare.services.tick import close_goal_periods, run_tick


@pytest.fixture
def mock_uow():
    uow = MagicMock()
    uow.goals = MagicMock()
    uow.periods = MagicMock()
    uow.entries = MagicMock()
    uow.users = MagicMock()
    uow.notifications = MagicMock()
    uow.events = MagicMock()
    uow.locks = MagicMock()
    uow.tick_runs = MagicMock()
    uow.session = MagicMock()

    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.session.flush = AsyncMock()

    return uow


def make_test_goal(goal_id: int = 101, notifications_enabled: bool = True) -> GoalTable:
    return GoalTable(
        id=goal_id,
        user_id=1,
        name="Trip M5",
        target_cents=5000,
        period_days=5,
        frequency="daily",
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 14),
        start_at=datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
        total_feedings=5,
        nominal_cents=1000,
        last_nominal_cents=1000,
        species="cat",
        pet_name="Milo",
        notifications_enabled=notifications_enabled,
        status="active",
    )


@pytest.mark.asyncio
async def test_close_goal_periods_fed_and_missed(mock_uow):
    goal = make_test_goal()
    now = datetime(2026, 11, 12, 17, 5, tzinfo=UTC)

    p0 = FeedingPeriodTable(
        goal_id=goal.id,
        idx=0,
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 10),
        cutoff_at=datetime(2026, 11, 10, 16, 59, tzinfo=UTC),
        nominal_cents=1000,
        status="open",
    )
    p1 = FeedingPeriodTable(
        goal_id=goal.id,
        idx=1,
        start_date=date(2026, 11, 11),
        end_date=date(2026, 11, 11),
        cutoff_at=datetime(2026, 11, 11, 16, 59, tzinfo=UTC),
        nominal_cents=1000,
        status="open",
    )

    mock_uow.periods.list_due_open = AsyncMock(return_value=[p0, p1])
    # Period 0 was fed, Period 1 was missed
    mock_uow.entries.has_active_feeding = AsyncMock(side_effect=lambda g_id, idx: idx == 0)
    mock_uow.periods.close_period = AsyncMock()
    mock_uow.periods.all_periods_closed = AsyncMock(return_value=False)

    closed, missed, outcome = await close_goal_periods(mock_uow, goal, now)

    assert closed == 2
    assert missed == 1
    assert outcome is None
    assert mock_uow.periods.close_period.call_count == 2
    mock_uow.periods.close_period.assert_any_call(goal.id, 0, "fed", now)
    mock_uow.periods.close_period.assert_any_call(goal.id, 1, "missed", now)


@pytest.mark.asyncio
async def test_close_goal_periods_finalizes_expired_with_notification(mock_uow):
    goal = make_test_goal(notifications_enabled=True)
    now = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)

    p_last = FeedingPeriodTable(
        goal_id=goal.id,
        idx=4,
        start_date=date(2026, 11, 14),
        end_date=date(2026, 11, 14),
        cutoff_at=datetime(2026, 11, 14, 16, 59, tzinfo=UTC),
        nominal_cents=1000,
        status="open",
    )

    mock_uow.periods.list_due_open = AsyncMock(return_value=[p_last])
    mock_uow.entries.has_active_feeding = AsyncMock(return_value=False)
    mock_uow.periods.close_period = AsyncMock()
    mock_uow.periods.all_periods_closed = AsyncMock(return_value=True)

    # 1 feeding of $10 recorded, target is $50 -> Expired
    entry = EntryTable(
        id=1,
        goal_id=goal.id,
        period_idx=0,
        kind="deposit",
        amount_cents=1000,
        occurred_at=now,
        is_feeding=True,
    )
    mock_uow.entries.list_by_goal = AsyncMock(return_value=[entry])

    all_p = [
        FeedingPeriodTable(goal_id=goal.id, idx=i, status="fed" if i == 0 else "missed")
        for i in range(5)
    ]
    mock_uow.periods.list_by_goal = AsyncMock(return_value=all_p)
    mock_uow.notifications.cancel_pending_by_goal = AsyncMock()
    mock_uow.notifications.add_all = MagicMock()
    mock_uow.events.record = MagicMock()

    closed, missed, outcome = await close_goal_periods(mock_uow, goal, now)

    assert closed == 1
    assert missed == 1
    assert outcome == "expired"
    assert goal.status == "expired"
    assert goal.result is not None
    assert goal.result["outcome"] == "expired"
    assert goal.result["deposited_cents"] == 1000

    # Verifies result notification is created
    mock_uow.notifications.add_all.assert_called_once()
    added_notifs = mock_uow.notifications.add_all.call_args[0][0]
    assert len(added_notifs) == 1
    assert added_notifs[0].kind == "result"


@pytest.mark.asyncio
async def test_run_tick_lease_locked_returns_skipped():
    now = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)

    mock_uow = MagicMock()
    mock_uow.locks.acquire_lease = AsyncMock(return_value=False)

    with patch("budgetcare.services.tick.uow_factory") as mock_factory:
        mock_factory.return_value.__aenter__.return_value = mock_uow
        mock_factory.return_value.__aexit__ = AsyncMock()

        stats = await run_tick(now=now)
        assert stats.skipped == "locked"
        mock_uow.locks.acquire_lease.assert_called_once()
