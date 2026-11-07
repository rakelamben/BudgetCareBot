from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from budgetcare.bot.callbacks import (
    CB_CONFIRM_NO,
    CB_CONFIRM_OK,
    CB_FREQ_DAILY,
    CB_FREQ_MONTHLY,
    CB_FREQ_WEEKLY,
    CB_NOTIF_OFF,
    CB_NOTIF_ON,
    cb_dom,
    cb_weekday,
)
from budgetcare.domain.models import GoalFrequency, OfferedFrequency
from budgetcare.domain.money import format_cents


def location_keyboard() -> ReplyKeyboardMarkup:
    btn = KeyboardButton(text="📍 Share Location", request_location=True)
    return ReplyKeyboardMarkup(
        keyboard=[[btn]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_reply_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def frequency_keyboard(offered: list[OfferedFrequency]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in offered:
        freq = item.frequency
        plan = item.plan
        nominal_str = format_cents(plan.nominal_cents)
        feedings_str = f"{plan.total_feedings}x {nominal_str}"

        if freq == GoalFrequency.DAILY:
            label = f"📅 Daily: {feedings_str}"
            cb = CB_FREQ_DAILY
        elif freq == GoalFrequency.WEEKLY:
            label = f"🗓 Weekly: {feedings_str}"
            cb = CB_FREQ_WEEKLY
        else:
            label = f"📆 Monthly: {feedings_str}"
            cb = CB_FREQ_MONTHLY

        rows.append([InlineKeyboardButton(text=label, callback_data=cb)])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def notifications_toggle_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 On", callback_data=CB_NOTIF_ON),
                InlineKeyboardButton(text="🔕 Off", callback_data=CB_NOTIF_OFF),
            ]
        ]
    )


def weekday_keyboard() -> InlineKeyboardMarkup:
    days = [
        ("Mon", 0),
        ("Tue", 1),
        ("Wed", 2),
        ("Thu", 3),
        ("Fri", 4),
        ("Sat", 5),
        ("Sun", 6),
    ]
    row1 = [InlineKeyboardButton(text=d[0], callback_data=cb_weekday(d[1])) for d in days[:4]]
    row2 = [InlineKeyboardButton(text=d[0], callback_data=cb_weekday(d[1])) for d in days[4:]]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


def dom_keyboard() -> InlineKeyboardMarkup:
    # 4 rows of 7 dates (1-28) + last date
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for day in range(1, 29):
        current_row.append(InlineKeyboardButton(text=str(day), callback_data=cb_dom(day)))
        if len(current_row) == 7:
            rows.append(current_row)
            current_row = []

    rows.append([InlineKeyboardButton(text="Last Date of Month", callback_data=cb_dom("last"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data=CB_CONFIRM_OK),
                InlineKeyboardButton(text="❌ Cancel", callback_data=CB_CONFIRM_NO),
            ]
        ]
    )


def pet_picker_keyboard(
    goals: list[tuple[int, str, str]], amount_cents: int
) -> InlineKeyboardMarkup:
    """Build keyboard for choosing which goal/pet to feed when user has multiple active goals.

    goals: list of (goal_id, pet_name, goal_name)
    """
    rows: list[list[InlineKeyboardButton]] = []
    for g_id, pet_name, _ in goals:
        label = f"🐾 Feed {pet_name}"
        cb = f"fd:g:{g_id}:{amount_cents}"
        rows.append([InlineKeyboardButton(text=label, callback_data=cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pet_free_food_picker_keyboard(goals: list[tuple[int, str, str]]) -> InlineKeyboardMarkup:
    """Build keyboard for choosing which pet gets free food."""
    rows: list[list[InlineKeyboardButton]] = []
    for g_id, pet_name, _ in goals:
        label = f"🥣 Free Food for {pet_name}"
        cb = f"fd:ff:{g_id}"
        rows.append([InlineKeyboardButton(text=label, callback_data=cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def undo_confirm_keyboard(entry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ Yes, Undo", callback_data=f"un:ok:{entry_id}"),
                InlineKeyboardButton(text="❌ Keep It", callback_data="un:no"),
            ]
        ]
    )


def digest_notification_keyboard(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """Build keyboard for digest notifications: up to 8 pets with Feed and Free food buttons.

    items: list of (goal_id, pet_name)
    """
    rows: list[list[InlineKeyboardButton]] = []
    for g_id, pet_name in items[:8]:
        rows.append(
            [
                InlineKeyboardButton(text=f"🐾 Feed {pet_name}", callback_data=f"fd:g:{g_id}"),
                InlineKeyboardButton(text="🥣 Free Food", callback_data=f"fd:ff:{g_id}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def single_notification_keyboard(goal_id: int, pet_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"🐾 Feed {pet_name}", callback_data=f"fd:g:{goal_id}"),
                InlineKeyboardButton(text="🥣 Free Food", callback_data=f"fd:ff:{goal_id}"),
            ]
        ]
    )


def delete_picker_keyboard(goals: list[tuple[int, str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for g_id, pet_name, name in goals:
        rows.append([InlineKeyboardButton(text=f"🗑 {pet_name} ({name})", callback_data=f"dl:g:{g_id}")])
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="dl:no")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Delete Forever", callback_data=f"dl:ok:{goal_id}"),
                InlineKeyboardButton(text="❌ Keep It", callback_data="dl:no"),
            ]
        ]
    )


def settings_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Goal Notifications", callback_data="st:notif")],
            [InlineKeyboardButton(text="📍 Change Timezone", callback_data="st:tz")],
            [InlineKeyboardButton(text="⚠️ Delete All My Data", callback_data="st:wipe")],
        ]
    )


def settings_goals_picker_keyboard(goals: list[tuple[int, str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for g_id, pet_name, name in goals:
        rows.append([InlineKeyboardButton(text=f"🐾 {pet_name} ({name})", callback_data=f"st:g:{g_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="st:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_goal_detail_keyboard(
    goal_id: int, notifications_enabled: bool, frequency: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    toggle_text = "🔕 Turn Off Notifications" if notifications_enabled else "🔔 Turn On Notifications"
    toggle_val = "0" if notifications_enabled else "1"
    rows.append([InlineKeyboardButton(text=toggle_text, callback_data=f"st:n:{goal_id}:{toggle_val}")])

    if notifications_enabled:
        if frequency == "weekly":
            rows.append([InlineKeyboardButton(text="📅 Change Reminder Day", callback_data=f"st:w:{goal_id}")])
        elif frequency == "monthly":
            rows.append([InlineKeyboardButton(text="📅 Change Reminder Date", callback_data=f"st:d:{goal_id}")])

    rows.append([InlineKeyboardButton(text="⬅️ Back to Goals", callback_data="st:notif")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wipe_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚠️ Yes, Proceed to Wipe", callback_data="st:wipe_ok"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="st:main"),
            ]
        ]
    )
