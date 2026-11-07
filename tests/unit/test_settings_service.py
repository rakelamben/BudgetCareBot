from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from budgetcare.db.tables import FeedingPeriodTable, GoalTable, UserTable
from budgetcare.services.settings import (
    change_user_timezone,
    delete_single_goal,
    toggle_goal_notifications,
    update_goal_reminder_time,
    wipe_all_user_data,
)


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

    uow.commit = AsyncMock()
    uow.session.flush = AsyncMock()
    uow.session.delete = AsyncMock()
    uow.notifications.delete_pending_by_goal = AsyncMock()
    uow.events.record = MagicMock()

    return uow


def make_test_goal(goal_id: int = 201) -> GoalTable:
    return GoalTable(
        id=goal_id,
        user_id=1,
        name="Macbook M6",
        target_cents=20000,
        period_days=10,
        frequency="weekly",
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 20),
        start_at=datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
        total_feedings=2,
        nominal_cents=10000,
        last_nominal_cents=10000,
        species="hamster",
        pet_name="Pipo",
        notifications_enabled=True,
        reminder_weekday=5,
        status="active",
        created_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_timezone_change_recomputes_cutoffs_and_replanned(mock_uow):
    user = UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    goal = make_test_goal()
    p0 = FeedingPeriodTable(
        goal_id=goal.id,
        idx=0,
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 15),
        cutoff_at=datetime(2026, 11, 15, 16, 59, tzinfo=UTC),
        status="open",
    )

    mock_uow.users.get_by_id = AsyncMock(return_value=user)
    mock_uow.goals.list_active_by_user = AsyncMock(return_value=[goal])
    mock_uow.periods.list_by_goal = AsyncMock(return_value=[p0])
    mock_uow.notifications.add_all = MagicMock()

    now = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
    await change_user_timezone(mock_uow, user_id=1, new_tz_str="America/New_York", now=now)

    assert user.timezone == "America/New_York"
    # Verification of recomputed cutoff (America/New_York midnight is UTC+5)
    assert p0.cutoff_at.tzinfo is not None
    mock_uow.notifications.delete_pending_by_goal.assert_called_once_with(goal.id)
    mock_uow.notifications.add_all.assert_called_once()
    mock_uow.events.record.assert_called_once_with(
        name="timezone_set",
        user_id=1,
        props={"timezone": "America/New_York"},
    )


@pytest.mark.asyncio
async def test_toggle_goal_notifications_on_and_off(mock_uow):
    user = UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    goal = make_test_goal()
    p0 = FeedingPeriodTable(
        goal_id=goal.id,
        idx=0,
        status="open",
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 15),
        cutoff_at=datetime.now(UTC),
        nominal_cents=1000,
    )

    mock_uow.users.get_by_id = AsyncMock(return_value=user)
    mock_uow.goals.get_by_id = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=[p0])
    mock_uow.notifications.add_all = MagicMock()

    # 1. Turn off
    await toggle_goal_notifications(mock_uow, goal.id, enabled=False)
    assert goal.notifications_enabled is False
    mock_uow.notifications.delete_pending_by_goal.assert_called_with(goal.id)

    # 2. Turn on
    await toggle_goal_notifications(mock_uow, goal.id, enabled=True)
    assert goal.notifications_enabled is True
    mock_uow.notifications.add_all.assert_called()


@pytest.mark.asyncio
async def test_update_goal_reminder_time(mock_uow):
    user = UserTable(id=1, telegram_user_id=123, chat_id=123, timezone="Asia/Jakarta")
    goal = make_test_goal()
    p0 = FeedingPeriodTable(
        goal_id=goal.id,
        idx=0,
        status="open",
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 15),
        cutoff_at=datetime.now(UTC),
        nominal_cents=1000,
    )

    mock_uow.users.get_by_id = AsyncMock(return_value=user)
    mock_uow.goals.get_by_id = AsyncMock(return_value=goal)
    mock_uow.periods.list_by_goal = AsyncMock(return_value=[p0])
    mock_uow.notifications.add_all = MagicMock()

    await update_goal_reminder_time(mock_uow, goal.id, reminder_weekday=2)
    assert goal.reminder_weekday == 2
    mock_uow.notifications.delete_pending_by_goal.assert_called_with(goal.id)
    mock_uow.notifications.add_all.assert_called()


@pytest.mark.asyncio
async def test_delete_single_goal(mock_uow):
    goal = make_test_goal()
    mock_uow.goals.get_by_id = AsyncMock(return_value=goal)
    mock_uow.goals.delete_goal = AsyncMock()

    res = await delete_single_goal(mock_uow, user_id=1, goal_id=goal.id)
    assert res is True
    mock_uow.goals.delete_goal.assert_called_once_with(goal.id)
    mock_uow.events.record.assert_called_once_with(
        name="goal_deleted",
        user_id=1,
        goal_id=None,
        props={},
    )


@pytest.mark.asyncio
async def test_wipe_all_user_data(mock_uow):
    user = UserTable(id=1, telegram_user_id=123, chat_id=123)
    mock_uow.users.get_by_id = AsyncMock(return_value=user)

    res = await wipe_all_user_data(mock_uow, user_id=1)
    assert res is True
    mock_uow.session.delete.assert_called_once_with(user)
