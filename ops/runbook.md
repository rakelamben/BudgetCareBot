# Budget Care v1 — Operations & Incident Runbook

This runbook guides on-call engineers and operators in maintaining, troubleshooting, and recovering **Budget Care v1**.

---

## 1. System Architecture Overview

- **Web Service**: FastAPI deployed on Vercel / serverless runtime.
- **Bot Engine**: Aiogram 3.x processing updates from `/webhook/telegram` or local polling.
- **Database**: Supabase PostgreSQL (schema `budget_care`), accessed via Transaction Pooler (`6543`).
- **Scheduler**: Supabase `pg_cron` invoking `pg_net` to trigger `POST /internal/tick` every minute (`* * * * *`).

---

## 2. Health Monitoring & Alerts

| Check | URL / Target | Alert Condition | Action |
| --- | --- | --- | --- |
| Deep Health Check | `GET /health?deep=1` | Returns `HTTP 503` or timeouts | Check Supabase project status, connection pooler, or DB pause. |
| Shallow Health | `GET /health` | Returns non-200 | Vercel runtime deployment down. Roll back immediately. |
| Tick Runs Freshness | `budget_care.tick_runs` | No successful tick in last 3 minutes | Verify `cron.job_run_details` and `net._http_response`. |
| Outbox Failure Rate | `budget_care.notifications` | > 5% notifications `failed` in 24h | Check Telegram Bot API status / rate limits. |

---

## 3. Incident Triage Matrix

### Incident A: Reminders / Notifications Stopped

1. **Check Cron Execution**:
   ```sql
   select * from cron.job_run_details order by start_time desc limit 5;
   ```
   If failed, verify `pg_cron` extension is active and `pg_net` is responsive.

2. **Check HTTP Responses from Postgres to App**:
   ```sql
   select * from net._http_response order by created desc limit 5;
   ```
   - Status 401: Vault tick secret does not match `TICK_SECRET` environment variable.
   - Status 504 / timeout: Tick function exceeded Vercel execution timeout.

3. **Check Stale Sending Claims**:
   ```sql
   select count(*) from budget_care.notifications
    where status = 'sending' and claimed_at < now() - interval '5 minutes';
   ```
   *Automatic recovery*: The tick engine automatically reclaims stale sending notifications every minute on start.

---

### Incident B: Telegram 429 Rate Limiting

- **Symptom**: Logs show `batch_stopped_by_telegram_rate_limit`.
- **System Behavior**: The bot engine immediately halts the current tick's notification batch, releases the lease, and preserves pending notifications for the next cycle.
- **Resolution**:
  - Verify `SEND_RATE_PER_SECOND` (default 25 msg/s).
  - If user volume has grown, reduce `SEND_BATCH_SIZE` or split notifications across multiple cron slots.

---

### Incident C: Stuck Lease Locks

- **Symptom**: `tick_runs` shows `skipped: "locked"`, but no tick is actively running.
- **Check Active Locks**:
  ```sql
  select name, locked_at, locked_by, expires_at, (expires_at < now()) as expired
    from budget_care.job_locks;
  ```
- **Resolution**:
  Lease locks automatically expire after `TICK_LEASE_SECONDS` (120 seconds).
  If a manual unlock is needed:
  ```sql
  delete from budget_care.job_locks where name = 'tick';
  ```

---

### Incident D: User Blocked the Bot

- **Symptom**: User blocked the bot or deleted account.
- **System Behavior**: Bot automatically detects Telegram HTTP 403 (`TelegramForbiddenError`) or chat not found (400), sets `users.blocked_at = now()`, cancels all pending notifications for that user's goals, and records `bot_blocked` in `events`. No operator action required.

---

## 4. Rollback & Disaster Recovery

1. **Bad Application Deployment**:
   - Vercel Dashboard $\rightarrow$ Deployments $\rightarrow$ Instant Rollback to previous known-good deployment.
   - Database migrations in `migrations/versions/` are strictly backward-compatible.
2. **Database Pause / Maintenance**:
   - Supabase Studio $\rightarrow$ Resume Project.
   - Once database is back online, the next tick automatically catches up: closing overdue periods (respecting message timestamps + grace period) and sending eligible notifications.

---

## 5. Routine Maintenance

- Run analytics queries from `ops/metrics_queries.sql` weekly to review on-time habit rates and pilot variant performance.
- Clean up historical audit rows periodically (`pg_cron.sql` cleans up `tick_runs` older than 30 days every hour).
