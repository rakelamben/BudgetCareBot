import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from budgetcare.db.tables import FeedingPeriodTable, GoalTable, NotificationTable, UserTable
from budgetcare.services.tick import TickStats, _send_due_notifications, close_goal_periods


@pytest.mark.asyncio
async def test_soak_simulated_high_volume_period_closing():
    """Soak Drill: Verify rapid closing and evaluation of 500 goal periods within time budget."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=5)
    t0 = time.monotonic()

    closed_total = 0
    missed_total = 0

    # Simulate 500 goals closing their due period
    for i in range(500):
        goal = GoalTable(
            id=i + 1,
            user_id=(i % 100) + 1,
            name=f"Goal {i + 1}",
            target_cents=100000,
            period_days=30,
            total_feedings=30,
            nominal_cents=3334,
            species="cat",
            pet_name=f"Pet {i + 1}",
            status="active",
            notifications_enabled=True,
        )

        mock_uow = AsyncMock()
        mock_uow.notifications.add_all = MagicMock()
        mock_uow.events.record = MagicMock()
        # Half of the periods were fed, half were missed
        period = FeedingPeriodTable(
            goal_id=goal.id,
            idx=0,
            start_date=cutoff.date() - timedelta(days=1),
            end_date=cutoff.date(),
            cutoff_at=cutoff,
            nominal_cents=3334,
            status="open",
        )
        mock_uow.periods.list_due_open.return_value = [period]
        mock_uow.periods.all_periods_closed.return_value = False
        mock_uow.entries.has_active_feeding.return_value = (i % 2 == 0)

        closed, missed, _outcome = await close_goal_periods(
            uow=mock_uow,
            goal=goal,
            now=now,
            grace_seconds=60,
        )
        closed_total += closed
        missed_total += missed

    duration = time.monotonic() - t0
    assert closed_total == 500
    assert missed_total == 250
    # 500 calculations should complete in well under 2 seconds
    assert duration < 2.0


@pytest.mark.asyncio
async def test_soak_simulated_digest_bundling_and_rate_limiting():
    """Soak Drill: Verify high-volume notification claiming, digest bundling for 100 users, and send throughput."""
    now = datetime.now(UTC)
    stats = TickStats()
    bot = AsyncMock()

    # 100 users, each having 3 pets due for notification = 300 notifications
    claimed_notifs: list[NotificationTable] = []
    goals_map: dict[int, GoalTable] = {}
    users_map: dict[int, UserTable] = {}

    for u_idx in range(1, 101):
        user = UserTable(
            id=u_idx,
            telegram_user_id=10000 + u_idx,
            chat_id=10000 + u_idx,
            timezone="Asia/Jakarta",
            variant="pet",
        )
        users_map[u_idx] = user

        for g_offset in range(3):
            g_id = u_idx * 10 + g_offset
            goal = GoalTable(
                id=g_id,
                user_id=u_idx,
                name=f"Goal {g_id}",
                target_cents=50000,
                period_days=14,
                total_feedings=14,
                nominal_cents=3571,
                species="dog",
                pet_name=f"Doggo {g_id}",
                status="active",
                notifications_enabled=True,
            )
            goals_map[g_id] = goal

            n_id = g_id * 100
            notif = NotificationTable(
                id=n_id,
                goal_id=g_id,
                period_idx=1,
                kind="reminder",
                due_at=now - timedelta(minutes=10),
                status="sending",
            )
            claimed_notifs.append(notif)

    t0 = time.monotonic()
    with patch("budgetcare.services.tick.uow_factory") as mock_uow_factory:
        mock_uow = AsyncMock()
        mock_uow_factory.return_value.__aenter__.return_value = mock_uow
        mock_uow.notifications.claim_due.return_value = claimed_notifs
        mock_uow.goals.get_by_id.side_effect = lambda gid: goals_map.get(gid)
        mock_uow.users.get_by_id.side_effect = lambda uid: users_map.get(uid)
        mock_uow.periods.get_period.return_value = MagicMock(status="open")
        mock_uow.entries.has_active_feeding.return_value = False

        await _send_due_notifications(
            bot=bot,
            now=now,
            deadline=time.monotonic() + 25.0,
            stats=stats,
        )

    duration = time.monotonic() - t0

    # 300 notifications across 100 users should be bundled into 100 digest messages!
    assert bot.send_message.call_count == 100
    assert stats.notifications_sent == 300
    assert stats.notifications_failed == 0
    # Throughput verification: should process and bundle 300 notifications rapidly
    assert duration < 5.0
