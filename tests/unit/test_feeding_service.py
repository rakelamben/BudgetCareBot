from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from budgetcare.db.tables import EntryTable, FeedingPeriodTable, GoalTable, UserTable
from budgetcare.services.feeding import feed_goal


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
    uow.notifications.cancel_pending_by_goal = AsyncMock()
    uow.events.record = MagicMock()

    return uow


def make_dummy_goal(
    user_id: int = 1,
    target_cents: int = 10000,
    status: str = "active",
    start_date: date = date(2026, 11, 10),
) -> GoalTable:
    goal = GoalTable(
        id=101,
        user_id=user_id,
        name="Test Vacation",
        target_cents=target_cents,
        period_days=10,
        frequency="daily",
        start_date=start_date,
        end_date=date(2026, 11, 19),
        start_at=datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
        total_feedings=10,
        nominal_cents=1000,
        last_nominal_cents=1000,
        species="cat",
        pet_name="Milo",
        status=status,
    )
    return goal


def make_dummy_periods(goal_id: int = 101) -> list[FeedingPeriodTable]:
    periods = []
    base_date = date(2026, 11, 10)
    for i in range(10):
        d = base_date + timedelta(days=i)
        cutoff = datetime(d.year, d.month, d.day, 16, 59, tzinfo=UTC)
        periods.append(
            FeedingPeriodTable(
                goal_id=goal_id,
                idx=i,
                start_date=d,
                end_date=d,
                cutoff_at=cutoff,
                nominal_cents=1000,
                status="open",
            )
        )
    return periods


@pytest.mark.asyncio
async def test_pre_start_deposit_accepted_as_feeding(mock_uow):
    goal = make_dummy_goal()
    periods = make_dummy_periods()

    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=periods)
    mock_uow.entries.has_active_feeding = AsyncMock(return_value=False)
    mock_uow.entries.list_by_goal = AsyncMock(return_value=[])
    mock_uow.users.get_by_id = AsyncMock(
        return_value=UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    )

    # Day 0 (before start_at)
    occurred_at = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    res = await feed_goal(
        mock_uow, user_id=1, goal_id=101, amount_cents=1000, occurred_at=occurred_at
    )

    assert res.success is True
    assert res.is_extra is False
    assert res.entry.is_feeding is True
    assert res.entry.kind == "deposit"
    assert res.entry.period_idx == 0
    mock_uow.entries.add.assert_called_once()


@pytest.mark.asyncio
async def test_pre_start_free_food_accepted_as_feeding(mock_uow):
    goal = make_dummy_goal()
    periods = make_dummy_periods()

    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=periods)
    mock_uow.entries.has_active_feeding = AsyncMock(return_value=False)
    mock_uow.entries.list_by_goal = AsyncMock(return_value=[])
    mock_uow.users.get_by_id = AsyncMock(
        return_value=UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    )

    # Day 0 (before start_at)
    occurred_at = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    res = await feed_goal(mock_uow, user_id=1, goal_id=101, amount_cents=0, occurred_at=occurred_at)

    assert res.success is True
    assert res.is_free_food is True
    assert res.entry.is_feeding is True
    assert res.entry.kind == "free_food"
    assert res.entry.period_idx == 0


@pytest.mark.asyncio
async def test_pre_start_already_fed_subsequent_handling(mock_uow):
    goal = make_dummy_goal()
    periods = make_dummy_periods()

    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=periods)
    mock_uow.entries.has_active_feeding = AsyncMock(return_value=True)
    mock_uow.entries.list_by_goal = AsyncMock(return_value=[])
    mock_uow.users.get_by_id = AsyncMock(
        return_value=UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    )

    occurred_at = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

    # 1. Second deposit before start_at is extra
    res_deposit = await feed_goal(
        mock_uow, user_id=1, goal_id=101, amount_cents=1000, occurred_at=occurred_at
    )
    assert res_deposit.success is True
    assert res_deposit.is_extra is True
    assert res_deposit.entry.is_feeding is False

    # 2. Free food when already fed is rejected
    res_free = await feed_goal(
        mock_uow, user_id=1, goal_id=101, amount_cents=0, occurred_at=occurred_at
    )
    assert res_free.success is False
    assert res_free.error_code == "already_fed"


@pytest.mark.asyncio
async def test_open_period_first_feeding(mock_uow):
    goal = make_dummy_goal()
    periods = make_dummy_periods()

    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=periods)
    mock_uow.entries.has_active_feeding = AsyncMock(return_value=False)
    mock_uow.entries.list_by_goal = AsyncMock(return_value=[])
    mock_uow.users.get_by_id = AsyncMock(
        return_value=UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    )

    occurred_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    res = await feed_goal(
        mock_uow, user_id=1, goal_id=101, amount_cents=1000, occurred_at=occurred_at
    )

    assert res.success is True
    assert res.is_extra is False
    assert res.entry.is_feeding is True
    assert res.entry.kind == "deposit"
    assert res.entry.period_idx == 0


@pytest.mark.asyncio
async def test_open_period_free_food(mock_uow):
    goal = make_dummy_goal()
    periods = make_dummy_periods()

    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=periods)
    mock_uow.entries.has_active_feeding = AsyncMock(return_value=False)
    mock_uow.entries.list_by_goal = AsyncMock(return_value=[])
    mock_uow.users.get_by_id = AsyncMock(
        return_value=UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    )

    occurred_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    res = await feed_goal(mock_uow, user_id=1, goal_id=101, amount_cents=0, occurred_at=occurred_at)

    assert res.success is True
    assert res.is_free_food is True
    assert res.entry.is_feeding is True
    assert res.entry.kind == "free_food"
    assert res.entry.amount_cents == 0


@pytest.mark.asyncio
async def test_open_period_free_food_twice_rejected(mock_uow):
    goal = make_dummy_goal()
    periods = make_dummy_periods()

    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=periods)
    mock_uow.entries.has_active_feeding = AsyncMock(return_value=True)  # Already fed!

    occurred_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    res = await feed_goal(mock_uow, user_id=1, goal_id=101, amount_cents=0, occurred_at=occurred_at)

    assert res.success is False
    assert res.error_code == "already_fed"


@pytest.mark.asyncio
async def test_graduation_trigger(mock_uow):
    goal = make_dummy_goal(target_cents=5000)
    periods = make_dummy_periods()

    mock_uow.goals.lock_goal = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=periods)
    mock_uow.entries.has_active_feeding = AsyncMock(return_value=False)

    existing_entry = EntryTable(
        id=1,
        goal_id=101,
        period_idx=0,
        kind="deposit",
        amount_cents=5000,
        occurred_at=datetime(2026, 11, 10, 10, 0, tzinfo=UTC),
        is_feeding=True,
    )
    mock_uow.entries.list_by_goal = AsyncMock(return_value=[existing_entry])
    mock_uow.users.get_by_id = AsyncMock(
        return_value=UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    )

    occurred_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    res = await feed_goal(
        mock_uow, user_id=1, goal_id=101, amount_cents=5000, occurred_at=occurred_at
    )

    assert res.success is True
    assert res.is_graduated is True
    assert goal.status == "graduated"
    assert goal.result is not None
    assert goal.result["outcome"] == "graduated"
    assert goal.result["title"] == "Well cared for"
    mock_uow.notifications.cancel_pending_by_goal.assert_called_once_with(101)
