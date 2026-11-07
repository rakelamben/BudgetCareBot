from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from budgetcare.db.tables import EntryTable, FeedingPeriodTable, GoalTable, UserTable
from budgetcare.services.undo import apply_undo


@pytest.fixture
def mock_uow():
    uow = MagicMock()
    uow.goals = MagicMock()
    uow.periods = MagicMock()
    uow.entries = MagicMock()
    uow.users = MagicMock()
    uow.notifications = MagicMock()
    uow.events = MagicMock()
    uow.session = MagicMock()

    uow.session.flush = AsyncMock()
    uow.notifications.delete_pending_by_goal = AsyncMock()
    uow.notifications.add_all = MagicMock()
    uow.events.record = MagicMock()

    return uow


@pytest.mark.asyncio
async def test_apply_undo_within_window(mock_uow):
    now = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
    entry_time = now - timedelta(hours=2)

    entry = EntryTable(
        id=99,
        goal_id=101,
        period_idx=0,
        kind="deposit",
        amount_cents=2000,
        occurred_at=entry_time,
        created_at=entry_time,
        is_feeding=True,
    )
    goal = GoalTable(
        id=101,
        user_id=1,
        name="Test",
        target_cents=10000,
        period_days=10,
        frequency="daily",
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 19),
        start_at=datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
        total_feedings=10,
        nominal_cents=1000,
        last_nominal_cents=1000,
        species="cat",
        pet_name="Milo",
        status="active",
    )

    mock_uow.entries.get_by_id = AsyncMock(return_value=entry)
    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=[])
    mock_uow.entries.list_by_goal = AsyncMock(return_value=[entry])
    mock_uow.users.get_by_id = AsyncMock(
        return_value=UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    )

    res = await apply_undo(mock_uow, user_id=1, entry_id=99, now=now)

    assert res.success is True
    assert entry.undone_at == now
    assert res.deposited_cents == 0


@pytest.mark.asyncio
async def test_apply_undo_after_24_hours_rejected(mock_uow):
    now = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    entry_time = now - timedelta(hours=25)  # 25 hours ago

    entry = EntryTable(
        id=99,
        goal_id=101,
        period_idx=0,
        kind="deposit",
        amount_cents=2000,
        occurred_at=entry_time,
        created_at=entry_time,
        is_feeding=True,
    )
    goal = GoalTable(
        id=101,
        user_id=1,
        name="Test",
        target_cents=10000,
        period_days=10,
        frequency="daily",
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 19),
        start_at=datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
        total_feedings=10,
        nominal_cents=1000,
        last_nominal_cents=1000,
        species="cat",
        pet_name="Milo",
        status="active",
    )

    mock_uow.entries.get_by_id = AsyncMock(return_value=entry)
    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)

    res = await apply_undo(mock_uow, user_id=1, entry_id=99, now=now)

    assert res.success is False
    assert res.error_code == "expired_window"
    assert entry.undone_at is None


@pytest.mark.asyncio
async def test_apply_undo_reopens_graduated_goal(mock_uow):
    now = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
    entry_time = now - timedelta(hours=1)

    entry = EntryTable(
        id=99,
        goal_id=101,
        period_idx=0,
        kind="deposit",
        amount_cents=10000,
        occurred_at=entry_time,
        created_at=entry_time,
        is_feeding=True,
    )
    goal = GoalTable(
        id=101,
        user_id=1,
        name="Test",
        target_cents=10000,
        period_days=10,
        frequency="daily",
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 19),
        start_at=datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
        total_feedings=10,
        nominal_cents=1000,
        last_nominal_cents=1000,
        species="cat",
        pet_name="Milo",
        status="graduated",
        graduated_at=entry_time,
        closed_at=entry_time,
        result={"outcome": "graduated"},
        notifications_enabled=False,
    )
    period = FeedingPeriodTable(
        goal_id=101,
        idx=0,
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 19),
        cutoff_at=now + timedelta(days=9),  # Future cut-off!
        nominal_cents=10000,
        status="open",
    )

    mock_uow.entries.get_by_id = AsyncMock(return_value=entry)
    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=[period])
    mock_uow.entries.list_by_goal = AsyncMock(return_value=[entry])
    mock_uow.users.get_by_id = AsyncMock(
        return_value=UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    )

    res = await apply_undo(mock_uow, user_id=1, entry_id=99, now=now)

    assert res.success is True
    assert res.reopened is True
    assert goal.status == "active"
    assert goal.graduated_at is None
    assert goal.result is None
