from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from budgetcare.bot.copy import get_text
from budgetcare.bot.keyboards import pet_free_food_picker_keyboard, pet_picker_keyboard
from budgetcare.bot.parsing import parse_amount_to_cents
from budgetcare.db.tables import UserTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.domain.money import format_cents
from budgetcare.domain.pets import SPECIES_EMOJI
from budgetcare.domain.timeutil import get_user_tz
from budgetcare.services.feeding import FeedingResult, feed_goal

router = Router(name="feed")

MOOD_EMOJIS = {
    4: "😄",
    3: "🙂",
    2: "😐",
    1: "🥺",
}


def _format_feeding_reply(res: FeedingResult, variant: str, tz_name: str | None) -> str:
    """Helper to build HTML reply text for a FeedingResult."""
    goal = res.goal
    if not goal:
        return get_text("err_generic", variant)

    tz = get_user_tz(tz_name)
    next_cutoff_str = (
        res.next_cutoff.astimezone(tz).strftime("%a, %d %b %H:%M")
        if res.next_cutoff
        else "Completed"
    )

    amount_str = format_cents(res.entry.amount_cents if res.entry else 0)
    target_str = format_cents(res.target_cents)
    deposited_str = format_cents(res.deposited_cents)
    progress_pct = (
        min(100, int((res.deposited_cents * 100) // res.target_cents))
        if res.target_cents > 0
        else 100
    )
    mood_emoji = MOOD_EMOJIS.get(res.mood_tier.value, "🐾")
    pet_emoji = SPECIES_EMOJI.get(goal.species.lower(), "🐾")

    if res.is_graduated:
        result_data = goal.result or {}
        surplus_str = format_cents(result_data.get("surplus_cents", 0))
        return get_text(
            "feed_graduated",
            variant,
            name=goal.name,
            pet_name=goal.pet_name,
            final_condition=res.condition_pct,
            final_quality=res.quality_pct,
            title=result_data.get("title", "Graduated"),
            deposited=deposited_str,
            surplus=surplus_str,
            days_taken=result_data.get("days_taken", goal.period_days),
        )

    if res.is_free_food:
        return get_text(
            "feed_free_food",
            variant,
            pet_name=f"{pet_emoji} {goal.pet_name}",
            condition=res.condition_pct,
            mood_emoji=mood_emoji,
            quality=res.quality_pct,
        )

    if res.is_extra:
        return get_text(
            "feed_extra",
            variant,
            pet_name=f"{pet_emoji} {goal.pet_name}",
            amount=amount_str,
            deposited=deposited_str,
            target=target_str,
            progress_pct=progress_pct,
            quality=res.quality_pct,
        )

    return get_text(
        "feed_success",
        variant,
        pet_name=f"{pet_emoji} {goal.pet_name}",
        amount=amount_str,
        condition=res.condition_pct,
        mood_emoji=mood_emoji,
        deposited=deposited_str,
        target=target_str,
        progress_pct=progress_pct,
        quality=res.quality_pct,
        next_cutoff=next_cutoff_str,
    )


@router.message(Command("feed"))
async def handle_feed_command(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    text = message.text or ""
    parts = text.strip().split(maxsplit=1)

    active_goals = await uow.goals.list_active_by_user(user.id)
    if not active_goals:
        await message.answer(get_text("err_no_goal", user.variant))
        return

    # Check if amount was supplied as argument, e.g. /feed 10 or /feed 0
    if len(parts) > 1:
        arg = parts[1].strip()
        amount_cents = parse_amount_to_cents(arg)
        if amount_cents is None:
            await message.answer(get_text("err_amount", user.variant))
            return

        if len(active_goals) == 1:
            # Single goal -> execute immediately
            goal = active_goals[0]
            res = await feed_goal(
                uow=uow,
                user_id=user.id,
                goal_id=goal.id,
                amount_cents=amount_cents,
                occurred_at=message.date.astimezone(UTC),
                source_update_id=message.message_id,
            )
            if not res.success:
                err_text = get_text(
                    f"feed_err_{res.error_code}",
                    user.variant,
                    status=res.goal.status if res.goal else "unknown",
                    pet_name=goal.pet_name,
                )
                await message.answer(err_text)
                return

            reply = _format_feeding_reply(res, user.variant, user.timezone)
            await message.answer(reply)
        else:
            # Multiple goals -> show picker
            goals_tuples = [(g.id, g.pet_name, g.name) for g in active_goals]
            if amount_cents == 0:
                kb = pet_free_food_picker_keyboard(goals_tuples)
            else:
                kb = pet_picker_keyboard(goals_tuples, amount_cents)
            await message.answer(get_text("feed_pick_pet", user.variant), reply_markup=kb)
    else:
        # Bare /feed without amount -> Prompt user or offer Free Food button if single goal
        if len(active_goals) == 1:
            goal = active_goals[0]
            pet_emoji = SPECIES_EMOJI.get(goal.species.lower(), "🐾")
            goals_tuples = [(goal.id, goal.pet_name, goal.name)]
            kb = pet_free_food_picker_keyboard(goals_tuples)
            await message.answer(
                f"🍽 How much would you like to feed {pet_emoji} <b>{goal.pet_name}</b>?\n\n"
                "• Type a number (e.g. <code>10</code> or <code>$10</code>)\n"
                "• Or press below to give free food ($0) for today:",
                reply_markup=kb,
            )
        else:
            goals_tuples = [(g.id, g.pet_name, g.name) for g in active_goals]
            kb = pet_free_food_picker_keyboard(goals_tuples)
            await message.answer(
                "🍽 Which pet would you like to give free food ($0) to? "
                "(To deposit money, type: <code>/feed [amount]</code>):",
                reply_markup=kb,
            )


@router.callback_query(F.data.startswith("fd:"))
async def handle_feed_callback(callback: CallbackQuery, user: UserTable, uow: UnitOfWork) -> None:
    data = callback.data or ""
    parts = data.split(":")
    # fd:g:<goal_id>:<amount_cents> OR fd:ff:<goal_id>
    if len(parts) < 3:
        await callback.answer()
        return

    action = parts[1]
    goal_id = int(parts[2])

    if action == "g" and len(parts) <= 3:
        goal = await uow.goals.get_by_id(goal_id)
        pet_name = goal.pet_name if goal else "pet"
        if callback.message:
            await callback.message.reply(
                f"🍽 How much would you like to feed <b>{pet_name}</b>?\n\nType a number (e.g. <code>10</code> or <code>$10</code>)."
            )
        return

    amount_cents = int(parts[3]) if action == "g" and len(parts) > 3 else 0

    occurred_at = callback.message.date.astimezone(UTC) if callback.message else datetime.now(UTC)

    res = await feed_goal(
        uow=uow,
        user_id=user.id,
        goal_id=goal_id,
        amount_cents=amount_cents,
        occurred_at=occurred_at,
        source_update_id=callback.message.message_id if callback.message else None,
    )
    await callback.answer()

    if not res.success:
        err_text = get_text(
            f"feed_err_{res.error_code}",
            user.variant,
            status=res.goal.status if res.goal else "unknown",
            pet_name=res.goal.pet_name if res.goal else "pet",
        )
        if callback.message:
            await callback.message.edit_text(err_text)
        return

    reply = _format_feeding_reply(res, user.variant, user.timezone)
    if callback.message:
        await callback.message.edit_text(reply)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_bare_number_shortcut(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    """Handle bare amount messages (e.g. '10', '$10', '50000', '50 rb') as shortcut for feeding."""
    text = (message.text or "").strip()

    # If user is in an active wizard conversation, let wizard router handle it
    conv = await uow.conversations.get(user.id)
    if conv:
        return

    amount_cents = parse_amount_to_cents(text)
    if amount_cents is None:
        return  # Not an amount, ignore

    active_goals = await uow.goals.list_active_by_user(user.id)
    if not active_goals:
        return  # No active goal, ignore

    if len(active_goals) == 1:
        goal = active_goals[0]
        res = await feed_goal(
            uow=uow,
            user_id=user.id,
            goal_id=goal.id,
            amount_cents=amount_cents,
            occurred_at=message.date.astimezone(UTC),
            source_update_id=message.message_id,
        )
        if not res.success:
            err_text = get_text(
                f"feed_err_{res.error_code}",
                user.variant,
                status=res.goal.status if res.goal else "unknown",
                pet_name=goal.pet_name,
            )
            await message.answer(err_text)
            return

        reply = _format_feeding_reply(res, user.variant, user.timezone)
        await message.answer(reply)
    else:
        # Multiple goals -> show pet picker
        goals_tuples = [(g.id, g.pet_name, g.name) for g in active_goals]
        kb = pet_picker_keyboard(goals_tuples, amount_cents)
        await message.answer(get_text("feed_pick_pet", user.variant), reply_markup=kb)
