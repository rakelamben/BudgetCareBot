# Budget Care — System Design Document (v1)

Nov 7, 2026 · @jas

This document is the single engineering anchor for building Budget Care v1. It turns the [PRD v1](https://claude.ai/artifact/BFkY9BgZSbTskw8BNEoass) into decisions, code structure, data model, flows and commands, so development can start without another design document or ADR. The PRD decides product behavior; this document decides implementation. Interpretations that go beyond the PRD are listed in Section 19.

## 1. Scope and how to use this document

- **In scope:** every P0 requirement in PRD Section 8, plus a pilot switch between plain logging and pet framing (PRD Section 12).
- **Out of scope for v1:** P1 and P2 items, multi-currency, the popularity or trust layer, editing goal terms, and any interface other than the Telegram chat.
- **Reading order for builders:** Sections 3-5 (decisions and structure), 6-7 (rules and data), 8-11 (interfaces and flows), 18 (build order).
- **Vocabulary:** a cut-off is the end of a feeding period, shown to users as 23:59 local time. The tick is the scheduled call that runs once a minute. Times are UTC unless marked local. Money is integer cents.

## 2. Requirements and constraints

**PRD-to-design map**

| PRD requirement | Where it lives in this design |
| --- | --- |
| 8.1 Goal setup | `domain/schedule.py`, `services/goals.py`, the `/newgoal` wizard (9.2) |
| 8.2 Due dates and periods | `feeding_periods` table, `domain/timeutil.py` (6.1, 6.2) |
| 8.3 Feeding and logging | `services/feeding.py`, `entries` table, `/feed` and `/undo` (6.3, 6.7, 10) |
| 8.4 Notifications | `domain/notifications.py`, `notifications` table, the tick (6.5, 11) |
| 8.5 Scoring | `domain/scoring.py` (6.4) |
| 8.6 End states and result screen | `services/results.py`, `goals.result`, the tick (6.6, 6.9, 11) |
| 8.7 Goal management | `/goals`, `/settings`, `/delete` (9) |
| 8.8 Commands | `bot/routers/*` (9.1) |
| 11 Non-functional | ledger and derived scores (7), idempotent jobs (11, 12), time (6.1), money (3), Telegram limits (11.4), privacy (13), analytics (14) |

**Non-functional targets** (hypotheses to confirm in the pilot)

| Area | Target |
| --- | --- |
| Pilot scale | 10-20 users; headroom for about 5,000 users and 20,000 active goals |
| Webhook latency | p95 under 1.5 s from Telegram request to reply sent, excluding Telegram's own delay |
| Tick duration | under 25 s per run, never overlapping (lease lock) |
| Notification timing | within 2 minutes of the planned time under normal load |
| Availability | best effort; a missed tick is caught up from stored due times and nothing is lost |
| Cost | free tiers for the pilot (Vercel Hobby, Supabase Free); a paid Supabase tier before real users |

**Load estimate for the headroom case.** 5,000 users with 2 goals each is 10,000 goals. If 60% are daily goals, that is about 6,000 feedings a day and at most 10,000 notification messages a day (one digest per user per slot). The worst peak is 10:00 local in the biggest timezone cluster: 3,000 digests at the 25 messages per second send budget take about 120 s, so reminders can arrive up to 2-3 minutes late at peak. Database load is a few thousand rows a day, which Postgres handles without tuning.

## 3. Technical decisions

| Decision | Choice | Why | Revisit when |
| --- | --- | --- | --- |
| Web framework | FastAPI on ASGI, Pydantic v2 | Your decision. Async, typed, small surface: one webhook route, one tick route, one health route | Not expected |
| Telegram library | aiogram 3.x for Bot API client, types, routers and filters. No aiogram FSM | Async-native; `Dispatcher.feed_update` accepts updates from any ASGI app. Wizard state lives in Postgres because serverless instances share no memory | A feature needs something aiogram lacks |
| Hosting | Vercel Python runtime with FastAPI zero-config, one project per environment | Your decision. No server to manage. The Python runtime is in Beta, so the app stays a plain ASGI app | If Beta limits bite, move the same app to a container host; only the entrypoint and the pg\_cron URL change |
| Database | Supabase Postgres through the shared pooler in transaction mode (port 6543) | Serverless functions open many short connections; the pooler protects Postgres | Dedicated pooler or direct connection on a long-running host |
| DB access | SQLAlchemy 2.0 async with asyncpg, `NullPool`, `statement_cache_size=0` | Supabase documents that transaction mode needs `NullPool` and no prepared statements | Re-enable prepared statements if you adopt the dedicated pooler |
| Migrations | Alembic with hand-written SQL (`op.execute`), run from CI or a laptop over the session pooler (port 5432, IPv4) | Enums, partial indexes and RLS are clearer in SQL than autogenerate. Never run at app start on Vercel | Not expected |
| Scheduler | pg\_cron runs every minute and calls `/internal/tick` through pg\_net | Vercel's own cron is limited on free plans. Business logic stays in Python and is testable; pg\_cron is only a clock | Sub-minute precision or heavy sending: move sending to a queue worker |
| Cron secrets | Supabase Vault holds the tick URL and secret | Keeps secrets out of migrations and out of `cron.job` text | Not expected |
| Scheduling model | Stored due timestamps (`cutoff_at`, `notifications.due_at`), one tick, lease lock | No per-user jobs; works across timezones; idempotent and self-catching-up | Not expected |
| Time zones | `zoneinfo` plus `tzdata`; `timezonefinder` turns a shared location into an IANA name; coordinates are discarded | Handles DST; avoids fixed offsets | Bundle size problem: use a lookup table or an external API |
| Money | Integer cents; `Fraction` or `Decimal` for percentages; never float | Exact sums and rounding | Multi-currency (P2) adds a currency column |
| Conversation state | `conversations` table, one active flow per user | Serverless instances share no memory | Not expected |
| Reply delivery | Handlers return `Reply` objects; they are sent after the database commit | A rolled-back update never produces a misleading message | Not expected |
| Pet art | Supabase Storage public bucket; Telegram `file_id` cached in `pet_images` | No reliance on static file serving from the function | Not expected |
| Observability | JSON logs to stdout, `tick_runs` heartbeat table, external uptime check on `/health?deep=1` | Enough for a pilot | Add error tracking (for example Sentry) as users grow |
| Tooling | uv, ruff, mypy, pytest with pytest-asyncio, hypothesis, time-machine | Fast checks; property tests suit date math | Not expected |

## 4. Architecture overview

&#91;embedded content: architecture · 2 entry points, 4 code layers\]

Telegram posts updates to the webhook route and gets replies; pg\_cron calls the tick route every minute with a secret header; the app reads and writes Postgres through the transaction pooler on port 6543, and Telegram loads pet images from Storage by URL.

| Component | Responsibility |
| --- | --- |
| Telegram | Delivers updates to the webhook and receives the bot's replies |
| Vercel function (FastAPI) | Three routes: webhook, tick, health. Runs handlers, services and domain logic |
| Supabase Postgres | System of record: users, goals, periods, ledger, notifications, conversation state |
| pg\_cron and pg\_net | The clock: POST to `/internal/tick` every minute; hourly purge SQL |
| Supabase Vault | Stores the tick URL and secret that pg\_cron uses |
| Supabase Storage | Public bucket with pet images |

There are two entry points. **Telegram updates** are event-driven and run the synchronous write path. **The tick** is time-driven: it closes periods, finalizes goals and sends notifications.

**Webhook lifecycle**

1. Check the `X-Telegram-Bot-Api-Secret-Token` header; reject with 401 on mismatch.
2. Parse the update and hand it to the aiogram dispatcher.
3. The unit-of-work middleware opens one transaction and inserts the `update_id` into `processed_updates`; a conflict means a retry, so return 200 without doing work.
4. The router calls a handler, which calls services; services use pure domain functions and repositories.
5. Commit, then send the replies the handler collected, then return 200.

**Trust boundaries.** Telegram to Vercel is authenticated by the secret header. pg\_cron to Vercel is authenticated by a second secret header. Vercel to Supabase uses TLS through the pooler with a server-side credential that never leaves the function's environment variables.

## 5. Repository and code structure

```text
budget-care/
├─ main.py                     # Vercel entrypoint: app = create_app()
├─ pyproject.toml              # deps, tool config, requires-python
├─ .python-version
├─ vercel.json                 # region (same as Supabase), maxDuration, excludeFiles
├─ alembic.ini
├─ migrations/
│  ├─ env.py                   # async env, reads DATABASE_URL_MIGRATIONS
│  └─ versions/0001_initial.py # tables, enums, indexes, RLS (SQL)
├─ ops/
│  └─ pg_cron.sql              # Vault secrets + cron schedules; run once per environment
├─ scripts/
│  ├─ set_webhook.py           # setWebhook with secret token and allowed_updates
│  ├─ set_commands.py          # setMyCommands
│  ├─ dev_poll.py              # local long polling through the same dispatcher
│  └─ tick_loop.py             # local stand-in for pg_cron
├─ src/budgetcare/
│  ├─ config.py                # pydantic-settings, all env vars
│  ├─ logging.py               # structlog JSON setup
│  ├─ api/
│  │  ├─ app.py                # create_app(), routers, exception handlers
│  │  ├─ deps.py               # secret checks, db session
│  │  └─ routes/               # telegram.py, internal.py, health.py
│  ├─ bot/
│  │  ├─ dispatcher.py         # builds Bot and Dispatcher, includes routers
│  │  ├─ middleware.py         # UnitOfWorkMiddleware, user loading, reply flush
│  │  ├─ routers/              # start, newgoal, feed, goals, undo, settings, delete, common
│  │  ├─ keyboards.py          # inline and reply keyboards
│  │  ├─ callbacks.py          # callback_data encode and decode
│  │  ├─ copy.py               # all user-facing text, two sets: pet and plain
│  │  └─ parsing.py            # amount parsing and validation
│  ├─ domain/                  # pure Python, no I/O, no clock
│  │  ├─ models.py             # enums and frozen dataclasses
│  │  ├─ money.py              # cents, parsing, formatting
│  │  ├─ timeutil.py           # local dates, cut-off instants, DST-safe helpers
│  │  ├─ schedule.py           # plan_schedule, offered_frequencies
│  │  ├─ scoring.py            # condition, mood tier, service quality
│  │  ├─ notifications.py      # plan_notifications
│  │  └─ pets.py               # species catalog, names, tier to image mapping
│  ├─ services/                # use cases; orchestrate domain and repositories
│  │  ├─ users.py  goals.py  feeding.py  undo.py  settings.py
│  │  ├─ results.py            # result snapshot and titles
│  │  ├─ tick.py               # close periods, finalize goals
│  │  └─ notify.py             # claim, filter, digest, send, acknowledge
│  ├─ db/
│  │  ├─ engine.py             # engine factory (NullPool, no prepared statements)
│  │  ├─ uow.py                # UnitOfWork: session, repositories, outgoing replies
│  │  ├─ tables.py             # SQLAlchemy models mirroring the migration
│  │  └─ repos/                # users, goals, periods, entries, notifications, conversations
│  ├─ integrations/
│  │  └─ telegram.py           # send with rate limit, retry and error mapping
│  └─ analytics.py             # track(name, goal_id, props) into events
└─ tests/
   ├─ unit/                    # domain, parsing, copy
   ├─ integration/             # Postgres: services, tick, concurrency
   └─ e2e/                     # simulated Telegram updates through the ASGI app
```

**Layering rules** (enforced by an import check in CI)

- `domain` imports nothing from the project. It receives `now` and timezones as arguments.
- `services` import `domain` and `db`. They never import aiogram or send messages.
- `bot` imports `services` and `domain`. Handlers return `Reply` objects; only the middleware and `integrations/telegram.py` talk to the Bot API.
- `api` only wires HTTP to `bot` and `services.tick`.
- Always lock the goal row first, then period, entry and notification rows. This single order prevents deadlocks between webhook writes and the tick.

**Conventions**

- Full type hints; mypy strict on `domain` and `services`.
- Services take a `Clock` (`now()`) so tests control time. Domain functions take `now` directly.
- Two error classes: `UserError` (safe to show, carries a copy key) and everything else (a bug: logged, user gets a generic apology).
- Every user-provided string (goal name) is HTML-escaped before it enters a message, because the bot uses HTML parse mode.
- Callback data is built only through `callbacks.py` and never exceeds 64 bytes.
- Runtime dependencies: `fastapi`, `aiogram>=3.20,<4`, `sqlalchemy[asyncio]>=2.0`, `asyncpg`, `alembic`, `pydantic-settings`, `tzdata`, `timezonefinder`, `aiolimiter`, `structlog`. Dev: `pytest`, `pytest-asyncio`, `hypothesis`, `time-machine`, `httpx`, `ruff`, `mypy`.

## 6. Domain rules

All rules here are pure functions in `domain/` and are covered by unit and property tests (Section 16).

### 6.1 Time model

- Instants are stored as UTC `timestamptz`. Calendar math (dates, weekdays, month ends) happens in the user's local zone.
- A **feeding period** is a run of local days ending on a cut-off date. The cut-off instant is **local midnight at the end of that date** (shown as 23:59). An exclusive midnight bound leaves no gap between 23:59:00 and 00:00:00.
- A log's `occurred_at` is the Telegram `message.date` for typed messages (server time for button taps), so webhook delay cannot push a 23:58 message past the cut-off.
- The tick closes a period only after `cutoff_at + 60 s` (`CUTOFF_GRACE_SECONDS`), so slightly late updates still count.
- **Goal start:** day 1 is the next local calendar day after creation. `start_at` is local midnight of that day. Users may advance their first feeding on the creation day (H+0): any deposit or free food before `start_at` immediately counts as the feeding for period 0.

### 6.2 Schedule generation

`plan_schedule(created_at, tz, period_days, frequency, target_cents) -> SchedulePlan | None`

1. `start_date` = local date of `created_at` plus 1 day. `end_date` = `start_date + period_days - 1`.
2. Cut-off dates inside the range: daily = every date; weekly = every Sunday; monthly = the last day of each month. Append `end_date` if it is not already the last one, because the goal's end is always a final cut-off.
3. Period k runs from the day after cut-off k-1 (or `start_date`) to cut-off date k. Its cut-off instant is local midnight after that date.
4. Let `n` be the number of periods. A frequency is offered only if `n >= 2` and `target_cents // n >= 100`.
5. Nominal per feeding = `target_cents // n`. The final period carries the remainder: `target_cents - nominal * (n - 1)`.

`offered_frequencies(...)` runs `plan_schedule` for the three frequencies and returns the valid ones with their plans.

| Case | Cut-off dates | n | Nominal |
| --- | --- | --- | --- |
| 28 days, weekly, starts Mon 2026-11-09, $70 | Nov 15, Nov 22, Nov 29, Dec 6 | 4 | $17.50 each |
| 10 days, monthly, starts Wed 2026-11-25, $20 | Nov 30, Dec 4 (end date) | 2 | $10.00 each |
| 60 days, monthly, starts Fri 2026-11-20, $90 | Nov 30, Dec 31, Jan 18 (end date) | 3 | $30.00 each |
| 3 days, weekly, starts Mon 2026-11-09 | only the end date, Nov 11 | 1 | not offered |
| 2 days, daily | two dates | 2 | allowed if target is at least $2 |

### 6.3 Period lookup and feeding classification

The period of a log is the first period whose `cutoff_at` is later than `occurred_at`; a log before the goal starts belongs to period 0. The feeding service locks the goal row first, then applies this table.

| Situation | Deposit | Give free food |
| --- | --- | --- |
| Before the goal starts (H+0), period 0 not yet fed | Becomes the feeding for period 0 | Becomes the feeding for period 0 |
| Before the goal starts (H+0), period 0 already fed | Extra (money only) | Rejected: already fed |
| Open period, no feeding yet | Becomes the feeding | Becomes the feeding |
| Open period already fed | Extra (money only) | Rejected: already fed |
| Period already closed by the tick (late update) | Extra (money only); the period stays missed | Rejected |
| After the last cut-off | Rejected: goal ended | Rejected |
| Goal graduated or expired | Rejected: goal closed | Rejected |

After every accepted entry the service recomputes totals; if deposited is at least the target, the goal graduates in the same transaction.

### 6.4 Scoring

Let `m` be the missed periods and `n` the total feedings. All values are derived from `feeding_periods` and `entries`, never from stored counters.

| Value | Formula | Notes |
| --- | --- | --- |
| Condition | `100 - m * 100 / n`, floor 0 | Drops only when the tick closes a period as missed. After early graduation the remaining open periods are not counted as missed. Shown rounded **down**, so 100% appears only when nothing was missed |
| Mood tier (image) | 4 if `m = 0`; 3 if condition at least 75; 2 if at least 50; otherwise 1 | Four images per species; below 25% keeps tier 1. Use integer comparison `(n - m) * 100 >= 75 * n` |
| Days elapsed | `clamp((today_local - start_date).days, 0, period_days)` | Whole local days completed |
| Care period | days elapsed / period days |  |
| Deposited | sum of `amount_cents` of entries that are not undone |  |
| Service quality, live | `min(1, deposited / (target * care period))` | Shown as 100% while care period is 0 (per PRD) |
| Service quality, final | `min(1, deposited / target)` | Used in the result snapshot |
| Surplus | `max(0, deposited - target)` |  |
| Hungry (display only) | open period, cut-off in the future, no feeding | Never changes condition by itself |

### 6.5 Notification planning

`plan_notifications(goal, periods, tz, now) -> list[PlannedNotification]` returns rows for `notifications`. It runs at goal creation and again after any change to timezone, notification setting, or reminder day or date.

| Frequency | Reminder | Follow-up (if not fed) |
| --- | --- | --- |
| Daily | 10:00 local on the period's date | 19:00 the same date |
| Weekly | 10:00 on the picked weekday inside the period | 10:00 the next day |
| Monthly | 10:00 on the picked date (1-28) or the last date | 19:00 the next day |

- **Edge rule (PRD 8.4):** if the reminder date is the cut-off date, or the follow-up date would fall after the cut-off date, the follow-up is replaced by an **early warning at 19:00 on the day before the cut-off date**. It is omitted when that day is before the period's first day.
- Clamp the reminder date into the period (partial first or last periods): before the first day becomes the first day; after the last day becomes the last day.
- Add random jitter of 0-299 s to every `due_at`.
- Plan only open periods, only when `notifications_enabled`, and skip any notification whose time has already passed.
- A `result` notification is created by the tick when a goal expires with notifications on (Section 11).
- At send time a notification is skipped if the goal is not active, the period is not open or already fed, or the user is blocked.

Examples: weekly with Sunday picked gives a reminder Sunday 10:00 and an early warning Saturday 19:00. Monthly with the 28th picked in a non-leap February gives a reminder Feb 28 10:00 and an early warning Feb 27 19:00.

### 6.6 Goal lifecycle

&#91;embedded content: goal lifecycle · 3 states, 4 transitions\]

A goal starts active, graduates when deposits reach the target, expires if the last period closes below it, and can return from graduated to active through `/undo` within 24 hours. Deleting a goal or wiping data removes it from any state.

| From | Event | To | Side effects |
| --- | --- | --- | --- |
| none | User confirms in the wizard | active | Goal, periods and notifications created in one transaction; event `goal_created` |
| active | Deposit makes deposited at least the target | graduated | `graduated_at` and `closed_at` set; result snapshot; pending notifications cancelled; result screen sent immediately |
| active | Last period closed below target | expired | `closed_at` set; result snapshot; pending notifications cancelled; result notification if notifications are on |
| graduated | `/undo` of the graduating entry within 24 h | active | `graduated_at`, `closed_at` and `result` cleared; notifications re-planned |
| any | `/delete` or data wipe | removed | Rows deleted by cascade |

### 6.7 Undo rules

- `/undo` targets the user's most recent entry that is not undone and was created within 24 hours (`UNDO_WINDOW_HOURS`).
- It asks for confirmation, then sets `undone_at`. Deposited, condition inputs and live quality update automatically because they are derived.
- A period already closed by the tick keeps its `fed` or `missed` status. Undo never reopens a closed period.
- If the entry was the one that graduated the goal, undo reopens the goal (see 6.6) as long as the goal's last cut-off has not passed.
- A goal that expired cannot be reopened.

### 6.8 Timezone change

A timezone change applies going forward only. For each of the user's active goals, recompute `cutoff_at` for **open** periods from their stored `end_date` in the new zone, recompute `start_at` if the goal has not started, and re-plan pending notifications. Closed periods are never touched. To avoid closing a period retroactively, the earliest open period gets `max(recomputed cut-off, the next local midnight after now)`.

### 6.9 Result snapshot and titles

When a goal closes, `goals.result` stores: `outcome`, `final_condition_pct`, `final_quality_pct`, `mood_tier`, `title`, `days_taken`, `deposited_cents`, `surplus_cents`, `free_food_count`, `closed_at`. `days_taken` is days from `start_date` to the graduation date inclusive, or `period_days` for an expired goal.

| Outcome | Mood tier | Title (default copy) |
| --- | --- | --- |
| Graduated | 4 | Well cared for |
| Graduated | 3 | Cared for |
| Graduated | 2 | Made it through |
| Graduated | 1 | Struggled but made it |
| Expired | 3 or 4 | Almost there |
| Expired | 1 or 2 | Needs another try |

## 7. Data model

Postgres is the system of record. `entries` is the money ledger, `feeding_periods` records cut-off outcomes, `notifications` is the outbox, and `events` is the audit and analytics trail. Scores are derived from these tables, never stored as counters; only the final result snapshot is stored, when a goal closes.

| Table | Purpose | Retention |
| --- | --- | --- |
| `users` | One row per Telegram user: chat id, timezone, pilot variant, blocked flag | Until the user wipes their data |
| `goals` | Goal terms, schedule summary, pet, status, result snapshot | Until deleted by the user |
| `feeding_periods` | One row per feeding period: dates, cut-off instant, nominal, status | Cascades with the goal |
| `entries` | Ledger of deposits and free food, including undone rows | Cascades with the goal |
| `notifications` | Planned and sent notifications (reminder, follow-up, early warning, result) | Cascades with the goal |
| `conversations` | Wizard and pending-input state, one row per user | Idle rows expire after 24 h |
| `processed_updates` | Telegram `update_id` dedupe | 3 days (hourly purge) |
| `job_locks` | Lease lock for the tick | Permanent, one row |
| `tick_runs` | Heartbeat and stats per tick | 7 days (hourly purge) |
| `pet_images` | Cached Telegram `file_id` per species and mood tier | Permanent |
| `events` | Analytics events (Section 14) | Cascades with the user |

```sql
create type goal_frequency as enum ('daily', 'weekly', 'monthly');
create type goal_status    as enum ('active', 'graduated', 'expired');
create type period_status  as enum ('open', 'fed', 'missed');
create type entry_kind     as enum ('deposit', 'free_food');
create type notif_kind     as enum ('reminder', 'follow_up', 'early_warning', 'result');
create type notif_status   as enum ('pending', 'sending', 'sent', 'skipped', 'cancelled', 'failed');

create table users (
  id               bigserial primary key,
  telegram_user_id bigint not null unique,
  chat_id          bigint not null,
  timezone         text,                          -- IANA name; null until a location is shared
  variant          text not null default 'pet',   -- 'pet' or 'plain' (pilot switch)
  blocked_at       timestamptz,
  created_at       timestamptz not null default now()
);

create table goals (
  id                    bigserial primary key,
  user_id               bigint not null references users(id) on delete cascade,
  name                  text not null check (char_length(name) between 1 and 60),
  target_cents          bigint not null check (target_cents > 0),
  period_days           int not null check (period_days between 2 and 365),
  frequency             goal_frequency not null,
  start_date            date not null,            -- local date of day 1
  end_date              date not null,            -- local date of the last day
  start_at              timestamptz not null,     -- local midnight of start_date
  total_feedings        int not null check (total_feedings >= 2),
  nominal_cents         bigint not null check (nominal_cents > 0),
  last_nominal_cents    bigint not null check (last_nominal_cents > 0),
  notifications_enabled boolean not null default true,
  reminder_weekday      smallint check (reminder_weekday between 0 and 6),   -- 0 = Monday
  reminder_dom          smallint check (reminder_dom between 1 and 28),
  reminder_on_last      boolean not null default false,
  species               text not null,
  pet_name              text not null,
  status                goal_status not null default 'active',
  graduated_at          timestamptz,
  closed_at             timestamptz,
  result                jsonb,
  created_at            timestamptz not null default now(),
  constraint reminder_fields check (
       (frequency = 'daily'   and reminder_weekday is null and reminder_dom is null and not reminder_on_last)
    or (frequency = 'weekly'  and reminder_dom is null and not reminder_on_last)
    or (frequency = 'monthly' and reminder_weekday is null and not (reminder_on_last and reminder_dom is not null))
  )
);
create index goals_user_idx on goals (user_id, status);

create table feeding_periods (
  goal_id       bigint not null references goals(id) on delete cascade,
  idx           int not null,
  start_date    date not null,
  end_date      date not null,                    -- local date on which the cut-off falls
  cutoff_at     timestamptz not null,             -- local midnight after end_date
  nominal_cents bigint not null,
  status        period_status not null default 'open',
  closed_at     timestamptz,
  primary key (goal_id, idx)
);
create index feeding_periods_due_idx on feeding_periods (cutoff_at) where status = 'open';

create table entries (
  id               bigserial primary key,
  goal_id          bigint not null references goals(id) on delete cascade,
  period_idx       int not null,
  kind             entry_kind not null,
  amount_cents     bigint not null,
  occurred_at      timestamptz not null,
  is_feeding       boolean not null,
  source_update_id bigint,
  undone_at        timestamptz,
  created_at       timestamptz not null default now(),
  foreign key (goal_id, period_idx) references feeding_periods (goal_id, idx) on delete cascade,
  check ((kind = 'deposit' and amount_cents > 0)
      or (kind = 'free_food' and amount_cents = 0 and is_feeding))
);
create unique index one_feeding_per_period on entries (goal_id, period_idx)
  where is_feeding and undone_at is null;
create index entries_goal_idx on entries (goal_id, id desc);

create table notifications (
  id         bigserial primary key,
  goal_id    bigint not null references goals(id) on delete cascade,
  period_idx int not null,                        -- for 'result': the last period index
  kind       notif_kind not null,
  due_at     timestamptz not null,
  status     notif_status not null default 'pending',
  attempts   int not null default 0,
  claimed_at timestamptz,
  sent_at    timestamptz,
  last_error text,
  unique (goal_id, period_idx, kind)
);
create index notifications_due_idx   on notifications (due_at)     where status = 'pending';
create index notifications_stale_idx on notifications (claimed_at) where status = 'sending';

create table conversations (
  user_id    bigint primary key references users(id) on delete cascade,
  flow       text not null,                       -- newgoal, feed, tz, settings, delete, wipe
  step       text not null,
  data       jsonb not null default '{}',
  updated_at timestamptz not null default now()
);

create table processed_updates (
  update_id   bigint primary key,
  received_at timestamptz not null default now()
);

create table job_locks (
  name         text primary key,
  locked_until timestamptz not null default 'epoch',
  locked_by    text
);
insert into job_locks (name) values ('tick');

create table tick_runs (
  id          bigserial primary key,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  stats       jsonb,
  error       text
);

create table pet_images (
  species          text not null,
  tier             smallint not null check (tier between 1 and 4),
  telegram_file_id text not null,
  primary key (species, tier)
);

create table events (
  id          bigserial primary key,
  user_id     bigint references users(id) on delete cascade,
  goal_id     bigint references goals(id) on delete set null,
  name        text not null,
  props       jsonb not null default '{}',
  occurred_at timestamptz not null default now()
);
create index events_name_time_idx on events (name, occurred_at);
```

**Row-level security.** The migration enables RLS on every table in `public` and creates no policies. The app connects with the project's server-side credential, which bypasses RLS; the Supabase Data API and the anon key therefore see nothing. Also disable the Data API for the project if it is not needed.

**Integrity rules enforced by the database**

- One feeding per period: the partial unique index `one_feeding_per_period`.
- Free food is always a feeding and always zero; deposits are always positive.
- Reminder fields must match the frequency.
- An entry can only reference an existing period of its own goal.

**Rules enforced in code** (configurable, so not in the schema): at least 2 feedings, nominal at least $1, amount cap, name length, one active conversation per user.

## 8. HTTP interface

There are no admin endpoints. Webhook registration and bot commands are set by scripts run from a developer machine or CI.

| Method and path | Caller | Authentication | Purpose and responses |
| --- | --- | --- | --- |
| `POST /webhook/telegram` | Telegram | Header `X-Telegram-Bot-Api-Secret-Token`, constant-time compare | Handles one update. 200 `{"ok": true}` for processed, duplicate, and handled-error updates. 401 on bad secret. 503 only when the database is unreachable, so Telegram retries |
| `POST /internal/tick` | pg\_net | Header `X-Tick-Secret`, constant-time compare | Runs one tick. 200 with stats JSON, or `{"skipped": "locked"}` when another tick holds the lease. 401 on bad secret. 500 on crash, recorded in `tick_runs` |
| `GET /health` | Uptime monitor | None | Liveness only. 200 `{"status": "ok"}` |
| `GET /health?deep=1` | Uptime monitor | None | Runs `select 1` and checks the last successful tick. 200 if the last tick finished within 5 minutes, otherwise 503 |

**Tick response example**

```json
{"tick_id": 1042, "closed_periods": 37, "missed": 6, "expired": 1, "graduated": 0,
 "notifications_claimed": 52, "sent": 48, "skipped": 3, "failed": 1, "duration_ms": 3180}
```

**Webhook registration (`scripts/set_webhook.py`)**

| Parameter | Value |
| --- | --- |
| `url` | `https://<project-domain>/webhook/telegram` |
| `secret_token` | `TELEGRAM_WEBHOOK_SECRET` (letters, digits, underscore, hyphen; up to 256 characters) |
| `allowed_updates` | `message`, `callback_query`, `my_chat_member` |
| `max_connections` | 10 for the pilot, to limit database load |
| `drop_pending_updates` | true on the first deploy of an environment, false afterwards |

## 9. Telegram interface

### 9.1 Commands

| Command | Behavior |
| --- | --- |
| `/start` | Creates or refreshes the user, clears the blocked flag, asks for a location if no timezone is set, otherwise shows a short welcome and `/newgoal` hint |
| `/newgoal` | Starts the goal wizard (9.2). Requires a timezone |
| `/feed [amount]` | Logs a deposit or free food (9.3). A bare number message also works when the user has exactly one active goal |
| `/goals` | Lists active goals and the archive of finished goals with condition, service quality, deposited versus target and the next cut-off (local) |
| `/undo` | Reverses the most recent entry within 24 hours after confirmation (6.7) |
| `/settings` | Per-goal notification on or off and reminder day or date; change timezone; delete all data |
| `/delete` | Deletes one goal after confirmation (9.4) |
| `/cancel` | Abandons the current wizard or pending input. Addition, required for the wizard |
| `/help` | Lists commands and explains condition, service quality and free food in a few lines. Addition |

The bot menu is set with `setMyCommands` by `scripts/set_commands.py`. Unknown commands get a short pointer to `/help`.

### 9.2 The `/newgoal` wizard

State lives in `conversations` (flow `newgoal`, `data` holds the draft). Every step validates input, replies with a fixed prompt, and re-asks on invalid input without losing the draft. Typed answers are plain messages; choices are inline buttons.

| Step | Prompt and input | Validation | Draft fields |
| --- | --- | --- | --- |
| 0 | If the user has no timezone, ask for a location first (F1), then continue | A timezone must exist before step 1 | none |
| 1 name | Goal name, typed | 1-60 characters after trimming; no leading `/` | `name` |
| 2 budget | Budget in dollars, typed | Amount grammar in 9.3; at least `2 * MIN_NOMINAL_CENTS`; at most `MAX_AMOUNT_CENTS` | `target_cents` |
| 3 period | Days, typed | Whole number from 2 to 365 | `period_days` |
| 4 pet | System picks species and name and sends the reveal (photo at tier 4 plus a line of text) | Species and name pair not already used by the user's active goals | `species`, `pet_name` |
| 5 frequency | Buttons for each valid frequency, labeled with feedings and amount, for example `Every week: 4 x $17.50`. If none is valid, explain and return to step 2 | `offered_frequencies` | `frequency` |
| 6 schedule | Show number of feedings, nominal amount, first cut-off date, and the cost of one missed feeding in condition (for example 25%) | Display only | `schedule_date` (local date shown) |
| 7 notifications | Buttons On or Off |  | `notifications_enabled` |
| 8 reminder pick | Only if on and weekly: weekday buttons Monday to Sunday. Only if on and monthly: date buttons 1-28 plus Last date |  | `reminder_weekday`, `reminder_dom`, `reminder_on_last` |
| 9 confirm | Summary of everything, including the notification times, with Confirm and Cancel | If the local date changed since step 6, recompute the schedule and show the summary again | none |

On Confirm, one transaction creates the goal, its periods and its notifications, deletes the conversation row and records `goal_created`. Cancel or `/cancel` deletes the conversation row and the draft pet is discarded.

### 9.3 Feeding input

- **Amount grammar:** `^\$?\s*(\d{1,7})(\.\d{1,2})?$`. Accepted: `10`, `$10`, `10.50`. Rejected with a copy message: zero, negative, more than two decimals, thousands separators, comma decimals, text. Maximum `MAX_AMOUNT_CENTS` (default $1,000,000).
- **One active goal:** `/feed 10` or a bare `10` records the deposit directly. `/feed` alone asks for the amount and shows a Give free food button.
- **Several active goals:** the bot first shows one button per pet. The amount (if already typed) is kept in the conversation row and used after the choice.
- **Replies:** a deposit that becomes the feeding says so and shows condition and live service quality. An extra says the deposit was added and the feeding was already counted. Free food confirms the feeding and notes that it adds $0.
- **Graduation:** when a deposit reaches the target the reply is the result screen (6.9) with the mood tier 4 or best-available image.

### 9.4 Goals, settings, delete, wipe

- **`/goals`:** one message with an Active section and an Archive section. Each goal has a Details button that shows the pet image for its mood tier, the schedule remaining, and a Feed button.
- **`/settings`:** a menu with three entries. Goal notifications: pick a goal, toggle notifications, change the reminder weekday or date; every change re-plans notifications (6.5). Change timezone: runs F1 and then 6.8. Delete all my data: asks for a button confirmation, then asks the user to type `DELETE`; on match, deletes the user row (cascade) and replies with a short goodbye.
- **`/delete`:** pick a goal, confirm with Delete forever or Keep. Deletion cascades to periods, entries and notifications, and records `goal_deleted` with the goal id set to null.

### 9.5 Callback data

Format `<prefix>:<action>:<args>`, at most 64 bytes, built only by `callbacks.py`. Every callback is validated against current state (goal exists and belongs to the user, flow and step match); stale buttons get a short alert and no action. Every callback query is answered with `answerCallbackQuery`.

| Callback | Meaning |
| --- | --- |
| `nf:f:daily`, `nf:f:weekly`, `nf:f:monthly` | Wizard: choose frequency |
| `nf:n:1`, `nf:n:0` | Wizard: notifications on or off |
| `nf:w:0` to `nf:w:6` | Wizard: reminder weekday (0 = Monday) |
| `nf:d:1` to `nf:d:28`, `nf:d:last` | Wizard: reminder date |
| `nf:ok`, `nf:no` | Wizard: confirm or cancel |
| `fd:g:<goal_id>` | Feeding: choose the pet |
| `fd:f:<goal_id>` | Feeding: give free food |
| `gl:v:<goal_id>` | Goals: details view |
| `ud:ok:<entry_id>`, `ud:no` | Undo: confirm or keep |
| `st:g:<goal_id>`, `st:n:<goal_id>:1`, `st:n:<goal_id>:0`, `st:r:<goal_id>`, `st:tz`, `st:wipe` | Settings actions |
| `dl:g:<goal_id>`, `dl:ok:<goal_id>`, `dl:no` | Delete: choose, confirm, keep |

### 9.6 Pet catalog and reveal

`domain/pets.py` holds the species list (placeholder set: hamster, rabbit, cat, duckling, turtle, hedgehog; the final list is an art decision) and a name pool per species. Selection is uniform random, retried up to 5 times to avoid a species and name pair already used by the user's active goals. Images live at `pets/<species>/<tier>.png` in the Storage bucket (tiers 1-4, Section 6.4). The first send of an image uses its public URL; the returned Telegram `file_id` is cached in `pet_images` and reused.

### 9.7 Copy and the pilot variant

All user-facing text lives in `bot/copy.py` as keyed templates in two sets, `pet` and `plain`, chosen by `users.variant`. The plain set talks about a goal and a deposit and never mentions pets, condition or free food; the pet set uses the product vocabulary. A new user gets a variant at `/start` (default `pet`; the pilot assigns half and half). Core keys: `welcome`, `ask_location`, `tz_saved`, `ask_name`, `ask_budget`, `ask_period`, `pet_reveal`, `pick_frequency`, `schedule_summary`, `confirm_goal`, `goal_created`, `feed_recorded`, `feed_extra`, `feed_free`, `graduated`, `expired`, `digest_reminder`, `digest_followup`, `digest_early_warning`, `undo_confirm`, `undo_done`, `delete_confirm`, `error_generic`. No emoji in the keys; emoji are added per species in the pet set.

### 9.8 User-facing errors

| Condition | Copy key | Next step offered |
| --- | --- | --- |
| Invalid amount | `err_amount` | Re-ask |
| No active goal | `err_no_goal` | `/newgoal` |
| No timezone | `err_no_tz` | Location request |
| Goal not started, deposit | Accepted (money only); reply notes it will count toward the total | None |
| Goal not started, free food | `err_not_started` | None |
| Already fed this period, free food | `err_already_fed` | None |
| Goal ended or closed | `err_goal_closed` | `/goals` |
| Wizard expired (over 24 h idle) | `err_expired_flow` | `/newgoal` |
| Stale button | Alert text, no message | None |
| Unexpected error | `error_generic` | Try again |

## 10. Data flows

Every flow that changes data runs inside the unit of work (Section 4): dedupe, state change and event write commit together; replies are sent after the commit.

**F1. Onboarding and timezone**

1. `/start` upserts the user by `telegram_user_id`, sets `chat_id`, clears `blocked_at`, assigns a `variant` if new.
2. If `timezone` is null, the bot sets the conversation to flow `tz` and sends a reply keyboard with a request-location button, saying the location is used only to find the timezone and is not stored.
3. A location message is accepted only in flow `tz`. `timezonefinder` maps latitude and longitude to an IANA name; if none is found (open sea), the bot asks again.
4. Save `timezone`, drop the coordinates, remove the keyboard, delete the conversation row, record `timezone_set`.
5. If a previous timezone existed, run the timezone change (F8). If the flow was started from `/newgoal`, continue the wizard.

**F2. Goal creation**

1. Wizard steps 1-9 (9.2) update `conversations.data`.
2. On Confirm, recompute `plan_schedule` with the current time. If the first cut-off date differs from `schedule_date`, show the new summary and ask again.
3. Insert the goal, all `feeding_periods` (cut-off instants from `cutoff_at`), and the planned `notifications`.
4. Delete the conversation row, record `goal_created`, reply with the created confirmation and the pet at tier 4.

**F3. Feeding (deposit or free food)**

1. Parse input; resolve the goal (single goal, or the pet-picker callback).
2. Lock the goal row. Reject if it is not active or the last cut-off has passed.
3. Locate the period for `occurred_at` and classify with the table in 6.3.
4. Insert the entry with `period_idx`, `is_feeding`, `occurred_at` and `source_update_id`.
5. Recompute deposited. If deposited is at least the target: set `graduated`, write the result snapshot, cancel pending notifications, record `goal_graduated`.
6. Record `feeding_logged`, `extra_deposit` or `free_food_used`. Build the reply: confirmation plus condition and live quality, or the result screen on graduation.

**F4. Tick, part A: closing periods** (details in Section 11)

1. Acquire the lease; stop if held by a live tick.
2. Find goals with open periods whose `cutoff_at + grace` has passed.
3. For each goal (locked first): mark each due period `fed` if it has an active feeding entry, otherwise `missed`.
4. If the closed period is the last one, finalize: `graduated` if deposited is at least the target (defensive), otherwise `expired`; write the result snapshot; cancel pending notifications; if notifications are on, insert a `result` notification due now.

**F5. Tick, part B: sending notifications** (details in Section 11)

1. Reclaim stale `sending` rows.
2. Claim due `pending` rows in a short transaction.
3. Drop rows that are no longer relevant (goal inactive, period closed or fed, user blocked).
4. Group the rest by user into one digest per user; send `result` notifications individually.
5. Acknowledge each row in a short transaction: sent, skipped, retry, or failed. Record stats in `tick_runs`.

**F6. Undo**

1. `/undo` finds the user's latest entry within 24 hours that is not undone; if none, say so.
2. Show the entry (goal, amount or free food, time) with Undo and Keep buttons.
3. On confirm: lock the goal, set `undone_at`. If the entry graduated the goal and the last cut-off has not passed, reopen it and re-plan notifications. If the goal expired, reply that it is closed.
4. Record `entry_undone` and reply with the updated condition and live quality.

**F7. Delete goal and wipe all data**

1. `/delete`: pick the goal, confirm; delete the goal row (cascade); record `goal_deleted`.
2. Wipe: confirm with a button, then require the text `DELETE`; delete the user row (cascade, which removes goals, entries, notifications, conversations and events); send a goodbye reply.

**F8. Timezone change**

1. For each active goal of the user, apply 6.8: recompute `cutoff_at` of open periods, `start_at` if not started.
2. Delete pending notifications and re-plan them with the new zone.
3. Closed periods and past entries are left as they are.

**F9. Block and unblock**

1. A `my_chat_member` update with status `kicked` for a private chat, or a 403 while sending, sets `blocked_at` and cancels the user's pending notifications.
2. A `my_chat_member` update with status `member`, or any message from the user, clears `blocked_at` and re-plans notifications for active goals.
3. Record `bot_blocked` or `bot_unblocked`.

## 11. Scheduling and notification delivery

### 11.1 pg\_cron setup

`ops/pg_cron.sql` is run once per environment in the Supabase SQL editor. It needs the `pg_cron`, `pg_net` and Vault features enabled. The URL and secret are stored in Vault, not in the schedule text.

```sql
select vault.create_secret('https://<project-domain>/internal/tick', 'tick_url');
select vault.create_secret('<TICK_SECRET value>', 'tick_secret');

select cron.schedule('budgetcare-tick', '* * * * *', $$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'tick_url'),
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-Tick-Secret', (select decrypted_secret from vault.decrypted_secrets where name = 'tick_secret')),
    body := '{}'::jsonb,
    timeout_milliseconds := 30000
  );
$$);

select cron.schedule('budgetcare-purge', '17 * * * *', $$
  delete from processed_updates where received_at < now() - interval '3 days';
  delete from tick_runs         where started_at  < now() - interval '7 days';
  delete from conversations     where updated_at  < now() - interval '1 day';
$$);
```

Pg\_net calls are asynchronous and fire-and-forget; the tick keeps its own record in `tick_runs`. To debug the clock itself:

```sql
select * from cron.job_run_details order by start_time desc limit 20;
select * from net._http_response where status_code >= 400 or error_msg is not null order by created desc limit 20;
```

### 11.2 Tick algorithm

1. **Lease.** Update `job_locks` set `locked_until = now() + 120 s` where name is `tick` and `locked_until < now()`. No row updated means another tick is alive: return `{"skipped": "locked"}`. The lease also recovers by itself 2 minutes after a crash.
2. **Start the run.** Insert a `tick_runs` row.
3. **Reclaim stale sends.** Rows in `sending` with `claimed_at` older than 5 minutes go back to `pending`; rows that reached the maximum attempts become `failed`.
4. **Part A: close periods.** One pass over up to 500 goals that have due open periods. Each goal is closed in its own transaction (F4). Stop early when the time budget (25 s) is used.
5. **Part B: send notifications.** Claim, filter, group, send, acknowledge (F5 and 11.4), within the remaining budget.
6. **Finish.** Release the lease, write stats and any error to `tick_runs`, return the stats JSON.

```python
async def run_tick(clock, db, bot, cfg) -> TickStats:
    if not await db.acquire_lease("tick", ttl_seconds=cfg.tick_lease_seconds):
        return TickStats(skipped="locked")
    run_id, stats, t0 = await db.start_run(), TickStats(), monotonic()
    deadline = t0 + cfg.tick_time_budget_seconds
    try:
        await requeue_stale_claims(db, cfg)
        for goal_id in await goals_with_due_periods(db, clock.now(), limit=500):
            if monotonic() > deadline:
                break
            stats.add(await close_goal_periods(db, goal_id, clock.now(), cfg))
        stats.add(await send_due_notifications(db, bot, clock, cfg, deadline))
    except Exception as exc:
        stats.error = repr(exc)
        raise
    finally:
        await db.release_lease("tick")
        await db.finish_run(run_id, stats)
    return stats


async def close_goal_periods(db, goal_id, now, cfg) -> TickStats:
    async with db.uow() as uow:  # one transaction per goal
        goal = await uow.goals.lock_skip_locked(goal_id)  # FOR UPDATE SKIP LOCKED
        if goal is None or goal.status != "active":
            return TickStats()  # busy or already closed; next tick retries
        stats = TickStats()
        cutoff = now - timedelta(seconds=cfg.cutoff_grace_seconds)
        for p in await uow.periods.due_open(goal_id, cutoff):  # ordered by idx
            fed = await uow.entries.has_active_feeding(goal_id, p.idx)
            await uow.periods.close(goal_id, p.idx, "fed" if fed else "missed", now)
            stats.closed += 1
            stats.missed += 0 if fed else 1
        if await uow.periods.all_closed(goal_id):
            stats.add(await results.finalize_goal(uow, goal, now))  # expired or graduated
        return stats
```

### 11.3 Key queries

```sql
-- goals that have periods to close
select distinct p.goal_id
  from feeding_periods p join goals g on g.id = p.goal_id
 where p.status = 'open' and g.status = 'active'
   and p.cutoff_at <= now() - make_interval(secs => :grace)
 limit 500;

-- claim notifications (short transaction), then send outside the transaction
update notifications n
   set status = 'sending', claimed_at = now(), attempts = n.attempts + 1
 where n.id in (
   select id from notifications
    where status = 'pending' and due_at <= now()
    order by due_at
    limit :batch
    for update skip locked)
returning n.*;

-- reclaim stale claims
update notifications
   set status = case when attempts >= :max_attempts then 'failed' else 'pending' end
 where status = 'sending' and claimed_at < now() - interval '5 minutes';
```

All due comparisons use the database clock (`now()`), so a slow or skewed function clock cannot close a period early.

### 11.4 Sending rules and Telegram limits

- **Relevance filter** after claiming: skip (status `skipped`) when the goal is not active, the period is not open, the period already has a feeding, the user is blocked or the goal's notifications are off. `result` notifications skip only the blocked check.
- **Digest:** group the remaining rows by user and send one message listing every pet that is due, with one Feed and one Free food button per pet (at most 8 pets, then a line pointing to `/feed`). `result` notifications are sent one by one with the pet image.
- **Rate limits:** a global limiter of 25 messages per second (`aiolimiter`) and at least 1 second between messages to the same chat. Telegram's guidance for bulk sending is roughly 30 messages per second, so 25 leaves headroom. Never send more than `SEND_BATCH_SIZE` (200) messages per tick.
- **Jitter:** `due_at` already carries 0-299 s of jitter, which spreads the 10:00 peak.

```text
2 pets are hungry
- Mochi (Lombok trip): feed by Sunday 23:59, about $17.50
- Pip (New outfit): last call, closes tomorrow 23:59
[Feed Mochi] [Free food]
[Feed Pip]   [Free food]
```

| Telegram response | Meaning | Action |
| --- | --- | --- |
| 200 | Sent | Status `sent`, set `sent_at` |
| 429 with `retry_after` | Rate limited | Stop the batch; put unsent rows back to `pending` (attempts minus 1); log |
| 403 (bot blocked, user deactivated) | Cannot message this user | Set `blocked_at`, cancel the user's pending notifications (F9) |
| 400 chat not found | Invalid chat | Same as 403 |
| 400 other (for example formatting) | Our bug | Status `failed`, log with the row id, no retry |
| 5xx or network timeout | Transient | Back to `pending`; after 3 attempts `failed` |

### 11.5 Catch-up and staleness

Period closing depends only on stored timestamps and entries, so after an outage the next tick produces the same result it would have produced on time. Notifications are different: a 10:00 reminder sent at 18:00 is noise. Pending reminders, follow-ups and early warnings whose `due_at` is more than 3 hours old are marked `skipped` (`STALE_NOTIFICATION_HOURS`). `result` notifications are never skipped for age.

## 12. Concurrency, idempotency and error handling

| Scenario | Mechanism |
| --- | --- |
| Telegram redelivers an update | `update_id` inserted into `processed_updates` in the same transaction as the work; a conflict returns 200 without work |
| Two messages from one user at once | The goal row lock serializes them; the partial unique index `one_feeding_per_period` is the backstop |
| Webhook write and tick touch the same goal | Lock order is always goal first; the tick uses `SKIP LOCKED` and picks the goal up on the next minute |
| Two ticks overlap | Lease row with a 120 s time to live |
| Tick crashes midway | Each goal closes in its own transaction and only open periods are processed, so a rerun is safe |
| Notification possibly sent twice | Claim, send, acknowledge. A crash between send and acknowledge leaves `sending`, which is reclaimed after 5 minutes. At-least-once delivery is accepted |
| Reply fails after commit | Logged, not retried. The state is correct; the user can see it in `/goals` |
| Database unreachable during a webhook | Return 503 so Telegram retries |
| Unexpected exception in a handler | Roll back, log with `update_id`, send the generic apology, return 200 to avoid a retry storm |
| Late update after a cut-off | `occurred_at` is the message time and the tick waits 60 s of grace |
| Stale button or expired wizard | Every callback and step is validated against current state before acting |
| Cold start | First request after idle is slower; handlers stay within the latency target because the work is a few queries |

## 13. Security and privacy

- **Secrets.** Bot token, webhook secret, tick secret and database URL live in Vercel environment variables; the cron URL and secret live in Vault. Nothing secret is committed. Rotation: change the variable, redeploy, rerun `set_webhook.py` for the webhook secret, update the Vault secrets for the tick secret.
- **Verification.** Both secret headers use constant-time comparison and fail closed if the server-side value is not set.
- **Data kept.** Telegram user id, chat id, timezone, and goal, deposit and event data. Not kept: name, username, phone number, language, and location coordinates (used once to find the timezone, then discarded).
- **Deletion.** `/settings` offers a full wipe (F7). Backups may retain data until they expire under the Supabase plan; say so in `/help` or a privacy note.
- **Logging.** Log ids and event names, not message text, goal names or amounts, at info level. Never log the bot token or secrets.
- **Input handling.** Parameterized queries only (SQLAlchemy); HTML-escape user text in messages; length and range limits on every input.
- **Database exposure.** RLS on with no policies and the Data API disabled (Section 7). The service credential never reaches a client.
- **Abuse guard.** A technical cap of 100 active goals per user (`MAX_ACTIVE_GOALS_PER_USER`) prevents unbounded notification rows; the product itself stays unlimited in practice. Telegram's own limits cover message flooding for the pilot.
- **Supply chain.** Lockfile (`uv.lock`) committed; dependency update bot enabled.

## 14. Observability and operations

**Logging.** JSON lines to stdout (Vercel logs) through structlog, with `event`, `level`, `ts`, `update_id`, `user_id`, `goal_id`, `tick_id` and `duration_ms` when known.

**Heartbeat and alerts.** `tick_runs` records each run. An external uptime monitor calls `/health?deep=1` every minute and alerts on 503. Other alerts: more than 5% of notifications `failed` in a day; any row in `net._http_response` with status 400 or above for the tick URL; a paused Supabase project.

**Analytics events** (table `events`, written in the same transaction as the change):

| Event | When | Properties |
| --- | --- | --- |
| `user_started` | First `/start` | `variant` |
| `timezone_set` | Location accepted | none |
| `goal_created` | Wizard confirmed | `frequency`, `period_days`, `target_cents`, `notifications` |
| `feeding_logged` | A deposit becomes the feeding | `on_time_gap_s` (seconds before cut-off) |
| `extra_deposit` | Deposit in an already fed period | `amount_cents` |
| `free_food_used` | Free food recorded | none |
| `goal_graduated` | Target reached | `early`, `condition_pct` |
| `goal_expired` | Goal closed below target | `final_quality_pct`, `condition_pct` |
| `entry_undone` | Undo confirmed | `kind` |
| `goal_deleted` | Goal deleted | none |
| `notification_sent`, `notification_failed` | Delivery outcome | `kind` |
| `bot_blocked`, `bot_unblocked` | F9 | none |

PRD metrics map to SQL over these tables. On-time feeding rate, for example:

```sql
select count(*) filter (where status = 'fed')::numeric / nullif(count(*), 0) as on_time_rate
  from feeding_periods where status in ('fed', 'missed');
```

Day-7 and day-21 retention come from `users.created_at` and `events`; free-food rate from `free_food_used` over `feeding_logged`; block rate from `bot_blocked` over `user_started`. A notification counts as acted on if a feeding follows within 2 hours of `notification_sent`. Telegram does not report opens.

**Runbook, first checks**

| Symptom | Check |
| --- | --- |
| Reminders stopped | `cron.job_run_details`, `net._http_response`, latest `tick_runs`, Vercel logs, Supabase project status |
| Duplicate messages | Rows stuck in `sending`, tick duration near its limit |
| A cut-off looks wrong | The user's `timezone` and `feeding_periods.cutoff_at` for that goal |
| Webhook failing | Telegram `getWebhookInfo` (last error), Vercel logs, the secret token |
| Bad deploy | Vercel instant rollback; migrations are written to be backward compatible (add first, remove later) |

## 15. Configuration and environments

**Environment variables** (read by `config.py` with pydantic-settings)

| Name | Default | Notes |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | none | From BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | none | Sent by Telegram in the secret header |
| `TICK_SECRET` | none | Shared with pg\_cron through Vault |
| `DATABASE_URL` | none | `postgresql+asyncpg://` URL of the shared pooler, transaction mode, port 6543 |
| `DATABASE_URL_MIGRATIONS` | none | Session pooler (port 5432) or direct connection; used only by Alembic |
| `APP_ENV` | `local` | `local`, `staging` or `production` |
| `LOG_LEVEL` | `INFO` |  |
| `PET_IMAGE_BASE_URL` | none | Public Storage URL prefix for pet images |
| `CUTOFF_GRACE_SECONDS` | 60 | Wait after a cut-off before closing |
| `TICK_TIME_BUDGET_SECONDS` | 25 | Per tick |
| `TICK_LEASE_SECONDS` | 120 | Lease time to live |
| `SEND_RATE_PER_SECOND` | 25 | Global send limiter |
| `SEND_BATCH_SIZE` | 200 | Messages per tick |
| `MAX_NOTIFICATION_ATTEMPTS` | 3 |  |
| `STALE_CLAIM_MINUTES` | 5 |  |
| `STALE_NOTIFICATION_HOURS` | 3 |  |
| `NOTIFY_JITTER_SECONDS` | 300 |  |
| `UNDO_WINDOW_HOURS` | 24 |  |
| `CONVERSATION_TTL_HOURS` | 24 |  |
| `MAX_ACTIVE_GOALS_PER_USER` | 100 | Abuse guard |
| `DEFAULT_VARIANT` | `pet` | Pilot copy set |

Business constants (minimum 2 feedings, minimum $1 per feeding, amount cap) live in `config.py`. The period bounds 2 and 365 are also in the schema, so changing them needs a migration.

**Environments**

|  | Local | Staging | Production |
| --- | --- | --- | --- |
| Bot | Test bot, long polling | Second bot from BotFather, webhook | Production bot, webhook |
| Database | Local Postgres (docker compose or Supabase CLI) | Separate Supabase project | Supabase project |
| App | `dev_poll.py` | Vercel Preview or a staging project | Vercel Production |
| Tick | `tick_loop.py` calls the endpoint every 60 s | pg\_cron | pg\_cron |

**Local development**

1. `uv sync`, then start Postgres and run `alembic upgrade head`.
2. `uv run python scripts/dev_poll.py` removes any webhook and polls Telegram through the same dispatcher, middleware and services as production.
3. `uv run python scripts/tick_loop.py` calls the tick every 60 seconds. Pg\_cron and pg\_net are not needed locally.

**First deployment of an environment**

1. Create the Supabase project; run `alembic upgrade head` with `DATABASE_URL_MIGRATIONS`.
2. Create the public Storage bucket `pets` and upload the pet images.
3. Create the Vercel project from the repository; set the environment variables; choose a region near the Supabase region; deploy.
4. Run `scripts/set_webhook.py` and `scripts/set_commands.py`.
5. Run `ops/pg_cron.sql` with the real URL and secret.
6. Verify: `/start` replies, `/health?deep=1` returns 200 within 2 minutes, `tick_runs` fills up.

**Release rules.** Merging to `main` deploys production through the Vercel Git integration. Preview deployments use the staging variables. Migrations are applied before the code that needs them and are written as add-then-remove (expand and contract), so rollback of the code never meets an incompatible schema.

## 16. Testing strategy

| Level | Scope | Tools |
| --- | --- | --- |
| Unit | `domain/`, amount parsing, copy (every key exists in both the `pet` and `plain` sets), callback encoding (never over 64 bytes) | pytest, hypothesis, time-machine |
| Integration | Repositories, services (goals, feeding, undo, results), tick, claim and acknowledge, migrations on an empty database | pytest-asyncio, real Postgres, rollback or truncate per test |
| End to end | Simulated Telegram updates through `/webhook/telegram` with a fake Bot that records replies; the wizard from `/start` to graduation; the tick through `/internal/tick` | httpx ASGI transport |
| Load and soak | 5,000 users and 10,000 goals seeded; tick closes and sends within its budget with a fake Bot | script in `tests/`, run at milestone M7 |

**Property tests (hypothesis)**

- Nominals sum exactly to the target, and the last nominal is at least the others.
- Cut-off dates strictly increase, the last equals `end_date`, and the count equals `total_feedings`.
- Every date of the goal belongs to exactly one period.
- Cut-off instants strictly increase and each is a local midnight, across Asia/Jakarta, Europe/London, America/New\_York, Pacific/Auckland and Australia/Lord\_Howe (DST, half-hour offsets).
- Condition never increases as missed periods grow; mood tier boundaries are exact at 100, 75, 50 and 25.
- Planned notification times fall inside their period; no follow-up falls after the cut-off; an early warning exists only when the edge rule applies.

**Concurrency tests.** Many simultaneous deposits to one period leave exactly one feeding. A webhook write and a tick on the same goal never deadlock. Two ticks started together: exactly one acquires the lease. Running the tick twice produces no extra changes.

**PRD acceptance criteria to tests**

| PRD criterion | Test |
| --- | --- |
| 8.1 28-day $70 weekly gives 4 feedings of $17.50 | `test_plan_weekly_28_days` |
| 8.1 frequency with fewer than 2 feedings not offered | `test_frequency_below_min_feedings_not_offered` |
| 8.1 nothing created before confirm | `test_no_rows_before_confirm` |
| 8.2 February cut-off in a non-leap year | `test_monthly_cutoff_feb_28` |
| 8.2 cut-off uses the user's timezone | `test_cutoff_instant_uses_user_timezone` |
| 8.3 first deposit is the feeding, condition unchanged | `test_first_deposit_is_feeding` |
| 8.3 second deposit is an extra | `test_second_deposit_is_extra` |
| 8.3 reaching target mid-period graduates and cancels notifications | `test_graduates_and_cancels_notifications` |
| 8.3 free food keeps condition and adds $0 | `test_free_food_keeps_condition` |
| 8.4 one follow-up for a daily goal | `test_daily_followup_once` |
| 8.4 one digest per user per slot | `test_one_digest_per_user` |
| 8.4 fed period sends nothing | `test_fed_period_skips_notifications` |
| 8.5 one miss of four gives 75% | `test_condition_75_after_one_miss_of_four` |
| 8.5 open unfed period does not drop condition | `test_open_period_keeps_condition` |
| 8.5 $35 deposited after 14 of 28 days gives live quality 100% | `test_live_quality_on_pace` |
| 8.5 surplus shows 100% and is tracked | `test_quality_capped_surplus_tracked` |
| 8.7 delete cancels notifications | `test_delete_cancels_notifications` |

**CI pipeline.** ruff check and format check, mypy, import-layer check, pytest (unit and integration, Postgres as a service), `alembic upgrade head` on an empty database. Coverage gates: 95% branch coverage on `domain`, 85% on `services`.

## 17. Scale, reliability and failure modes

| Failure | Effect | Recovery |
| --- | --- | --- |
| Vercel deploy broken or function down | Webhook returns errors, Telegram retries; the tick fails | Instant rollback. Closing catches up on the next good tick; stale notifications are skipped (11.5) |
| Supabase paused or down | Webhook returns 503; the tick fails; deep health returns 503 | Alert fires; resume the project; the system catches up |
| pg\_cron stops or pg\_net fails | No ticks: periods stay open, no reminders | Heartbeat alert; fix the schedule; catch-up applies |
| Telegram API down or rate limiting | Sends fail or slow | Retry up to 3 attempts, then `failed`; 429 stops the batch |
| Connection exhaustion | Errors on database access | Pooler in transaction mode, `NullPool`, webhook `max_connections` 10 |
| Cold start | One slow first response | Accepted; keep the bundle small |

**Scaling levers, in order**

1. Raise `SEND_BATCH_SIZE` and the time budget; split the sender into its own route called by a second cron job so closing and sending run in parallel.
2. Move sending to a queue (for example Supabase Queues) when volume passes roughly 50,000 messages a day.
3. Move to a long-running host with a direct or dedicated-pooler connection; only the entrypoint and the cron URL change.
4. Partition or export `events` when analytics queries get heavy.

## 18. Build plan

| Milestone | Scope | Exit criteria |
| --- | --- | --- |
| M0 Skeleton and infrastructure | Repo, CI, config, logging, Vercel and Supabase projects, webhook registered, `/health`, secret check, `/start` reply | `/start` replies from the deployed function; CI green |
| M1 Domain core | `money`, `timeutil`, `schedule`, `scoring`, `notifications`, `pets`, `parsing`, with property tests | Unit tests and acceptance tests for 8.1, 8.2, 8.4 planning and 8.5 pass without a database |
| M2 Data layer | Initial migration, tables, repositories, unit of work, dedupe, conversations, events | Integration tests pass; migration applies on an empty database; RLS on |
| M3 Onboarding and goal creation | `/start`, location to timezone, `/newgoal` wizard, creation transaction, re-confirm rule | End-to-end test from `/start` to a created goal with periods and notifications |
| M4 Feeding | `/feed`, free food, extras, classification, graduation, result screen, `/undo` with reopen | Acceptance tests for 8.3 and 8.6 and the concurrency tests pass |
| M5 Tick and notifications | Lease, closing, finalize, outbox, digest, sending, retries, blocked handling, pg\_cron SQL, heartbeat | Tick idempotency test; 48 hours on staging with a real bot and pg\_cron; the pilot can start |
| M6 Management and polish | `/goals`, `/settings`, `/delete`, wipe, `/help`, `/cancel`, timezone change, pet art, both copy sets, analytics events | Every PRD P0 acceptance criterion green; manual script walked through on staging |
| M7 Hardening and launch | Soak test, failure drills (kill the tick mid-send, pause the database, simulate 429), runbook rehearsal, privacy note | Drills pass; metric queries return sensible numbers |

**Pilot (PRD Phase 0).** M0 to M5 are enough to run the pet versus plain experiment if the first release offers only the daily frequency, no undo and no settings, with `users.variant` driving the copy set. M6 and M7 continue while the pilot runs.

**Definition of done for any change.** Typed and tested; user-facing text only in `copy.py`; migration is backward compatible; logs carry ids; if a decision changes, this document is updated through a comment or edit here, with no separate ADR file.

## 19. Interpretations, assumptions and deviations from the PRD

These resolve gaps in the PRD. Each can be reversed by changing the named module.

1. **Cut-off instant:** local midnight at the end of the cut-off date, shown as 23:59 (`domain/timeutil.py`).
2. **Pre-start deposits (Advance first feeding / Option A):** a deposit or free food made after goal creation on day H+0 before day 1 (local midnight start_at) immediately counts as the feeding for period 0 (`is_feeding = True`), feeding the pet without delay. If period 0 is already fed, subsequent deposits before day 1 count as extra deposits (`is_feeding = False`), and subsequent free food is rejected. Period 0 cut-off remains tomorrow at 23:59 local.
3. **Early graduation and condition:** condition is `100 - missed * 100 / total`. The PRD's "on-time feedings divided by total feedings" gives the same value only for goals that run to expiry; periods that never came due after an early graduation are not counted as missed.
4. **Timestamp and grace:** a log's time is the Telegram message time; the tick waits 60 seconds after a cut-off before closing.
5. **Expiry result:** the result is pushed only when the goal's notifications are on; otherwise it appears in `/goals`. Graduation always replies immediately.
6. **Scope of settings:** notification on or off and reminder day or date are per goal (as in the wizard); the timezone is per user.
7. **Undo reopens a graduation:** undoing the entry that graduated a goal within 24 hours reopens it if the last cut-off has not passed. Closed periods are never reopened.
8. **Free food twice:** free food in an already fed period is rejected, because it would change nothing.
9. **Digest scope:** items due in the same tick are merged into one message per user; a reminder and a follow-up for different goals merge only if due in the same tick.
10. **Additions:** `/cancel`, `/help`, a bare number as a shortcut for `/feed` with one goal, the pilot `variant` switch, the `result` notification kind, and a technical cap of 100 active goals per user.
11. **Timezone change:** future cut-offs move to the new zone; the earliest open period gets the later of the recomputed time and the next local midnight so nothing closes retroactively.
12. **Stale notifications:** reminders, follow-ups and early warnings more than 3 hours late are skipped.
13. **Idle wizard:** conversations expire after 24 hours of inactivity.
14. **Display:** condition is shown rounded down, so 100% means nothing was missed.
15. **Mood image below 25%:** keeps the lowest of the four images (per the PRD edit).
16. **Deletion:** deleted goals are hard-deleted; finished goals stay in the archive. The PRD's P1 soft-archive of deleted goals is not part of v1.
17. **Location:** never stored; only the IANA timezone name.

## 20. Risks and what to revisit as the system grows

| Risk | Mitigation now | Revisit when |
| --- | --- | --- |
| Vercel Python runtime is in Beta | Plain ASGI app, pinned versions, nothing Vercel-specific outside `main.py` and `vercel.json` | A Beta limit bites, or general availability changes behavior |
| Supabase free tier can pause a quiet project and stop reminders | Deep health alert; paid tier before real users | Before the pilot goes beyond friends |
| Location sharing may be hard on some Telegram clients | Explain in `/help`; a manual `/timezone <name>` fallback is a small addition | Any user reports being stuck at onboarding |
| `timezonefinder` adds bundle size and cold-start time | Measure at M0 | Bundle approaches the platform limit or cold start exceeds 2 s |
| One tick closes periods and sends messages | Closing runs first, with a time budget | Volume passes about 50,000 messages a day: queue and separate sender |
| pg\_net is fire-and-forget | `tick_runs` heartbeat and response-table checks | More observability is needed |
| Notifications are at-least-once | Reclaim after 5 minutes; rare duplicates accepted | Users complain |
| Analytics live in the main database | Index on name and time | Queries slow the app |
| No admin tooling | Runbook and Supabase Studio queries | After the pilot |
| English only | All text keyed in `copy.py` | Localization (PRD P2; Indonesian is the likely first) |
| Pet art volume (4 images per species) | Placeholders until art is final | Art finishes |
| Spam or abuse | Telegram limits plus the 100-goal cap | Per-user rate limiter if abuse appears |

## Appendix A. Worked example

Goal: Lombok trip, $70, 28 days, weekly, notifications on with Saturday as reminder day. Created Sunday 2026-11-08 by a user in Asia/Jakarta (UTC+7).

| Table | Stored values |
| --- | --- |
| `goals` | `start_date` 2026-11-09, `end_date` 2026-12-06, `start_at` 2026-11-08 17:00 UTC, `total_feedings` 4, `nominal_cents` 1750, `last_nominal_cents` 1750 |
| `feeding_periods` | idx 0: Nov 9 to Nov 15, cut-off 2026-11-15 17:00 UTC. idx 1: Nov 16 to Nov 22, cut-off 11-22 17:00 UTC. idx 2: Nov 23 to Nov 29, cut-off 11-29 17:00 UTC. idx 3: Nov 30 to Dec 6, cut-off 12-06 17:00 UTC |
| `notifications` | Per period, a reminder Saturday 10:00 local (03:00 UTC) and a follow-up Sunday 10:00 local, each with jitter: Nov 14 and 15, Nov 21 and 22, Nov 28 and 29, Dec 5 and 6 |

| When (local) | What happens | State afterwards |
| --- | --- | --- |
| Sat Nov 14 | Deposit $17.50 (period 0) | Feeding recorded; condition 100%; deposited $17.50; the Sunday follow-up is skipped at send time |
| Sat Nov 21 | Give free food (period 1) | Feeding recorded, adds $0; condition 100% |
| Mon Nov 23, morning | User opens `/goals` | Days elapsed 14, care period 50%, live quality $17.50 divided by ($70 times 0.5) = 50% |
| Mon Nov 30, 00:01 | Tick closes period 2: no feeding | Missed; condition 75%; mood tier 3 |
| Thu Dec 3 | Deposit $52.50 (period 3, becomes the feeding) | Deposited $70.00, which reaches the target: graduated; condition 75%, quality 100%, tier 3, title Cared for, 25 days taken, surplus $0; pending notifications cancelled; result screen sent |
