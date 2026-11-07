from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage

from budgetcare.db.tables import GoalTable, NotificationTable, UserTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.services.tick import (
    TickStats,
    _send_due_notifications,
    _send_message_safe,
    run_tick,
)


@pytest.mark.asyncio
async def test_drill_a_reclaim_stale_sending_on_tick_crash():
    """Drill A: Kill the tick mid-send. Reclaim stale 'sending' claims on subsequent tick."""
    session = AsyncMock()
    uow = UnitOfWork(session)

    # Mock execute returning row counts for fail and requeue statements
    mock_fail_res = MagicMock(rowcount=1)
    mock_requeue_res = MagicMock(rowcount=3)
    session.execute.side_effect = [mock_fail_res, mock_requeue_res]

    cutoff = datetime.now(UTC) - timedelta(minutes=5)
    failed, requeued = await uow.notifications.reclaim_stale_sending(
        cutoff=cutoff,
        max_attempts=3,
    )

    assert failed == 1
    assert requeued == 3
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_drill_b_telegram_429_rate_limit_stops_batch():
    """Drill B: Telegram 429 halts the notification batch and sets rate_limited flag."""
    bot = AsyncMock()
    retry_exc = TelegramRetryAfter(
        method=SendMessage(chat_id=123, text="test"),
        message="Too many requests",
        retry_after=15,
    )
    bot.send_message.side_effect = retry_exc

    stats = TickStats()
    now = datetime.now(UTC)

    # Mock notifications, goal, and user
    user = UserTable(id=1, telegram_user_id=12345, chat_id=12345, timezone="Asia/Jakarta", variant="pet")
    goal = GoalTable(
        id=10,
        user_id=1,
        name="Emergency",
        target_cents=100000,
        period_days=30,
        total_feedings=30,
        nominal_cents=3334,
        species="cat",
        pet_name="Whiskers",
        status="active",
        notifications_enabled=True,
    )
    notif = NotificationTable(
        id=101,
        goal_id=10,
        period_idx=1,
        kind="reminder",
        due_at=now,
        status="sending",
    )

    with patch("budgetcare.services.tick.uow_factory") as mock_uow_factory:
        mock_uow = AsyncMock()
        mock_uow_factory.return_value.__aenter__.return_value = mock_uow
        mock_uow.notifications.claim_due.return_value = [notif]
        mock_uow.goals.get_by_id.return_value = goal
        mock_uow.users.get_by_id.return_value = user
        mock_uow.periods.get_period.return_value = MagicMock(status="open")
        mock_uow.entries.has_active_feeding.return_value = False

        await _send_due_notifications(
            bot=bot,
            now=now,
            deadline=float("inf"),
            stats=stats,
        )

    assert stats.rate_limited is True
    assert stats.notifications_sent == 0


@pytest.mark.asyncio
async def test_drill_c_telegram_403_user_blocked_bot():
    """Drill C: Telegram 403 marks user blocked_at, cancels pending notifications, records event."""
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramForbiddenError(
        method=SendMessage(chat_id=123, text="test"),
        message="Forbidden: bot was blocked by the user",
    )

    limiter = AsyncMock()
    user = UserTable(id=2, telegram_user_id=999, chat_id=999, timezone="Asia/Jakarta", blocked_at=None)
    goal = GoalTable(id=20, user_id=2, name="Travel", target_cents=50000, status="active")

    with patch("budgetcare.services.tick.uow_factory") as mock_uow_factory:
        mock_uow = AsyncMock()
        mock_uow.events.record = MagicMock()
        mock_uow_factory.return_value.__aenter__.return_value = mock_uow
        mock_uow.users.get_by_id.return_value = user
        mock_uow.goals.list_active_by_user.return_value = [goal]

        success = await _send_message_safe(
            bot=bot,
            chat_id=999,
            text="Hello",
            reply_markup=None,
            limiter=limiter,
            user_id=2,
        )

        assert success is False
        assert user.blocked_at is not None
        mock_uow.notifications.cancel_pending_by_goal.assert_awaited_once_with(20)
        mock_uow.events.record.assert_called_once_with(name="bot_blocked", user_id=2, props={})


@pytest.mark.asyncio
async def test_drill_e_tick_lease_lock_prevents_concurrent_runs():
    """Drill E: When lease is active, concurrent tick gracefully skips."""
    with patch("budgetcare.services.tick.uow_factory") as mock_uow_factory:
        mock_uow = AsyncMock()
        mock_uow_factory.return_value.__aenter__.return_value = mock_uow
        mock_uow.locks.acquire_lease.return_value = False

        stats = await run_tick(now=datetime.now(UTC), bot=AsyncMock())
        assert stats.skipped == "locked"
