import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiolimiter import AsyncLimiter

from budgetcare.bot.copy import get_text
from budgetcare.bot.dispatcher import create_bot
from budgetcare.bot.keyboards import digest_notification_keyboard, single_notification_keyboard
from budgetcare.config import settings
from budgetcare.db.tables import GoalTable, NotificationTable
from budgetcare.db.uow import UnitOfWork, uow_factory
from budgetcare.domain.money import format_cents
from budgetcare.domain.pets import SPECIES_EMOJI
from budgetcare.domain.scoring import (
    calculate_condition,
    calculate_final_service_quality,
    calculate_mood_tier,
    calculate_surplus,
    get_result_title,
)
from budgetcare.domain.timeutil import get_user_tz
from budgetcare.logging import logger


class TelegramRateLimitStop(Exception):
    """Raised when Telegram returns 429 rate limit to halt current batch."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Telegram rate limited: retry after {retry_after}s")


@dataclass
class TickStats:
    skipped: str | None = None
    periods_closed: int = 0
    periods_missed: int = 0
    goals_graduated: int = 0
    goals_expired: int = 0
    notifications_claimed: int = 0
    notifications_sent: int = 0
    notifications_skipped: int = 0
    notifications_failed: int = 0
    rate_limited: bool = False
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)



async def close_goal_periods(
    uow: UnitOfWork,
    goal: GoalTable,
    now: datetime,
    grace_seconds: int = 60,
) -> tuple[int, int, str | None]:
    """Close due open periods for a single goal and finalize if all periods are closed.

    Returns (closed_count, missed_count, finalized_outcome).
    """
    cutoff = now - timedelta(seconds=grace_seconds)
    due_periods = await uow.periods.list_due_open(goal.id, cutoff)

    closed_count = 0
    missed_count = 0

    for p in due_periods:
        fed = await uow.entries.has_active_feeding(goal.id, p.idx)
        status = "fed" if fed else "missed"
        await uow.periods.close_period(goal.id, p.idx, status, now)
        closed_count += 1
        if not fed:
            missed_count += 1

    finalized_outcome: str | None = None
    all_closed = await uow.periods.all_periods_closed(goal.id)

    if all_closed:
        # Finalize goal (SDD 6.4 & 11.2)
        all_entries = await uow.entries.list_by_goal(goal.id)
        all_periods = await uow.periods.list_by_goal(goal.id)

        deposited = sum(e.amount_cents for e in all_entries if e.undone_at is None)
        total_missed = sum(1 for p in all_periods if p.status == "missed")
        free_food_count = sum(
            1 for e in all_entries if e.kind == "free_food" and e.undone_at is None
        )

        condition_pct = calculate_condition(total_missed, goal.total_feedings)
        mood_tier = calculate_mood_tier(total_missed, goal.total_feedings)
        final_quality = calculate_final_service_quality(deposited, goal.target_cents)
        final_quality_pct = round(final_quality * 100)
        surplus = calculate_surplus(deposited, goal.target_cents)

        if deposited >= goal.target_cents:
            finalized_outcome = "graduated"
            goal.status = "graduated"
            goal.graduated_at = now
            title = get_result_title("graduated", mood_tier)
        else:
            finalized_outcome = "expired"
            goal.status = "expired"
            title = get_result_title("expired", mood_tier)

        goal.closed_at = now
        goal.result = {
            "outcome": finalized_outcome,
            "final_condition_pct": condition_pct,
            "final_quality_pct": final_quality_pct,
            "mood_tier": mood_tier.value,
            "title": title,
            "days_taken": goal.period_days,
            "deposited_cents": deposited,
            "surplus_cents": surplus,
            "free_food_count": free_food_count,
            "closed_at": now.isoformat(),
        }

        # Cancel remaining notifications
        await uow.notifications.cancel_pending_by_goal(goal.id)

        # If expired with notifications on, enqueue result notification
        if goal.notifications_enabled and finalized_outcome == "expired":
            uow.notifications.add_all(
                [
                    NotificationTable(
                        goal_id=goal.id,
                        period_idx=goal.total_feedings - 1,
                        kind="result",
                        due_at=now,
                        status="pending",
                    )
                ]
            )

        # Audit event
        uow.events.record(
            name=f"goal_{finalized_outcome}",
            user_id=goal.user_id,
            goal_id=goal.id,
            props={
                "outcome": finalized_outcome,
                "deposited_cents": deposited,
                "final_condition_pct": condition_pct,
                "final_quality_pct": final_quality_pct,
            },
        )

    return closed_count, missed_count, finalized_outcome


async def run_tick(
    now: datetime | None = None,
    bot: Bot | None = None,
) -> TickStats:
    """Execute the full tick routine: acquire lease, close periods, send notifications."""
    t_start = time.monotonic()
    now_dt = now or datetime.now(UTC)
    stats = TickStats()
    deadline = t_start + settings.TICK_TIME_BUDGET_SECONDS

    # 1. Acquire Lease Lock
    async with uow_factory() as uow:
        acquired = await uow.locks.acquire_lease(
            name="tick",
            ttl_seconds=settings.TICK_LEASE_SECONDS,
            locked_by=f"worker-{int(time.time())}",
        )
        if not acquired:
            stats.skipped = "locked"
            return stats

        run_id = await uow.tick_runs.start_run()
        await uow.commit()

    run_error: str | None = None

    try:
        # 2. Reclaim stale sending claims
        async with uow_factory() as uow:
            stale_cutoff = now_dt - timedelta(minutes=settings.STALE_CLAIM_MINUTES)
            failed, _requeued = await uow.notifications.reclaim_stale_sending(
                cutoff=stale_cutoff,
                max_attempts=settings.MAX_NOTIFICATION_ATTEMPTS,
            )
            stats.notifications_failed += failed
            await uow.commit()

        # 3. Part A: Close periods for goals with due cut-offs
        async with uow_factory() as uow:
            grace_cutoff = now_dt - timedelta(seconds=settings.CUTOFF_GRACE_SECONDS)
            due_goal_ids = await uow.periods.find_goal_ids_with_due_periods(
                cutoff_threshold=grace_cutoff,
                limit=500,
            )

        for g_id in due_goal_ids:
            if time.monotonic() > deadline:
                break
            async with uow_factory() as goal_uow:
                goal = await goal_uow.goals.lock_skip_locked(g_id)
                if not goal or goal.status != "active":
                    continue
                closed, missed, outcome = await close_goal_periods(
                    uow=goal_uow,
                    goal=goal,
                    now=now_dt,
                    grace_seconds=settings.CUTOFF_GRACE_SECONDS,
                )
                stats.periods_closed += closed
                stats.periods_missed += missed
                if outcome == "graduated":
                    stats.goals_graduated += 1
                elif outcome == "expired":
                    stats.goals_expired += 1
                await goal_uow.commit()

        # 4. Part B: Send due notifications
        bot_instance = bot or create_bot()
        try:
            await _send_due_notifications(
                bot=bot_instance,
                now=now_dt,
                deadline=deadline,
                stats=stats,
            )
        finally:
            if bot is None:
                await bot_instance.session.close()

    except Exception as exc:  # noqa: BLE001
        run_error = repr(exc)
        stats.error = run_error
        logger.exception("tick_failed", error=run_error)

    finally:
        # Finish run and release lease
        stats.duration_ms = round((time.monotonic() - t_start) * 1000, 2)
        async with uow_factory() as uow:
            await uow.tick_runs.finish_run(
                run_id=run_id,
                stats=stats.to_dict(),
                error=run_error,
            )
            await uow.locks.release_lease("tick")
            await uow.commit()

    return stats


async def _send_due_notifications(
    bot: Bot,
    now: datetime,
    deadline: float,
    stats: TickStats,
) -> None:
    """Claim and send due notifications with relevance checks and batching."""
    limiter = AsyncLimiter(settings.SEND_RATE_PER_SECOND, 1.0)
    stale_hours_cutoff = now - timedelta(hours=settings.STALE_NOTIFICATION_HOURS)

    # 1. Claim batch
    async with uow_factory() as uow:
        claimed_notifs = await uow.notifications.claim_due(
            limit=settings.SEND_BATCH_SIZE,
            now=now,
        )
        stats.notifications_claimed += len(claimed_notifs)
        await uow.commit()

    if not claimed_notifs:
        return

    # 2. Filter relevance
    relevant_notifs: list[tuple[NotificationTable, GoalTable, Any]] = []

    for n in claimed_notifs:
        async with uow_factory() as uow:
            goal = await uow.goals.get_by_id(n.goal_id)
            if not goal:
                await uow.notifications.mark_skipped(n.id)
                stats.notifications_skipped += 1
                await uow.commit()
                continue

            user = await uow.users.get_by_id(goal.user_id)
            if not user or user.blocked_at is not None:
                await uow.notifications.mark_skipped(n.id)
                stats.notifications_skipped += 1
                await uow.commit()
                continue

            # Result notifications bypass active/open checks
            if n.kind == "result":
                relevant_notifs.append((n, goal, user))
                continue

            # Check staleness (> 3 hours old)
            if n.due_at < stale_hours_cutoff:
                await uow.notifications.mark_skipped(n.id)
                stats.notifications_skipped += 1
                await uow.commit()
                continue

            # Check goal active and notifications enabled
            if goal.status != "active" or not goal.notifications_enabled:
                await uow.notifications.mark_skipped(n.id)
                stats.notifications_skipped += 1
                await uow.commit()
                continue

            # Check period still open and not fed
            period = await uow.periods.get_period(goal.id, n.period_idx)
            if not period or period.status != "open":
                await uow.notifications.mark_skipped(n.id)
                stats.notifications_skipped += 1
                await uow.commit()
                continue

            already_fed = await uow.entries.has_active_feeding(goal.id, n.period_idx)
            if already_fed:
                await uow.notifications.mark_skipped(n.id)
                stats.notifications_skipped += 1
                await uow.commit()
                continue

            relevant_notifs.append((n, goal, user))

    # 3. Group by user into digests or single reminders
    user_groups: dict[int, list[tuple[NotificationTable, GoalTable, Any]]] = {}
    for n, goal, user in relevant_notifs:
        user_groups.setdefault(user.id, []).append((n, goal, user))

    try:
        for user_id, items in user_groups.items():
            if time.monotonic() > deadline:
                break

            first_user = items[0][2]
            chat_id = first_user.chat_id
            variant = first_user.variant or "pet"
            tz = get_user_tz(first_user.timezone)

            # Check for result notifications (sent individually)
            result_items = [item for item in items if item[0].kind == "result"]
            hunger_items = [item for item in items if item[0].kind != "result"]

            # Send individual result notifications
            for n, goal, _ in result_items:
                res_data = goal.result or {}
                text = get_text(
                    "notif_result_expired",
                    variant,
                    name=goal.name,
                    pet_name=goal.pet_name,
                    pet_emoji=SPECIES_EMOJI.get(goal.species.lower(), "🐾"),
                    final_condition=res_data.get("final_condition_pct", 100),
                    final_quality=res_data.get("final_quality_pct", 0),
                    deposited=format_cents(res_data.get("deposited_cents", 0)),
                    target=format_cents(goal.target_cents),
                    title=res_data.get("title", "Ended"),
                )
                success = await _send_message_safe(bot, chat_id, text, None, limiter, user_id)
                async with uow_factory() as uow:
                    if success:
                        await uow.notifications.mark_sent(n.id, datetime.now(UTC))
                        stats.notifications_sent += 1
                    else:
                        await uow.notifications.mark_failed(n.id, "Delivery failed")
                        stats.notifications_failed += 1
                    await uow.commit()

            # Send hunger notifications (digest or single)
            if not hunger_items:
                continue

            if len(hunger_items) == 1:
                n, goal, _ = hunger_items[0]
                cutoff_str = (
                    n.due_at.astimezone(tz).strftime("%a, %d %b %H:%M")
                    if n.due_at
                    else "tomorrow 23:59"
                )
                key_map = {
                    "reminder": "notif_reminder_single",
                    "followup": "notif_followup_single",
                    "early_warning": "notif_early_warning_single",
                }
                copy_key = key_map.get(n.kind, "notif_reminder_single")
                text = get_text(
                    copy_key,
                    variant,
                    name=goal.name,
                    pet_name=goal.pet_name,
                    cutoff=cutoff_str,
                    nominal=format_cents(goal.nominal_cents),
                )
                kb = single_notification_keyboard(goal.id, goal.pet_name)
                success = await _send_message_safe(bot, chat_id, text, kb, limiter, user_id)
                async with uow_factory() as uow:
                    if success:
                        await uow.notifications.mark_sent(n.id, datetime.now(UTC))
                        stats.notifications_sent += 1
                    else:
                        await uow.notifications.mark_failed(n.id, "Delivery failed")
                        stats.notifications_failed += 1
                    await uow.commit()
            else:
                # Digest message
                count = len(hunger_items)
                lines = [
                    get_text("digest_title", variant, count=count, s="s" if count > 1 else "", verb="are")
                ]
                kb_items: list[tuple[int, str]] = []

                for n, goal, _ in hunger_items[:8]:
                    cutoff_str = n.due_at.astimezone(tz).strftime("%a %H:%M")
                    lines.append(
                        get_text(
                            "digest_item",
                            variant,
                            pet_emoji=SPECIES_EMOJI.get(goal.species.lower(), "🐾"),
                            pet_name=goal.pet_name,
                            name=goal.name,
                            cutoff=cutoff_str,
                            nominal=format_cents(goal.nominal_cents),
                        )
                    )
                    kb_items.append((goal.id, goal.pet_name))

                if count > 8:
                    lines.append(f"\n<i>...and {count - 8} more pets. Use /goals to view all!</i>")

                digest_text = "\n".join(lines)
                kb = digest_notification_keyboard(kb_items)
                success = await _send_message_safe(bot, chat_id, digest_text, kb, limiter, user_id)

                async with uow_factory() as uow:
                    for n, _, _ in hunger_items:
                        if success:
                            await uow.notifications.mark_sent(n.id, datetime.now(UTC))
                            stats.notifications_sent += 1
                        else:
                            await uow.notifications.mark_failed(n.id, "Delivery failed")
                            stats.notifications_failed += 1
                    await uow.commit()
    except TelegramRateLimitStop as exc:
        logger.warning("batch_stopped_by_telegram_rate_limit", retry_after=exc.retry_after)
        stats.rate_limited = True


async def _send_message_safe(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Any,
    limiter: AsyncLimiter,
    user_id: int,
) -> bool:
    """Send message respecting rate limits and handling blocked user errors."""
    await limiter.acquire()
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        return True
    except TelegramForbiddenError:
        # User blocked the bot (HTTP 403)
        logger.warning("user_blocked_bot", user_id=user_id, chat_id=chat_id)
        async with uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user:
                user.blocked_at = datetime.now(UTC)
                active_goals = await uow.goals.list_active_by_user(user_id)
                for g in active_goals:
                    await uow.notifications.cancel_pending_by_goal(g.id)
                uow.events.record(name="bot_blocked", user_id=user_id, props={})
                await uow.commit()
        return False
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower() or "user is deactivated" in str(e).lower():
            logger.warning("chat_not_found", user_id=user_id, error=str(e))
            async with uow_factory() as uow:
                user = await uow.users.get_by_id(user_id)
                if user:
                    user.blocked_at = datetime.now(UTC)
                    active_goals = await uow.goals.list_active_by_user(user_id)
                    for g in active_goals:
                        await uow.notifications.cancel_pending_by_goal(g.id)
                    await uow.commit()
            return False
        logger.error("telegram_bad_request", error=str(e))
        return False
    except TelegramRetryAfter as e:
        logger.warning("telegram_rate_limited", retry_after=e.retry_after)
        raise TelegramRateLimitStop(e.retry_after) from e
    except Exception as e:  # noqa: BLE001
        logger.error("message_send_failed", error=str(e))
        return False

