-- Budget Care - pg_cron and pg_net configuration
-- Execute once in Supabase SQL Editor per environment.

-- 1. Create Vault Secrets
-- Replace placeholders with real values before executing:
-- select vault.create_secret('https://<your-vercel-domain>/internal/tick', 'tick_url');
-- select vault.create_secret('<your-TICK_SECRET-value>', 'tick_secret');

-- 2. Schedule the Tick Loop (Every Minute)
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

-- 3. Schedule the Purge Routine (Hourly at minute 17)
select cron.schedule('budgetcare-purge', '17 * * * *', $$
  delete from budget_care.processed_updates where received_at < now() - interval '3 days';
  delete from budget_care.tick_runs         where started_at  < now() - interval '7 days';
  delete from budget_care.conversations     where updated_at  < now() - interval '1 day';
$$);
