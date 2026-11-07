from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, Depends, Request

from budgetcare.api.deps import verify_telegram_secret
from budgetcare.bot.dispatcher import create_bot, create_dispatcher
from budgetcare.logging import logger

router = APIRouter(tags=["telegram"])

# Module-level bot and dispatcher instances for the webhook
bot: Bot | None = None
dispatcher: Dispatcher | None = None


def get_bot() -> Bot:
    global bot
    if bot is None:
        bot = create_bot()
    return bot


def get_dispatcher() -> Dispatcher:
    global dispatcher
    if dispatcher is None:
        dispatcher = create_dispatcher()
    return dispatcher


@router.post("/webhook/telegram", dependencies=[Depends(verify_telegram_secret)])
async def telegram_webhook(request: Request) -> dict[str, bool]:
    bot_inst = get_bot()
    dp_inst = get_dispatcher()

    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": bot_inst})

    try:
        await dp_inst.feed_update(bot_inst, update)
    except Exception as e:  # noqa: BLE001
        logger.error("error_processing_telegram_update", update_id=update.update_id, error=str(e))

    return {"ok": True}
