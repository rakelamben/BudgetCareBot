from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from budgetcare.bot.copy import get_text
from budgetcare.db.tables import UserTable
from budgetcare.db.uow import UnitOfWork

router = Router(name="common")


@router.message(Command("cancel"))
async def handle_cancel(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    await uow.conversations.delete(user.id)
    await message.answer(
        text=get_text("cancelled", user.variant),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def handle_help(message: Message, user: UserTable) -> None:
    await message.answer(
        text=get_text("help", user.variant),
        parse_mode="HTML",
    )
