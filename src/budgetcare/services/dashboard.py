from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import (
    EntryTable,
    EventTable,
    FeedingPeriodTable,
    GoalTable,
    JobLockTable,
    NotificationTable,
    TickRunTable,
    UserTable,
)
from budgetcare.domain.money import format_cents
from budgetcare.domain.pets import SPECIES_EMOJI
from budgetcare.domain.scoring import calculate_condition, calculate_mood_tier


async def get_dashboard_summary(session: AsyncSession) -> dict[str, Any]:
    """Compile comprehensive dashboard analytics and operational metrics."""
    now = datetime.now(UTC)

    # -------------------------------------------------------------------------
    # 1. Overview KPIs
    # -------------------------------------------------------------------------
    # Users summary
    users_stmt = select(
        func.count(UserTable.id).label("total"),
        func.count().filter(UserTable.blocked_at.is_(None)).label("active"),
        func.count().filter(UserTable.blocked_at.is_not(None)).label("blocked"),
    )
    users_res = (await session.execute(users_stmt)).one()
    total_users = users_res.total or 0
    active_users = users_res.active or 0
    blocked_users = users_res.blocked or 0

    # Goals summary
    goals_stmt = select(
        func.count(GoalTable.id).label("total"),
        func.count().filter(GoalTable.status == "active").label("active"),
        func.count().filter(GoalTable.status == "graduated").label("graduated"),
        func.count().filter(GoalTable.status == "closed").label("closed"),
        func.coalesce(func.sum(GoalTable.target_cents).filter(GoalTable.status == "active"), 0).label("active_target_cents"),
    )
    goals_res = (await session.execute(goals_stmt)).one()
    total_goals = goals_res.total or 0
    active_goals_count = goals_res.active or 0
    graduated_goals_count = goals_res.graduated or 0
    closed_goals_count = goals_res.closed or 0
    active_target_cents = goals_res.active_target_cents or 0

    # Deposits & Entries summary
    entries_stmt = select(
        func.coalesce(func.sum(EntryTable.amount_cents).filter(EntryTable.undone_at.is_(None)), 0).label("total_saved"),
        func.count().filter(EntryTable.kind == "deposit", EntryTable.undone_at.is_(None)).label("deposits_count"),
        func.count().filter(EntryTable.kind == "free_food", EntryTable.undone_at.is_(None)).label("free_food_count"),
    )
    entries_res = (await session.execute(entries_stmt)).one()
    total_saved_cents = entries_res.total_saved or 0
    deposits_count = entries_res.deposits_count or 0
    free_food_count = entries_res.free_food_count or 0

    total_feed_events = deposits_count + free_food_count
    free_food_ratio = round((free_food_count * 100.0) / total_feed_events, 1) if total_feed_events > 0 else 0.0

    # Habit Metric: On-time Feeding Rate
    periods_stmt = select(
        func.count().filter(FeedingPeriodTable.status == "fed").label("fed"),
        func.count().filter(FeedingPeriodTable.status == "missed").label("missed"),
        func.count().filter(FeedingPeriodTable.status == "open").label("open"),
    )
    periods_res = (await session.execute(periods_stmt)).one()
    fed_periods = periods_res.fed or 0
    missed_periods = periods_res.missed or 0
    evaluated_periods = fed_periods + missed_periods
    on_time_rate = round((fed_periods * 100.0) / evaluated_periods, 1) if evaluated_periods > 0 else 100.0

    # Mood Distribution across active goals
    active_goals_stmt = (
        select(GoalTable)
        .where(GoalTable.status == "active")
        .order_by(GoalTable.created_at.desc())
    )
    active_goals = (await session.execute(active_goals_stmt)).scalars().all()

    mood_counts = {4: 0, 3: 0, 2: 0, 1: 0}
    recent_goals_data: list[dict[str, Any]] = []

    # Cache periods and entries for active goals
    if active_goals:
        goal_ids = [g.id for g in active_goals]

        periods_by_goal_stmt = select(FeedingPeriodTable).where(FeedingPeriodTable.goal_id.in_(goal_ids))
        all_periods = (await session.execute(periods_by_goal_stmt)).scalars().all()
        periods_map: dict[int, list[FeedingPeriodTable]] = {}
        for p in all_periods:
            periods_map.setdefault(p.goal_id, []).append(p)

        entries_by_goal_stmt = select(EntryTable).where(
            EntryTable.goal_id.in_(goal_ids),
            EntryTable.undone_at.is_(None),
        )
        all_entries = (await session.execute(entries_by_goal_stmt)).scalars().all()
        entries_map: dict[int, list[EntryTable]] = {}
        for e in all_entries:
            entries_map.setdefault(e.goal_id, []).append(e)

        for g in active_goals:
            g_periods = periods_map.get(g.id, [])
            g_entries = entries_map.get(g.id, [])

            missed_count = sum(1 for p in g_periods if p.status == "missed")
            condition = calculate_condition(missed_count, g.total_feedings)
            tier = calculate_mood_tier(missed_count, g.total_feedings).value
            mood_counts[tier] = mood_counts.get(tier, 0) + 1

            g_deposited = sum(e.amount_cents for e in g_entries)
            progress_pct = min(100, (g_deposited * 100) // g.target_cents) if g.target_cents > 0 else 100

            # Only append the most recent 15 goals for feed view
            if len(recent_goals_data) < 15:
                pet_emoji = SPECIES_EMOJI.get(g.species.lower(), "🐾")
                recent_goals_data.append(
                    {
                        "id": g.id,
                        "user_id": g.user_id,
                        "name": g.name,
                        "pet_name": g.pet_name,
                        "species": g.species,
                        "pet_emoji": pet_emoji,
                        "frequency": g.frequency,
                        "target_formatted": format_cents(g.target_cents),
                        "deposited_formatted": format_cents(g_deposited),
                        "progress_pct": progress_pct,
                        "condition_pct": condition,
                        "mood_tier": tier,
                        "created_at": g.created_at.strftime("%Y-%m-%d %H:%M") if g.created_at else "-",
                    }
                )

    # -------------------------------------------------------------------------
    # 2. DevOps & System Reliability
    # -------------------------------------------------------------------------
    # Tick runs history
    tick_runs_stmt = (
        select(TickRunTable)
        .order_by(TickRunTable.started_at.desc())
        .limit(10)
    )
    tick_runs = (await session.execute(tick_runs_stmt)).scalars().all()

    last_tick_data = None
    is_cron_healthy = False
    seconds_since_last_tick = None

    if tick_runs:
        latest = tick_runs[0]
        stats = latest.stats or {}
        duration_ms = stats.get("duration_ms")
        if duration_ms is None and latest.finished_at:
            duration_ms = round((latest.finished_at - latest.started_at).total_seconds() * 1000, 1)

        diff_seconds = (now - latest.started_at).total_seconds()
        seconds_since_last_tick = max(0, int(diff_seconds))
        # Cron is scheduled once per minute. Healthy if executed within the last 180 seconds (3 min)
        is_cron_healthy = diff_seconds <= 180

        last_tick_data = {
            "id": latest.id,
            "started_at": latest.started_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "duration_ms": duration_ms or 0,
            "error": latest.error,
            "stats": stats,
            "is_healthy": is_cron_healthy,
            "seconds_ago": seconds_since_last_tick,
        }

    recent_ticks_data = []
    for tr in tick_runs:
        tr_stats = tr.stats or {}
        dur = tr_stats.get("duration_ms")
        if dur is None and tr.finished_at:
            dur = round((tr.finished_at - tr.started_at).total_seconds() * 1000, 1)
        recent_ticks_data.append(
            {
                "id": tr.id,
                "started_at": tr.started_at.strftime("%H:%M:%S"),
                "duration_ms": dur or 0,
                "error": tr.error,
                "periods_closed": tr_stats.get("periods_closed", 0),
                "periods_missed": tr_stats.get("periods_missed", 0),
                "goals_graduated": tr_stats.get("goals_graduated", 0),
                "notifications_sent": tr_stats.get("notifications_sent", 0),
            }
        )

    # Outbox notifications queue
    notif_stmt = select(
        func.count().filter(NotificationTable.status == "pending").label("pending"),
        func.count().filter(NotificationTable.status == "sending").label("sending"),
        func.count().filter(NotificationTable.status == "sent").label("sent"),
        func.count().filter(NotificationTable.status == "failed").label("failed"),
        func.count().filter(NotificationTable.status == "cancelled").label("cancelled"),
        func.count().filter(
            NotificationTable.status == "sending",
            NotificationTable.claimed_at < now - timedelta(minutes=5),
        ).label("stale_claims"),
    )
    notif_res = (await session.execute(notif_stmt)).one()
    outbox_data = {
        "pending": notif_res.pending or 0,
        "sending": notif_res.sending or 0,
        "sent": notif_res.sent or 0,
        "failed": notif_res.failed or 0,
        "cancelled": notif_res.cancelled or 0,
        "stale_claims": notif_res.stale_claims or 0,
    }

    # Job locks
    locks_stmt = select(JobLockTable).order_by(JobLockTable.locked_at.desc())
    locks = (await session.execute(locks_stmt)).scalars().all()
    locks_data = [
        {
            "name": l.name,
            "locked_by": l.locked_by,
            "locked_at": l.locked_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "expires_at": l.expires_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "is_expired": l.expires_at < now,
        }
        for l in locks
    ]

    # -------------------------------------------------------------------------
    # 3. Product & A/B Experiment Analytics
    # -------------------------------------------------------------------------
    # A/B Variant Comparison (pet vs plain)
    variants_stmt = (
        select(
            UserTable.variant,
            func.count(UserTable.id).label("total_users"),
            func.count(GoalTable.id).label("total_goals"),
            func.count().filter(GoalTable.status == "graduated").label("graduated_goals"),
        )
        .outerjoin(GoalTable, GoalTable.user_id == UserTable.id)
        .group_by(UserTable.variant)
    )
    variants_res = (await session.execute(variants_stmt)).all()

    variants_data = {}
    for row in variants_res:
        v_name = row.variant or "unknown"
        v_users = row.total_users or 0
        v_goals = row.total_goals or 0
        v_grad = row.graduated_goals or 0
        v_grad_rate = round((v_grad * 100.0) / v_goals, 1) if v_goals > 0 else 0.0
        variants_data[v_name] = {
            "total_users": v_users,
            "total_goals": v_goals,
            "graduated_goals": v_grad,
            "grad_rate": v_grad_rate,
        }

    # Day-7 and Day-21 Retention
    # Users who triggered any event >= 7 or 21 days after user.created_at
    d7_threshold = timedelta(days=7)
    d21_threshold = timedelta(days=21)

    retention_stmt = select(
        func.count(
            func.distinct(
                func.case((EventTable.created_at >= UserTable.created_at + d7_threshold, UserTable.id))
            )
        ).label("retained_d7"),
        func.count(
            func.distinct(
                func.case((EventTable.created_at >= UserTable.created_at + d21_threshold, UserTable.id))
            )
        ).label("retained_d21"),
    ).outerjoin(EventTable, EventTable.user_id == UserTable.id)

    retention_res = (await session.execute(retention_stmt)).one()
    retained_d7 = retention_res.retained_d7 or 0
    retained_d21 = retention_res.retained_d21 or 0
    retention_d7_rate = round((retained_d7 * 100.0) / total_users, 1) if total_users > 0 else 0.0
    retention_d21_rate = round((retained_d21 * 100.0) / total_users, 1) if total_users > 0 else 0.0

    return {
        "meta": {
            "server_time": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "status": "online",
        },
        "overview": {
            "total_users": total_users,
            "active_users": active_users,
            "blocked_users": blocked_users,
            "total_goals": total_goals,
            "active_goals": active_goals_count,
            "graduated_goals": graduated_goals_count,
            "closed_goals": closed_goals_count,
            "total_saved_formatted": format_cents(total_saved_cents),
            "total_saved_cents": total_saved_cents,
            "active_target_formatted": format_cents(active_target_cents),
            "on_time_feeding_rate": on_time_rate,
            "fed_periods": fed_periods,
            "missed_periods": missed_periods,
            "free_food_ratio": free_food_ratio,
            "mood_counts": mood_counts,
        },
        "devops": {
            "is_cron_healthy": is_cron_healthy,
            "seconds_since_last_tick": seconds_since_last_tick,
            "last_tick": last_tick_data,
            "recent_ticks": recent_ticks_data,
            "outbox": outbox_data,
            "locks": locks_data,
        },
        "analytics": {
            "variants": variants_data,
            "retention_d7_rate": retention_d7_rate,
            "retention_d21_rate": retention_d21_rate,
            "retained_d7": retained_d7,
            "retained_d21": retained_d21,
            "deposits_count": deposits_count,
            "free_food_count": free_food_count,
        },
        "recent_goals": recent_goals_data,
    }
