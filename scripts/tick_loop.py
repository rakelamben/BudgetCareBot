"""Local tick loop runner for executing tick cycles periodically without pg_cron."""

import asyncio

from budgetcare.logging import logger, setup_logging
from budgetcare.services.tick import run_tick


async def main() -> None:
    setup_logging("INFO")
    logger.info("starting_local_tick_loop", interval_seconds=60)
    print("[INFO] Starting local tick loop every 60s (Press Ctrl+C to stop)...")
    try:
        while True:
            try:
                stats = await run_tick()
                logger.info("tick_executed", stats=stats.to_dict())
                print(f"[TICK] {stats.duration_ms}ms | Closed: {stats.periods_closed} | Sent: {stats.notifications_sent} | Skipped: {stats.skipped}")
            except Exception as e:  # noqa: BLE001
                logger.exception("tick_loop_error", error=str(e))
                print(f"[ERROR] Tick failed: {e}")
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        print("\n[INFO] Local tick loop stopped.")


if __name__ == "__main__":
    asyncio.run(main())
