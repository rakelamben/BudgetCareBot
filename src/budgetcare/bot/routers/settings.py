from typing import Any

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from budgetcare.bot.copy import get_text
from budgetcare.bot.keyboards import (
    location_keyboard,
    settings_goal_detail_keyboard,
    settings_goals_picker_keyboard,
    settings_main_keyboard,
    wipe_confirm_keyboard,
)
from budgetcare.db.tables import UserTable
from budgetcare.db.uow import UnitOfWork
from budgetcare.services.settings import (
    toggle_goal_notifications,
    update_goal_reminder_time,
    wipe_all_user_data,
)

router = Router(name="settings")

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class InWipeFlowFilter(BaseFilter):
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
        return bool(conv and conv.flow == "wipe")


def settings_weekday_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    rows = []
    for idx, day in enumerate(WEEKDAYS):
        rows.append([InlineKeyboardButton(text=day, callback_data=f"st:sw:{goal_id}:{idx}")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=f"st:g:{goal_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_dom_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    rows = []
    for row in range(0, 28, 7):
        btns = [
            InlineKeyboardButton(text=str(d), callback_data=f"st:sd:{goal_id}:{d}")
            for d in range(row + 1, row + 8)
        ]
        rows.append(btns)
    rows.append(
        [
            InlineKeyboardButton(text="Last Date of Month", callback_data=f"st:sd:{goal_id}:last"),
            InlineKeyboardButton(text="⬅️ Back", callback_data=f"st:g:{goal_id}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
async def handle_settings_command(message: Message, user: UserTable) -> None:
    await message.answer(
        get_text("settings_main", user.variant),
        reply_markup=settings_main_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("st:"))
async def handle_settings_callbacks(
    callback: CallbackQuery, user: UserTable, uow: UnitOfWork
) -> None:
    data = callback.data or ""
    parts = data.split(":")
    action = parts[1]

    if action == "main":
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                get_text("settings_main", user.variant),
                reply_markup=settings_main_keyboard(),
                parse_mode="HTML",
            )
        return

    if action == "notif":
        active_goals = await uow.goals.list_active_by_user(user.id)
        if not active_goals:
            await callback.answer("No active goals found.", show_alert=True)
            return

        goals_tuples = [(g.id, g.pet_name, g.name) for g in active_goals]
        if callback.message:
            await callback.message.edit_text(
                get_text("settings_goals_pick", user.variant),
                reply_markup=settings_goals_picker_keyboard(goals_tuples),
                parse_mode="HTML",
            )
        await callback.answer()

    elif action == "g":
        goal_id = int(parts[2])
        goal = await uow.goals.get_by_id(goal_id)
        if not goal or goal.user_id != user.id:
            await callback.answer("Goal not found.", show_alert=True)
            return

        status_text = "Enabled ✅" if goal.notifications_enabled else "Disabled ❌"
        reminder_info = "None"
        if goal.notifications_enabled:
            if goal.frequency == "daily":
                reminder_info = "10:00 every day"
            elif goal.frequency == "weekly":
                day_name = (
                    WEEKDAYS[goal.reminder_weekday]
                    if goal.reminder_weekday is not None
                    else "Sunday"
                )
                reminder_info = f"10:00 every {day_name}"
            elif goal.frequency == "monthly":
                dom = "Last date" if goal.reminder_on_last else f"Day {goal.reminder_dom or 1}"
                reminder_info = f"10:00 on {dom}"

        text = get_text(
            "settings_goal_detail",
            user.variant,
            name=goal.name,
            pet_name=goal.pet_name,
            status=status_text,
            frequency=goal.frequency.capitalize(),
            reminder_info=reminder_info,
        )
        if callback.message:
            await callback.message.edit_text(
                text,
                reply_markup=settings_goal_detail_keyboard(
                    goal.id, goal.notifications_enabled, goal.frequency
                ),
                parse_mode="HTML",
            )
        await callback.answer()

    elif action == "n":
        goal_id = int(parts[2])
        new_val = parts[3] == "1"
        await toggle_goal_notifications(uow, goal_id, new_val)
        await callback.answer(get_text("settings_notif_updated", user.variant))

        # Re-render detail
        goal = await uow.goals.get_by_id(goal_id)
        if goal and callback.message:
            status_text = "Enabled ✅" if goal.notifications_enabled else "Disabled ❌"
            text = get_text(
                "settings_goal_detail",
                user.variant,
                name=goal.name,
                pet_name=goal.pet_name,
                status=status_text,
                frequency=goal.frequency.capitalize(),
                reminder_info="Configured" if new_val else "Disabled",
            )
            await callback.message.edit_text(
                text,
                reply_markup=settings_goal_detail_keyboard(
                    goal.id, goal.notifications_enabled, goal.frequency
                ),
                parse_mode="HTML",
            )

    elif action == "w":
        goal_id = int(parts[2])
        if callback.message:
            await callback.message.edit_text(
                "📅 Select reminder day of the week:",
                reply_markup=settings_weekday_keyboard(goal_id),
                parse_mode="HTML",
            )
        await callback.answer()

    elif action == "d":
        goal_id = int(parts[2])
        if callback.message:
            await callback.message.edit_text(
                "📅 Select reminder date of the month:",
                reply_markup=settings_dom_keyboard(goal_id),
                parse_mode="HTML",
            )
        await callback.answer()

    elif action == "sw":
        goal_id = int(parts[2])
        weekday = int(parts[3])
        await update_goal_reminder_time(uow, goal_id, reminder_weekday=weekday)
        await callback.answer(get_text("settings_notif_updated", user.variant))
        # Re-render detail
        goal = await uow.goals.get_by_id(goal_id)
        if goal and callback.message:
            text = get_text(
                "settings_goal_detail",
                user.variant,
                name=goal.name,
                pet_name=goal.pet_name,
                status="Enabled ✅",
                frequency=goal.frequency.capitalize(),
                reminder_info=f"10:00 every {WEEKDAYS[weekday]}",
            )
            await callback.message.edit_text(
                text,
                reply_markup=settings_goal_detail_keyboard(
                    goal.id, goal.notifications_enabled, goal.frequency
                ),
                parse_mode="HTML",
            )

    elif action == "sd":
        goal_id = int(parts[2])
        val = parts[3]
        if val == "last":
            await update_goal_reminder_time(
                uow, goal_id, reminder_dom=None, reminder_on_last=True
            )
            dom_text = "Last date"
        else:
            dom = int(val)
            await update_goal_reminder_time(
                uow, goal_id, reminder_dom=dom, reminder_on_last=False
            )
            dom_text = f"Day {dom}"

        await callback.answer(get_text("settings_notif_updated", user.variant))
        goal = await uow.goals.get_by_id(goal_id)
        if goal and callback.message:
            text = get_text(
                "settings_goal_detail",
                user.variant,
                name=goal.name,
                pet_name=goal.pet_name,
                status="Enabled ✅",
                frequency=goal.frequency.capitalize(),
                reminder_info=f"10:00 on {dom_text}",
            )
            await callback.message.edit_text(
                text,
                reply_markup=settings_goal_detail_keyboard(
                    goal.id, goal.notifications_enabled, goal.frequency
                ),
                parse_mode="HTML",
            )

    elif action == "tz":
        await uow.conversations.set_state(
            user_id=user.id,
            flow="tz",
            step="ask_location",
            data={},
        )
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                get_text("ask_location", user.variant),
                reply_markup=location_keyboard(),
                parse_mode="HTML",
            )

    elif action == "wipe":
        if callback.message:
            await callback.message.edit_text(
                get_text("settings_wipe_prompt", user.variant),
                reply_markup=wipe_confirm_keyboard(),
                parse_mode="HTML",
            )
        await callback.answer()

    elif action == "wipe_ok":
        await uow.conversations.set_state(
            user_id=user.id,
            flow="wipe",
            step="confirm_text",
            data={},
        )
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                get_text("settings_wipe_confirm_text", user.variant),
                parse_mode="HTML",
            )


@router.message(F.text, InWipeFlowFilter())
async def handle_wipe_text_confirmation(
    message: Message, user: UserTable, uow: UnitOfWork
) -> None:
    text = (message.text or "").strip()
    if text == "DELETE":
        await wipe_all_user_data(uow, user.id)
        await message.answer(
            get_text("settings_wipe_success", user.variant),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "⚠️ Please type <code>DELETE</code> in all caps to confirm data wipe, or /cancel to abort.",
            parse_mode="HTML",
        )
