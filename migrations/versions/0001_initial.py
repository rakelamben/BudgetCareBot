"""0001 initial schema with tables, enums, indexes, constraints, and RLS

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-07 21:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("create schema if not exists budget_care")
    op.execute("set search_path to budget_care, public")

    # 1. Enums in budget_care schema
    op.execute("""
        do $$ begin
            create type budget_care.goal_frequency as enum ('daily', 'weekly', 'monthly');
        exception when duplicate_object then null; end $$
    """)

    op.execute("""
        do $$ begin
            create type budget_care.goal_status as enum ('active', 'graduated', 'expired');
        exception when duplicate_object then null; end $$
    """)

    op.execute("""
        do $$ begin
            create type budget_care.period_status as enum ('open', 'fed', 'missed');
        exception when duplicate_object then null; end $$
    """)

    op.execute("""
        do $$ begin
            create type budget_care.entry_kind as enum ('deposit', 'free_food');
        exception when duplicate_object then null; end $$
    """)

    op.execute("""
        do $$ begin
            create type budget_care.notif_kind as enum ('reminder', 'follow_up', 'early_warning', 'result');
        exception when duplicate_object then null; end $$
    """)

    op.execute("""
        do $$ begin
            create type budget_care.notif_status as enum ('pending', 'sending', 'sent', 'skipped', 'cancelled', 'failed');
        exception when duplicate_object then null; end $$
    """)

    # 2. Users table
    op.execute("""
        create table if not exists budget_care.users (
            id bigserial primary key,
            telegram_user_id bigint not null unique,
            chat_id bigint not null,
            timezone text,
            variant text not null default 'pet',
            blocked_at timestamptz,
            created_at timestamptz not null default now()
        )
    """)

    # 3. Goals table
    op.execute("""
        create table if not exists budget_care.goals (
            id bigserial primary key,
            user_id bigint not null references budget_care.users(id) on delete cascade,
            name text not null check (char_length(name) between 1 and 60),
            target_cents bigint not null check (target_cents > 0),
            period_days int not null check (period_days between 2 and 365),
            frequency budget_care.goal_frequency not null,
            start_date date not null,
            end_date date not null,
            start_at timestamptz not null,
            total_feedings int not null check (total_feedings >= 2),
            nominal_cents bigint not null check (nominal_cents > 0),
            last_nominal_cents bigint not null check (last_nominal_cents > 0),
            notifications_enabled boolean not null default true,
            reminder_weekday smallint check (reminder_weekday between 0 and 6),
            reminder_dom smallint check (reminder_dom between 1 and 28),
            reminder_on_last boolean not null default false,
            species text not null,
            pet_name text not null,
            status budget_care.goal_status not null default 'active',
            graduated_at timestamptz,
            closed_at timestamptz,
            result jsonb,
            created_at timestamptz not null default now(),
            constraint reminder_fields check (
                (frequency = 'daily' and reminder_weekday is null and reminder_dom is null and not reminder_on_last)
                or (frequency = 'weekly' and reminder_dom is null and not reminder_on_last)
                or (frequency = 'monthly' and reminder_weekday is null and not (reminder_on_last and reminder_dom is not null))
            )
        )
    """)
    op.execute("create index if not exists goals_user_idx on budget_care.goals (user_id, status)")

    # 4. Feeding periods table
    op.execute("""
        create table if not exists budget_care.feeding_periods (
            goal_id bigint not null references budget_care.goals(id) on delete cascade,
            idx int not null,
            start_date date not null,
            end_date date not null,
            cutoff_at timestamptz not null,
            nominal_cents bigint not null,
            status budget_care.period_status not null default 'open',
            closed_at timestamptz,
            primary key (goal_id, idx)
        )
    """)
    op.execute(
        "create index if not exists feeding_periods_due_idx on budget_care.feeding_periods (cutoff_at) where status = 'open'"
    )

    # 5. Entries table
    op.execute("""
        create table if not exists budget_care.entries (
            id bigserial primary key,
            goal_id bigint not null references budget_care.goals(id) on delete cascade,
            period_idx int not null,
            kind budget_care.entry_kind not null,
            amount_cents bigint not null,
            occurred_at timestamptz not null,
            is_feeding boolean not null,
            source_update_id bigint,
            undone_at timestamptz,
            created_at timestamptz not null default now(),
            foreign key (goal_id, period_idx) references budget_care.feeding_periods (goal_id, idx) on delete cascade,
            check ((kind = 'deposit' and amount_cents > 0)
                or (kind = 'free_food' and amount_cents = 0 and is_feeding))
        )
    """)
    op.execute("""
        create unique index if not exists one_feeding_per_period on budget_care.entries (goal_id, period_idx)
            where is_feeding and undone_at is null
    """)
    op.execute(
        "create index if not exists entries_goal_idx on budget_care.entries (goal_id, id desc)"
    )

    # 6. Notifications table
    op.execute("""
        create table if not exists budget_care.notifications (
            id bigserial primary key,
            goal_id bigint not null references budget_care.goals(id) on delete cascade,
            period_idx int not null,
            kind budget_care.notif_kind not null,
            due_at timestamptz not null,
            status budget_care.notif_status not null default 'pending',
            attempts int not null default 0,
            claimed_at timestamptz,
            sent_at timestamptz,
            last_error text,
            unique (goal_id, period_idx, kind)
        )
    """)
    op.execute(
        "create index if not exists notifications_due_idx on budget_care.notifications (due_at) where status = 'pending'"
    )
    op.execute(
        "create index if not exists notifications_stale_idx on budget_care.notifications (claimed_at) where status = 'sending'"
    )

    # 7. Conversations table
    op.execute("""
        create table if not exists budget_care.conversations (
            user_id bigint primary key references budget_care.users(id) on delete cascade,
            flow text not null,
            step text not null,
            data jsonb not null default '{}',
            updated_at timestamptz not null default now()
        )
    """)

    # 8. Processed updates table
    op.execute("""
        create table if not exists budget_care.processed_updates (
            update_id bigint primary key,
            received_at timestamptz not null default now()
        )
    """)

    # 9. Job locks table
    op.execute("""
        create table if not exists budget_care.job_locks (
            name text primary key,
            locked_until timestamptz not null default 'epoch',
            locked_by text
        )
    """)
    op.execute("insert into budget_care.job_locks (name) values ('tick') on conflict do nothing")

    # 10. Tick runs table
    op.execute("""
        create table if not exists budget_care.tick_runs (
            id bigserial primary key,
            started_at timestamptz not null default now(),
            finished_at timestamptz,
            stats jsonb,
            error text
        )
    """)

    # 11. Pet images table
    op.execute("""
        create table if not exists budget_care.pet_images (
            species text not null,
            tier smallint not null check (tier between 1 and 4),
            telegram_file_id text not null,
            primary key (species, tier)
        )
    """)

    # 12. Events table
    op.execute("""
        create table if not exists budget_care.events (
            id bigserial primary key,
            user_id bigint references budget_care.users(id) on delete cascade,
            goal_id bigint references budget_care.goals(id) on delete set null,
            name text not null,
            props jsonb not null default '{}',
            occurred_at timestamptz not null default now()
        )
    """)
    op.execute(
        "create index if not exists events_name_time_idx on budget_care.events (name, occurred_at)"
    )

    # 13. Enable Row-Level Security on all tables in budget_care
    for table_name in [
        "users",
        "goals",
        "feeding_periods",
        "entries",
        "notifications",
        "conversations",
        "processed_updates",
        "job_locks",
        "tick_runs",
        "pet_images",
        "events",
    ]:
        op.execute(f"alter table budget_care.{table_name} enable row level security")


def downgrade() -> None:
    for table_name in [
        "events",
        "pet_images",
        "tick_runs",
        "job_locks",
        "processed_updates",
        "conversations",
        "notifications",
        "entries",
        "feeding_periods",
        "goals",
        "users",
    ]:
        op.execute(f"drop table if exists budget_care.{table_name} cascade")

    for type_name in [
        "notif_status",
        "notif_kind",
        "entry_kind",
        "period_status",
        "goal_status",
        "goal_frequency",
    ]:
        op.execute(f"drop type if exists budget_care.{type_name}")
