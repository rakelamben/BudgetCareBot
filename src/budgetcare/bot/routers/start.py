from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from budgetcare.bot.copy import get_text
from budgetcare.bot.keyboards import location_keyboard, remove_reply_keyboard
from budgetcare.db.tables import UserTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.services.users import update_timezone_from_coords

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    if not user.timezone:
        await uow.conversations.set_state(
            user_id=user.id,
            flow="tz",
            step="ask_location",
            data={},
        )
        await message.answer(
            text=get_text("ask_location", user.variant),
            reply_markup=location_keyboard(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            text=get_text("welcome", user.variant),
            parse_mode="HTML",
        )


@router.message(F.location)
async def handle_location(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    conv = await uow.conversations.get(user.id)
    if not conv or conv.flow != "tz":
        return

    loc = message.location
    if not loc:
        return

    tz_name = await update_timezone_from_coords(
        uow=uow,
        user_id=user.id,
        lat=loc.latitude,
        lng=loc.longitude,
    )

    await uow.conversations.delete(user.id)

    if tz_name:
        await message.answer(
            text=get_text("tz_saved", user.variant, tz=tz_name),
            reply_markup=remove_reply_keyboard(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            text="⚠️ Could not determine your timezone from that location. Please try sharing again.",
            reply_markup=location_keyboard(),
            parse_mode="HTML",
        )
