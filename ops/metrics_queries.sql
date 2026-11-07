-- =============================================================================
-- Budget Care v1 — Analytics & Operations SQL Queries (SDD Section 14)
-- Target Schema: budget_care
-- =============================================================================

-- 1. On-Time Feeding Rate (Primary Habit Metric)
-- Definition: Proportion of closed feeding periods that were fed on time vs missed.
select 
    count(*) filter (where status = 'fed')::numeric / nullif(count(*), 0) as on_time_rate,
    count(*) filter (where status = 'fed') as total_fed,
    count(*) filter (where status = 'missed') as total_missed,
    count(*) as total_evaluated_periods
from budget_care.feeding_periods
where status in ('fed', 'missed');


-- 2. User Retention: Day-7 and Day-21 Retention
-- Definition: Users who logged activity (events) 7+ or 21+ days after their first /start.
select
    count(distinct case when e.created_at >= u.created_at + interval '7 days' then u.id end)::numeric / 
        nullif(count(distinct u.id), 0) as retention_d7,
    count(distinct case when e.created_at >= u.created_at + interval '21 days' then u.id end)::numeric / 
        nullif(count(distinct u.id), 0) as retention_d21,
    count(distinct u.id) as total_users
from budget_care.users u
left join budget_care.events e on e.user_id = u.id;


-- 3. Free-Food Usage Rate
-- Definition: Ratio of free food actions to total feedings.
select
    count(*) filter (where name = 'free_food_used')::numeric /
        nullif(count(*) filter (where name = 'feeding_logged'), 0) as free_food_ratio,
    count(*) filter (where name = 'free_food_used') as total_free_food,
    count(*) filter (where name = 'feeding_logged') as total_feedings_logged
from budget_care.events;


-- 4. Bot Block Rate
-- Definition: Percentage of onboarded users who blocked the bot.
select
    count(*) filter (where name = 'bot_blocked')::numeric /
        nullif(count(*) filter (where name = 'user_started'), 0) as bot_block_rate,
    count(*) filter (where name = 'bot_blocked') as total_blocked,
    count(*) filter (where name = 'user_started') as total_started
from budget_care.events;


-- 5. Acted-On Notification Rate (< 2 hours after delivery)
-- Definition: Reminders that led to a deposit or feeding within 2 hours.
select
    count(distinct e.id)::numeric / nullif(count(distinct n.id), 0) as notification_acted_rate,
    count(distinct n.id) as total_sent_notifications,
    count(distinct e.id) as total_conversions_under_2h
from budget_care.notifications n
join budget_care.events e on e.user_id = n.user_id
    and e.name in ('feeding_logged', 'extra_deposit', 'free_food_used')
    and e.created_at between n.sent_at and n.sent_at + interval '2 hours'
where n.status = 'sent';


-- 6. Pet vs Plain Experiment Comparison (Phase 0 Pilot)
-- Compares engagement, graduation rate, and condition between copy variants.
select
    u.variant,
    count(distinct u.id) as total_users,
    count(distinct g.id) as total_goals,
    count(distinct case when g.status = 'graduated' then g.id end) as graduated_goals,
    count(*) filter (where p.status = 'fed')::numeric / nullif(count(p.id), 0) as on_time_rate,
    round(avg(coalesce((g.result->>'final_condition_pct')::numeric, 0)), 1) as avg_final_condition_pct,
    round(avg(coalesce((g.result->>'final_quality_pct')::numeric, 0)), 1) as avg_final_quality_pct
from budget_care.users u
left join budget_care.goals g on g.user_id = u.id
left join budget_care.feeding_periods p on p.goal_id = g.id and p.status in ('fed', 'missed')
group by u.variant;


-- =============================================================================
-- Operational & Health Inspection Queries
-- =============================================================================

-- 7. Stale Sending Outbox (Should be 0 during normal operation)
select id, goal_id, period_idx, kind, status, attempts, claimed_at, last_error
from budget_care.notifications
where status = 'sending' and claimed_at < now() - interval '5 minutes';

-- 8. Recent Cron Tick Audit Runs (Last 20 executions)
select id, started_at, finished_at, error, stats
from budget_care.tick_runs
order by started_at desc
limit 20;

-- 9. Active Lease Locks
select name, locked_at, locked_by, expires_at, (expires_at < now()) as is_expired
from budget_care.job_locks;
