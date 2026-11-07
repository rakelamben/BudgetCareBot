from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from budgetcare.bot.copy import get_text
from budgetcare.db.tables import UserTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.domain.money import format_cents
from budgetcare.domain.pets import SPECIES_EMOJI
from budgetcare.domain.scoring import (
    calculate_condition,
    calculate_live_service_quality,
    calculate_mood_tier,
)
from budgetcare.domain.timeutil import get_user_tz

router = Router(name="goals")

MOOD_EMOJIS = {
    4: "😄",
    3: "🙂",
    2: "😐",
    1: "🥺",
}


@router.message(Command("goals"))
async def handle_goals_command(message: Message, user: UserTable, uow: UnitOfWork) -> None:
    active_goals = await uow.goals.list_active_by_user(user.id)
    archived_goals = await uow.goals.list_archived_by_user(user.id)

    if not active_goals and not archived_goals:
        await message.answer(get_text("err_no_goal", user.variant))
        return

    tz = get_user_tz(user.timezone)
    now = datetime.now(UTC)
    today_local = now.astimezone(tz).date()

    lines: list[str] = []

    if active_goals:
        lines.append("🐾 <b>Active Savings Goals:</b>\n")

        for g in active_goals:
            periods = await uow.periods.list_by_goal(g.id)
            entries = await uow.entries.list_by_goal(g.id)

            deposited = sum(e.amount_cents for e in entries if e.undone_at is None)
            missed = sum(1 for p in periods if p.status == "missed")
            condition = calculate_condition(missed, g.total_feedings)
            mood_tier = calculate_mood_tier(missed, g.total_feedings)
            mood_emoji = MOOD_EMOJIS.get(mood_tier.value, "🐾")
            pet_emoji = SPECIES_EMOJI.get(g.species.lower(), "🐾")

            days_elapsed = max(0, min(g.period_days, (today_local - g.start_date).days))
            live_quality = calculate_live_service_quality(
                deposited_cents=deposited,
                target_cents=g.target_cents,
                days_elapsed=days_elapsed,
                period_days=g.period_days,
            )
            quality_pct = round(live_quality * 100)

            # Check current open period
            open_period = next((p for p in periods if p.status == "open"), None)
            if open_period:
                has_fed = any(
                    e.period_idx == open_period.idx and e.is_feeding and e.undone_at is None
                    for e in entries
                )
                feed_status = "Fed today ✅" if has_fed else "Hungry today 🥣"
                cutoff_str = open_period.cutoff_at.astimezone(tz).strftime("%a, %d %b %H:%M")
            else:
                feed_status = "Awaiting tick ⏳"
                cutoff_str = "Finalized"

            progress_pct = (
                min(100, (deposited * 100) // g.target_cents) if g.target_cents > 0 else 100
            )

            lines.append(
                f"• {pet_emoji} <b>{g.pet_name}</b> ({g.species.capitalize()}) — <i>{g.name}</i>\n"
                f"  💰 Saved: <b>{format_cents(deposited)}</b> / {format_cents(g.target_cents)} ({progress_pct}%)\n"
                f"  ❤️ Condition: <b>{condition}%</b> ({mood_emoji})\n"
                f"  ⭐ Live Quality: <b>{quality_pct}%</b>\n"
                f"  🕒 Status: {feed_status}\n"
                f"  ⏰ Next cut-off: {cutoff_str}\n"
            )

    if archived_goals:
        lines.append("🏆 <b>Completed / Archived Goals:</b>\n")
        for ag in archived_goals:
            res_data = ag.result or {}
            title = res_data.get("title", ag.status.capitalize())
            saved_str = format_cents(res_data.get("deposited_cents", ag.target_cents))
            pet_emoji = SPECIES_EMOJI.get(ag.species.lower(), "🐾")
            lines.append(
                f"• {pet_emoji} <b>{ag.pet_name}</b> ({ag.name}): "
                f"<b>{ag.status.capitalize()}</b> — <i>{title}</i> ({saved_str})\n"
            )

    buttons = []
    for g in active_goals:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🐾 Details: {g.pet_name}",
                    callback_data=f"gl:v:{g.id}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="➕ New Goal", callback_data="btn_newgoal")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("\n".join(lines), reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith("gl:"))
async def handle_goal_details_callback(
    callback: CallbackQuery, user: UserTable, uow: UnitOfWork
) -> None:
    data = callback.data or ""
    parts = data.split(":")
    action = parts[1]

    if action == "v":
        goal_id = int(parts[2])
        goal = await uow.goals.get_by_id(goal_id)
        if not goal or goal.user_id != user.id:
            await callback.answer("Goal not found.", show_alert=True)
            return

        periods = await uow.periods.list_by_goal(goal.id)
        entries = await uow.entries.list_by_goal(goal.id)

        deposited = sum(e.amount_cents for e in entries if e.undone_at is None)
        missed = sum(1 for p in periods if p.status == "missed")
        condition = calculate_condition(missed, goal.total_feedings)
        mood_tier = calculate_mood_tier(missed, goal.total_feedings)
        mood_emoji = MOOD_EMOJIS.get(mood_tier.value, "🐾")
        pet_emoji = SPECIES_EMOJI.get(goal.species.lower(), "🐾")

        tz = get_user_tz(user.timezone)
        now = datetime.now(UTC)
        today_local = now.astimezone(tz).date()
        days_elapsed = max(0, min(goal.period_days, (today_local - goal.start_date).days))
        live_quality = calculate_live_service_quality(
            deposited_cents=deposited,
            target_cents=goal.target_cents,
            days_elapsed=days_elapsed,
            period_days=goal.period_days,
        )
        quality_pct = round(live_quality * 100)

        open_periods = [p for p in periods if p.status == "open"]
        feedings_remaining = len(open_periods)
        next_cutoff = (
            open_periods[0].cutoff_at.astimezone(tz).strftime("%a, %d %b %H:%M")
            if open_periods
            else "Completed"
        )
        progress_pct = (
            min(100, (deposited * 100) // goal.target_cents) if goal.target_cents > 0 else 100
        )

        detail_text = (
            f"{pet_emoji} <b>Companion: {goal.pet_name}</b> ({goal.species.capitalize()})\n"
            f"🎯 Goal: <b>{goal.name}</b>\n\n"
            f"• Saved: <b>{format_cents(deposited)}</b> / {format_cents(goal.target_cents)} ({progress_pct}%)\n"
            f"• Condition: <b>{condition}%</b> ({mood_emoji})\n"
            f"• Live Quality: <b>{quality_pct}%</b>\n"
            f"• Feedings remaining: <b>{feedings_remaining}</b> of {goal.total_feedings}\n"
            f"• Next cut-off: <b>{next_cutoff}</b> (23:59 local)\n"
            f"• Nominal per feeding: ~<b>{format_cents(goal.nominal_cents)}</b>\n"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🍽 Feed {goal.pet_name}", callback_data=f"fd:g:{goal.id}"
                    ),
                    InlineKeyboardButton(
                        text="🥣 Free Food", callback_data=f"fd:ff:{goal.id}"
                    ),
                ],
                [InlineKeyboardButton(text="⬅️ Back to Goals", callback_data="gl:list")],
            ]
        )
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(detail_text, reply_markup=kb, parse_mode="HTML")

    elif action == "list":
        await callback.answer()
        if callback.message:
            # Re-render /goals view
            active_goals = await uow.goals.list_active_by_user(user.id)
            archived_goals = await uow.goals.list_archived_by_user(user.id)
            tz = get_user_tz(user.timezone)
            now = datetime.now(UTC)
            today_local = now.astimezone(tz).date()

            lines = ["🐾 <b>Active Savings Goals:</b>\n"]
            for g in active_goals:
                periods = await uow.periods.list_by_goal(g.id)
                entries = await uow.entries.list_by_goal(g.id)
                deposited = sum(e.amount_cents for e in entries if e.undone_at is None)
                missed = sum(1 for p in periods if p.status == "missed")
                condition = calculate_condition(missed, g.total_feedings)
                mood_tier = calculate_mood_tier(missed, g.total_feedings)
                mood_emoji = MOOD_EMOJIS.get(mood_tier.value, "🐾")
                pet_emoji = SPECIES_EMOJI.get(g.species.lower(), "🐾")

                open_period = next((p for p in periods if p.status == "open"), None)
                if open_period:
                    has_fed = any(
                        e.period_idx == open_period.idx and e.is_feeding and e.undone_at is None
                        for e in entries
                    )
                    feed_status = "Fed today ✅" if has_fed else "Hungry today 🥣"
                    cutoff_str = open_period.cutoff_at.astimezone(tz).strftime("%a, %d %b %H:%M")
                else:
                    feed_status = "Awaiting tick ⏳"
                    cutoff_str = "Finalized"

                lines.append(
                    f"• {pet_emoji} <b>{g.pet_name}</b> ({g.species.capitalize()}) — <i>{g.name}</i>\n"
                    f"  💰 Saved: <b>{format_cents(deposited)}</b> / {format_cents(g.target_cents)}\n"
                    f"  ❤️ Condition: <b>{condition}%</b> ({mood_emoji})\n"
                    f"  🕒 Status: {feed_status}\n"
                    f"  ⏰ Next cut-off: {cutoff_str}\n"
                )

            if archived_goals:
                lines.append("🏆 <b>Completed / Archived Goals:</b>\n")
                for ag in archived_goals:
                    res_data = ag.result or {}
                    title = res_data.get("title", ag.status.capitalize())
                    saved_str = format_cents(res_data.get("deposited_cents", ag.target_cents))
                    pet_emoji = SPECIES_EMOJI.get(ag.species.lower(), "🐾")
                    lines.append(
                        f"• {pet_emoji} <b>{ag.pet_name}</b> ({ag.name}): "
                        f"<b>{ag.status.capitalize()}</b> — <i>{title}</i> ({saved_str})\n"
                    )

            buttons = [
                [InlineKeyboardButton(text=f"🐾 Details: {g.pet_name}", callback_data=f"gl:v:{g.id}")]
                for g in active_goals
            ]
            buttons.append([InlineKeyboardButton(text="➕ New Goal", callback_data="btn_newgoal")])
            await callback.message.edit_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML",
            )
