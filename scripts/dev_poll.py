"""Local long-polling runner for testing bot updates directly with Telegram API."""

import asyncio

from budgetcare.bot.dispatcher import create_bot, create_dispatcher
from budgetcare.config import settings
from budgetcare.logging import setup_logging


async def main() -> None:
    setup_logging("DEBUG")
    if not settings.TELEGRAM_BOT_TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN is not set in .env!")
        return

    bot = create_bot()
    dp = create_dispatcher()

    bot_info = await bot.get_me()
    print(f"[OK] Connected as @{bot_info.username} ({bot_info.first_name})")
    print("[INFO] Starting long polling (Press Ctrl+C to stop)...")

    # Drop any pending updates accumulated while bot was offline
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(bot, polling_timeout=15)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
