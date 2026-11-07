from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from budgetcare.bot.copy import get_text
from budgetcare.bot.keyboards import undo_confirm_keyboard
from budgetcare.db.tables import UserTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.domain.money import format_cents
from budgetcare.domain.timeutil import get_user_tz
from budgetcare.services.undo import apply_undo, get_undo_candidate

router = Router(name="undo")


@router.message(Command("undo"))
async def handle_undo_command(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    candidate = await get_undo_candidate(uow, user.id)
    if not candidate:
        await message.answer(get_text("undo_err_none", user.variant))
        return

    goal = await uow.goals.get_by_id(candidate.goal_id)
    if not goal:
        await message.answer(get_text("err_generic", user.variant))
        return

    tz = get_user_tz(user.timezone)
    occurred_str = candidate.occurred_at.astimezone(tz).strftime("%a, %d %b %H:%M")
    amount_str = (
        format_cents(candidate.amount_cents) if candidate.kind == "deposit" else "Free Food ($0)"
    )

    prompt = get_text(
        "undo_prompt",
        user.variant,
        name=goal.name,
        pet_name=goal.pet_name,
        amount=amount_str,
        occurred_at=occurred_str,
    )
    await message.answer(prompt, reply_markup=undo_confirm_keyboard(candidate.id))


@router.callback_query(F.data.startswith("un:"))
async def handle_undo_callback(callback: CallbackQuery, user: UserTable, uow: UnitOfWork) -> None:
    data = callback.data or ""
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    await callback.answer()

    if action == "no":
        if callback.message:
            await callback.message.edit_text("❌ Action cancelled. Deposit kept.")
        return

    if action == "ok" and len(parts) > 2:
        entry_id = int(parts[2])
        res = await apply_undo(
            uow=uow,
            user_id=user.id,
            entry_id=entry_id,
            now=datetime.now(UTC),
        )

        if not res.success or not res.goal:
            err_msg = res.error_message or get_text("err_generic", user.variant)
            if callback.message:
                await callback.message.edit_text(f"⚠️ {err_msg}")
            return

        goal = res.goal
        amount_str = format_cents(res.entry.amount_cents if res.entry else 0)
        target_str = format_cents(res.target_cents)
        deposited_str = format_cents(res.deposited_cents)

        msg = get_text(
            "undo_success",
            user.variant,
            amount=amount_str,
            pet_name=goal.pet_name,
            deposited=deposited_str,
            target=target_str,
            condition=res.condition_pct,
            quality=res.quality_pct,
        )

        if res.reopened:
            msg += "\n\n" + get_text("undo_reopened", user.variant, name=goal.name)

        if callback.message:
            await callback.message.edit_text(msg)
