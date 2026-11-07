from datetime import UTC, datetime
from typing import Any

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message

from budgetcare.bot.copy import get_text
from budgetcare.bot.keyboards import (
    confirm_keyboard,
    dom_keyboard,
    frequency_keyboard,
    location_keyboard,
    notifications_toggle_keyboard,
    weekday_keyboard,
)
from budgetcare.bot.parsing import parse_amount
from budgetcare.config import settings
from budgetcare.db.tables import UserTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.domain.models import GoalFrequency
from budgetcare.domain.money import format_cents
from budgetcare.domain.pets import SPECIES_EMOJI, pick_pet
from budgetcare.domain.schedule import offered_frequencies, plan_schedule
from budgetcare.domain.timeutil import get_user_tz
from budgetcare.services.goals import create_goal_from_wizard

router = Router(name="newgoal")


class InNewGoalWizardFilter(BaseFilter):
    """Filter that matches only if user is actively in the newgoal conversation flow."""

    async def __call__(
        self,
        message: Message,
        user: UserTable | None = None,
        uow: UnitOfWork | None = None,
        **kwargs: Any,
    ) -> bool:
        if not user or not uow:
            return False
        conv = await uow.conversations.get(user.id)
        return bool(conv and conv.flow == "newgoal")


@router.message(Command("newgoal"))
async def handle_newgoal(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    if not user.timezone:
        await uow.conversations.set_state(
            user_id=user.id,
            flow="tz",
            step="ask_location",
            data={},
        )
        await message.answer(
            text=get_text("err_no_tz", user.variant)
            + "\n\n"
            + get_text("ask_location", user.variant),
            reply_markup=location_keyboard(),
            parse_mode="HTML",
        )
        return

    # Check active goals count limit
    active_count = await uow.goals.count_active_by_user(user.id)
    if active_count >= settings.MAX_ACTIVE_GOALS_PER_USER:
        await message.answer(
            text=f"⚠️ You already have {active_count} active goals (maximum limit reached).",
            parse_mode="HTML",
        )
        return

    await uow.conversations.set_state(
        user_id=user.id,
        flow="newgoal",
        step="name",
        data={},
    )
    await message.answer(
        text=get_text("ask_name", user.variant),
        parse_mode="HTML",
    )


@router.message(F.text, ~F.text.startswith("/"), InNewGoalWizardFilter())
async def handle_newgoal_text_steps(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    conv = await uow.conversations.get(user.id)
    if not conv or conv.flow != "newgoal":
        return

    text = message.text.strip() if message.text else ""
    data = dict(conv.data)

    # Step 1: Goal Name
    if conv.step == "name":
        if len(text) < 1 or len(text) > 60 or text.startswith("/"):
            await message.answer(get_text("err_name_len", user.variant), parse_mode="HTML")
            return
        data["name"] = text
        await uow.conversations.set_state(user.id, "newgoal", "budget", data)
        await message.answer(get_text("ask_budget", user.variant), parse_mode="HTML")

    # Step 2: Target Budget
    elif conv.step == "budget":
        try:
            cents = parse_amount(text, max_cents=settings.MAX_AMOUNT_CENTS)
            if cents < 2 * settings.MIN_NOMINAL_CENTS:
                await message.answer(
                    "⚠️ Budget must be at least $2.00 to allow at least 2 feedings of $1.00.",
                    parse_mode="HTML",
                )
                return
        except ValueError as e:
            await message.answer(str(e), parse_mode="HTML")
            return

        data["target_cents"] = cents
        await uow.conversations.set_state(user.id, "newgoal", "period", data)
        await message.answer(get_text("ask_period", user.variant), parse_mode="HTML")

    # Step 3: Period Days
    elif conv.step == "period":
        try:
            days = int(text)
            if days < 2 or days > 365:
                await message.answer(get_text("err_period_range", user.variant), parse_mode="HTML")
                return
        except ValueError:
            await message.answer(get_text("err_period_range", user.variant), parse_mode="HTML")
            return

        data["period_days"] = days

        # Pick a pet avoiding user's current active pairs
        active_goals = await uow.goals.list_active_by_user(user.id)
        active_pairs = {(g.species, g.pet_name) for g in active_goals}
        species, pet_name = pick_pet(active_pairs)
        data["species"] = species
        data["pet_name"] = pet_name

        # Calculate offered frequencies
        tz = get_user_tz(user.timezone or "UTC")
        now = datetime.now(UTC)
        offered = offered_frequencies(
            created_at=now,
            tz=tz,
            period_days=days,
            target_cents=data["target_cents"],
            min_nominal_cents=settings.MIN_NOMINAL_CENTS,
        )

        if not offered:
            await message.answer(get_text("err_no_freq", user.variant), parse_mode="HTML")
            await uow.conversations.set_state(user.id, "newgoal", "budget", data)
            await message.answer(get_text("ask_budget", user.variant), parse_mode="HTML")
            return

        await uow.conversations.set_state(user.id, "newgoal", "frequency", data)

        emoji = SPECIES_EMOJI.get(species, "🐾")
        reveal_text = get_text(
            "pet_reveal",
            user.variant,
            name=data["name"],
            emoji=emoji,
            pet_name=pet_name,
            species=species.capitalize(),
        )
        await message.answer(reveal_text, parse_mode="HTML")

        pick_freq_text = get_text("pick_frequency", user.variant, pet_name=pet_name)
        await message.answer(
            pick_freq_text,
            reply_markup=frequency_keyboard(offered),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("nf:"))
async def handle_newgoal_callbacks(
    callback: CallbackQuery, user: UserTable, uow: UnitOfWork
) -> None:
    await callback.answer()
    if not callback.data:
        return

    conv = await uow.conversations.get(user.id)
    if not conv or conv.flow != "newgoal":
        await callback.message.answer(get_text("err_expired_flow", user.variant), parse_mode="HTML")  # type: ignore
        return

    data = dict(conv.data)
    parts = callback.data.split(":")
    action = parts[1]

    # Frequency Selection (nf:f:<freq>)
    if action == "f":
        freq_str = parts[2]
        data["frequency"] = freq_str
        tz = get_user_tz(user.timezone or "UTC")
        now = datetime.now(UTC)
        plan = plan_schedule(
            created_at=now,
            tz=tz,
            period_days=data["period_days"],
            frequency=GoalFrequency(freq_str),
            target_cents=data["target_cents"],
        )
        if not plan:
            return

        penalty_pct = 100 // plan.total_feedings
        first_p = plan.periods[0]

        data["total_feedings"] = plan.total_feedings
        data["nominal_cents"] = plan.nominal_cents
        data["last_nominal_cents"] = plan.last_nominal_cents
        data["first_cutoff"] = first_p.end_date.strftime("%a, %d %b %Y")

        await uow.conversations.set_state(user.id, "newgoal", "notifications", data)

        summary_text = get_text(
            "schedule_summary",
            user.variant,
            pet_name=data["pet_name"],
            total_feedings=plan.total_feedings,
            nominal=format_cents(plan.nominal_cents),
            last_nominal=format_cents(plan.last_nominal_cents),
            first_cutoff=data["first_cutoff"],
            penalty=penalty_pct,
        )
        await callback.message.edit_text(  # type: ignore
            text=summary_text,
            reply_markup=notifications_toggle_keyboard(),
            parse_mode="HTML",
        )

    # Notifications Toggle (nf:n:<0|1>)
    elif action == "n":
        enabled = parts[2] == "1"
        data["notifications_enabled"] = enabled
        freq = data.get("frequency")

        if not enabled or freq == "daily":
            # Jump straight to confirmation
            await _show_confirmation(callback, user, uow, data)
        elif freq == "weekly":
            await uow.conversations.set_state(user.id, "newgoal", "reminder_pick", data)
            await callback.message.edit_text(  # type: ignore
                text=get_text("pick_weekday", user.variant),
                reply_markup=weekday_keyboard(),
                parse_mode="HTML",
            )
        elif freq == "monthly":
            await uow.conversations.set_state(user.id, "newgoal", "reminder_pick", data)
            await callback.message.edit_text(  # type: ignore
                text=get_text("pick_dom", user.variant),
                reply_markup=dom_keyboard(),
                parse_mode="HTML",
            )

    # Weekday Pick (nf:w:<wd>)
    elif action == "w":
        data["reminder_weekday"] = int(parts[2])
        await _show_confirmation(callback, user, uow, data)

    # Date of Month Pick (nf:d:<dom>)
    elif action == "d":
        dom_val = parts[2]
        if dom_val == "last":
            data["reminder_on_last"] = True
        else:
            data["reminder_dom"] = int(dom_val)
        await _show_confirmation(callback, user, uow, data)

    # Cancel (nf:no)
    elif action == "no":
        await uow.conversations.delete(user.id)
        await callback.message.edit_text(  # type: ignore
            text=get_text("cancelled", user.variant),
            parse_mode="HTML",
        )

    # Confirm (nf:ok)
    elif action == "ok":
        now = datetime.now(UTC)
        try:
            goal = await create_goal_from_wizard(uow, user, data, now)
        except Exception as e:  # noqa: BLE001
            await callback.message.answer(f"⚠️ Error creating goal: {e}")  # type: ignore
            return

        emoji = SPECIES_EMOJI.get(goal.species, "🐾")
        success_text = get_text(
            "goal_created",
            user.variant,
            emoji=emoji,
            pet_name=goal.pet_name,
        )
        await callback.message.edit_text(text=success_text, parse_mode="HTML")  # type: ignore


async def _show_confirmation(
    callback: CallbackQuery,
    user: UserTable,
    uow: UnitOfWork,
    data: dict,
) -> None:
    await uow.conversations.set_state(user.id, "newgoal", "confirm", data)
    emoji = SPECIES_EMOJI.get(data["species"], "🐾")
    notif_label = "On" if data.get("notifications_enabled", True) else "Off"
    freq_label = str(data.get("frequency", "")).capitalize()

    text = get_text(
        "confirm_goal",
        user.variant,
        name=data["name"],
        emoji=emoji,
        pet_name=data["pet_name"],
        species=data["species"].capitalize(),
        target=format_cents(data["target_cents"]),
        period_days=data["period_days"],
        frequency=freq_label,
        total_feedings=data.get("total_feedings", 0),
        nominal=format_cents(data.get("nominal_cents", 0)),
        first_cutoff=data.get("first_cutoff", ""),
        notifs=notif_label,
    )
    await callback.message.edit_text(  # type: ignore
        text=text,
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )
