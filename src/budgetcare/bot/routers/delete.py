from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from budgetcare.bot.copy import get_text
from budgetcare.bot.keyboards import delete_confirm_keyboard, delete_picker_keyboard
from budgetcare.db.tables import UserTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.domain.pets import SPECIES_EMOJI
from budgetcare.services.settings import delete_single_goal

router = Router(name="delete")


@router.message(Command("delete"))
async def handle_delete_command(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    # Reset any active conversation state
    await uow.conversations.delete(user.id)

    active_goals = await uow.goals.list_active_by_user(user.id)
    if not active_goals:
        await message.answer(get_text("err_no_goal", user.variant), parse_mode="HTML")
        return

    if len(active_goals) == 1:
        goal = active_goals[0]
        pet_emoji = SPECIES_EMOJI.get(goal.species.lower(), "🐾")
        text = get_text(
            "delete_prompt",
            user.variant,
            name=goal.name,
            pet_name=goal.pet_name,
            pet_emoji=pet_emoji,
        )
        await message.answer(
            text,
            reply_markup=delete_confirm_keyboard(goal.id),
            parse_mode="HTML",
        )
    else:
        goals_tuples = [(g.id, g.pet_name, g.name) for g in active_goals]
        await message.answer(
            get_text("delete_pick", user.variant),
            reply_markup=delete_picker_keyboard(goals_tuples),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("dl:"))
async def handle_delete_callback(callback: CallbackQuery, user: UserTable, uow: UnitOfWork) -> None:
    data = callback.data or ""
    parts = data.split(":")
    action = parts[1]

    if action == "no":
        try:
            await callback.answer()
        except Exception:
            pass
        await uow.conversations.delete(user.id)
        cancelled_text = get_text("delete_cancelled", user.variant)
        try:
            if isinstance(callback.message, Message):
                await callback.message.edit_text(cancelled_text, parse_mode="HTML")
            elif callback.message and callback.bot:
                await callback.bot.edit_message_text(
                    text=cancelled_text,
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    parse_mode="HTML",
                )
        except Exception:
            if callback.bot and callback.message:
                await callback.bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=cancelled_text,
                    parse_mode="HTML",
                )
        return

    if action == "g":
        goal_id = int(parts[2])
        goal = await uow.goals.get_by_id(goal_id)
        if not goal or goal.user_id != user.id:
            try:
                await callback.answer("Goal not found.", show_alert=True)
            except Exception:
                pass
            return

        try:
            await callback.answer()
        except Exception:
            pass

        pet_emoji = SPECIES_EMOJI.get(goal.species.lower(), "🐾")
        text = get_text(
            "delete_prompt",
            user.variant,
            name=goal.name,
            pet_name=goal.pet_name,
            pet_emoji=pet_emoji,
        )
        kb = delete_confirm_keyboard(goal.id)
        try:
            if isinstance(callback.message, Message):
                await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            elif callback.message and callback.bot:
                await callback.bot.edit_message_text(
                    text=text,
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    reply_markup=kb,
                    parse_mode="HTML",
                )
        except Exception:
            if callback.bot and callback.message:
                await callback.bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=text,
                    reply_markup=kb,
                    parse_mode="HTML",
                )

    elif action == "ok":
        goal_id = int(parts[2])
        goal = await uow.goals.get_by_id(goal_id)
        if not goal or goal.user_id != user.id:
            try:
                await callback.answer("Goal not found.", show_alert=True)
            except Exception:
                pass
            return

        try:
            await callback.answer()
        except Exception:
            pass

        goal_name = goal.name
        await delete_single_goal(uow, user.id, goal.id)
        await uow.conversations.delete(user.id)

        done_text = get_text("delete_done", user.variant, name=goal_name)
        try:
            if isinstance(callback.message, Message):
                await callback.message.edit_text(done_text, parse_mode="HTML")
            elif callback.message and callback.bot:
                await callback.bot.edit_message_text(
                    text=done_text,
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    parse_mode="HTML",
                )
        except Exception:
            if callback.bot and callback.message:
                await callback.bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=done_text,
                    parse_mode="HTML",
                )
