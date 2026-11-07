"""Set or delete Telegram Webhook for Budget Care."""

import asyncio
import sys

from budgetcare.bot.dispatcher import create_bot
from budgetcare.config import settings


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/set_webhook.py <webhook_url | delete> [--drop-pending]")
        return

    url = sys.argv[1]
    drop = "--drop-pending" in sys.argv

    bot = create_bot()
    try:
        if url == "delete":
            await bot.delete_webhook(drop_pending_updates=drop)
            print("[OK] Webhook deleted successfully.")
        else:
            await bot.set_webhook(
                url=url,
                secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
                drop_pending_updates=drop,
            )
            print(f"[OK] Webhook successfully registered to: {url}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
