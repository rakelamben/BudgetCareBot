from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from budgetcare.bot.middleware import UnitOfWorkMiddleware
from budgetcare.bot.routers import (
    common,
    delete,
    feed,
    goals,
    newgoal,
    start,
    undo,
)
from budgetcare.bot.routers import (
    settings as settings_router,
)
from budgetcare.config import settings


def create_bot() -> Bot:
    return Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # Register unit of work middleware for message and callback query updates
    uow_mw = UnitOfWorkMiddleware()
    dp.message.outer_middleware(uow_mw)
    dp.callback_query.outer_middleware(uow_mw)

    # Register routers in priority order
    dp.include_router(common.router)
    dp.include_router(start.router)
    dp.include_router(goals.router)
    dp.include_router(newgoal.router)
    dp.include_router(feed.router)
    dp.include_router(undo.router)
    dp.include_router(delete.router)
    dp.include_router(settings_router.router)

    return dp
