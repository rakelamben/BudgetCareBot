import html

COPY: dict[str, dict[str, str]] = {
    "pet": {
        "welcome": (
            "👋 Welcome to <b>Budget Care</b>!\n\n"
            "I help you reach your short-term savings goals by turning each goal into a virtual pet "
            "that you care for by saving consistently.\n\n"
            "Type /newgoal to create your first savings goal!"
        ),
        "ask_location": (
            "📍 To set up your schedule and feeding cut-offs at 23:59 your local time, "
            "please share your location.\n\n"
            "<i>Your coordinates are used once to detect your timezone and are never stored.</i>"
        ),
        "tz_saved": "✅ Timezone set to <b>{tz}</b>. You're ready to create a goal!",
        "ask_name": "🎯 What are you saving for? (e.g. <i>Trip to Lombok</i>, <i>New Laptop</i>)",
        "ask_budget": "💰 What is your target budget in dollars? (e.g. <code>70</code> or <code>70.50</code>)",
        "ask_period": "📅 Over how many days do you want to save? (Enter a whole number between <b>2</b> and <b>365</b> days)",
        "pet_reveal": (
            "✨ Meet your new savings companion: {emoji} <b>{pet_name} the {species}</b>!\n\n"
            "Every deposit you save will be 'feeding' {pet_name}. Keep {pet_name} well-fed to stay on track!"
        ),
        "pick_frequency": "⏰ How often do you want to feed {pet_name}?",
        "schedule_summary": (
            "📋 <b>Schedule for {pet_name}</b>:\n"
            "• Total feedings: <b>{total_feedings}</b>\n"
            "• Nominal per feeding: <b>{nominal}</b> (last feeding: {last_nominal})\n"
            "• First feeding due: <b>{first_cutoff}</b> (23:59 local)\n"
            "• Missed feeding penalty: -<b>{penalty}%</b> condition\n\n"
            "Would you like reminders when {pet_name} is hungry?"
        ),
        "ask_notifications": "🔔 Do you want hunger notifications?",
        "pick_weekday": "📅 Which day of the week would you like your weekly reminder?",
        "pick_dom": "📅 Which date of the month would you like your reminder?",
        "confirm_goal": (
            "🔎 <b>Confirm Your Goal</b>:\n\n"
            "• Goal: <b>{name}</b>\n"
            "• Companion: {emoji} <b>{pet_name}</b> ({species})\n"
            "• Target: <b>{target}</b> over <b>{period_days} days</b>\n"
            "• Rhythm: <b>{frequency}</b> ({total_feedings} feedings of ~{nominal})\n"
            "• First cut-off: <b>{first_cutoff}</b>\n"
            "• Notifications: <b>{notifs}</b>\n\n"
            "Ready to begin?"
        ),
        "goal_created": (
            "🎉 <b>Goal started!</b>\n\n"
            "{emoji} <b>{pet_name}</b> is ready for your care! You can feed your pet right away today, or anytime before the first cut-off tomorrow night (23:59).\n\n"
            "• Type a number (e.g. <code>10</code> or <code>$10</code>) to feed\n"
            "• Or use /feed to give free food ($0) / view options\n"
            "• View progress anytime with /goals"
        ),
        "cancelled": "❌ Action cancelled. Type /newgoal to start over.",
        "help": (
            "🐾 <b>Budget Care Help</b>\n\n"
            "<b>Commands:</b>\n"
            "/newgoal - Create a new savings goal\n"
            "/feed [amount] - Log a deposit or give free food ($0)\n"
            "/goals - View your active pets and completed archive\n"
            "/undo - Revert the last deposit within 24 hours\n"
            "/settings - Manage reminders, timezone, or data wipe\n"
            "/delete - Delete a savings goal\n"
            "/cancel - Cancel current flow\n\n"
            "<b>How it works:</b>\n"
            "• Each deposit is a <i>feeding</i>.\n"
            "• Missing a cut-off (23:59 local) reduces pet condition.\n"
            "• <i>Give free food ($0)</i> keeps pet condition intact on days you can't deposit, "
            "protecting your streak while reflecting in service quality.\n\n"
            "🔒 <b>Privacy Note:</b>\n"
            "We only store your Telegram ID, timezone, and savings schedule. "
            "Location coordinates are used once to detect your timezone and are never stored. "
            "You can permanently delete all your data at any time via /settings. "
            "Database backups expire per our standard cloud retention schedule."
        ),
        "feed_success": (
            "🍽 <b>{pet_name} has been fed!</b>\n\n"
            "• Deposit: <b>{amount}</b>\n"
            "• Condition: <b>{condition}%</b> ({mood_emoji})\n"
            "• Saved: <b>{deposited}</b> / {target} ({progress_pct}%)\n"
            "• Live Quality: <b>{quality}%</b>\n\n"
            "<i>Next cut-off: {next_cutoff}</i>"
        ),
        "feed_extra": (
            "💰 <b>Extra deposit saved!</b>\n\n"
            "{pet_name} was already fed for this period. <b>{amount}</b> has been added to your savings!\n\n"
            "• Saved: <b>{deposited}</b> / {target} ({progress_pct}%)\n"
            "• Live Quality: <b>{quality}%</b>"
        ),
        "feed_free_food": (
            "🥣 <b>Free food given to {pet_name}!</b>\n\n"
            "Condition stays intact at <b>{condition}%</b> ({mood_emoji})! No money was deposited ($0).\n"
            "• Live Quality: <b>{quality}%</b>\n\n"
            "<i>Remember to save when you can!</i>"
        ),
        "feed_graduated": (
            "🎓 <b>CONGRATULATIONS! {pet_name} HAS GRADUATED!</b> 🏆\n\n"
            "You reached your savings target for <b>{name}</b>!\n\n"
            "• Final Condition: <b>{final_condition}%</b>\n"
            "• Final Quality: <b>{final_quality}%</b>\n"
            "• Result: <b>{title}</b>\n"
            "• Total Saved: <b>{deposited}</b> (Surplus: {surplus})\n"
            "• Days Taken: <b>{days_taken} days</b>\n\n"
            "🌟 {pet_name} is proud of you! Use /newgoal to start your next journey."
        ),
        "feed_pick_pet": "🐾 Which pet would you like to feed?",
        "feed_err_goal_closed": "⚠️ This goal is already closed ({status}).",
        "feed_err_already_fed": "⚠️ {pet_name} has already been fed for this period! Free food cannot be used twice.",
        "feed_err_not_started": "⚠️ Day 1 hasn't started yet! Free food cannot be given before day 1.",
        "undo_prompt": (
            "↩️ <b>Undo Deposit</b>\n\n"
            "Revert your most recent entry?\n"
            "• Goal: <b>{name}</b> ({pet_name})\n"
            "• Amount: <b>{amount}</b>\n"
            "• Occurred: <b>{occurred_at}</b>\n\n"
            "<i>Reverting will adjust your saved balance and live quality.</i>"
        ),
        "undo_success": (
            "✅ <b>Deposit undone!</b>\n\n"
            "Entry of <b>{amount}</b> for {pet_name} has been cancelled.\n"
            "• Updated Saved: <b>{deposited}</b> / {target}\n"
            "• Updated Condition: <b>{condition}%</b>\n"
            "• Live Quality: <b>{quality}%</b>"
        ),
        "undo_reopened": "🔄 <b>Goal reopened!</b> Because this deposit previously graduated the goal, <b>{name}</b> is now active again.",
        "undo_err_none": "ℹ️ No eligible deposits found to undo (only deposits within the last 24 hours can be reverted).",
        "digest_title": "🔔 <b>{count} companion{s} {verb} hungry!</b>\n",
        "digest_item": "• {pet_emoji} <b>{pet_name}</b> (<i>{name}</i>): due {cutoff}, ~{nominal}",
        "notif_reminder_single": (
            "🔔 <b>{pet_name} is hungry!</b>\n\n"
            "• Goal: <b>{name}</b>\n"
            "• Due: <b>{cutoff}</b> (23:59 local)\n"
            "• Target deposit: ~<b>{nominal}</b>\n\n"
            "<i>Type an amount (e.g. <code>10</code>) or feed below!</i>"
        ),
        "notif_followup_single": (
            "⏰ <b>Reminder: {pet_name} is still waiting for food!</b>\n\n"
            "• Goal: <b>{name}</b>\n"
            "• Cut-off: <b>{cutoff}</b> (23:59 local)\n"
            "• Target deposit: ~<b>{nominal}</b>\n\n"
            "<i>Don't let {pet_name}'s condition drop!</i>"
        ),
        "notif_early_warning_single": (
            "⚠️ <b>Final call for {pet_name}!</b>\n\n"
            "The feeding period closes tomorrow at 23:59!\n"
            "• Goal: <b>{name}</b>\n"
            "• Target deposit: ~<b>{nominal}</b>"
        ),
        "notif_result_expired": (
            "🏁 <b>Goal Ended: {name}</b>\n\n"
            "{pet_emoji} <b>{pet_name}</b>'s care period has concluded.\n\n"
            "• Final Condition: <b>{final_condition}%</b>\n"
            "• Final Service Quality: <b>{final_quality}%</b>\n"
            "• Total Saved: <b>{deposited}</b> / {target}\n"
            "• Evaluation: <b>{title}</b>\n\n"
            "Thank you for caring for {pet_name}! Type /newgoal to start a new savings goal."
        ),
        "delete_pick": "🗑 Which goal would you like to delete?",
        "delete_prompt": (
            "⚠️ <b>Delete Goal: {name}</b>\n\n"
            "Are you sure you want to delete {pet_emoji} <b>{pet_name}</b>?\n"
            "All progress, deposit history, and schedules will be permanently removed."
        ),
        "delete_done": "🗑 <b>{name}</b> has been deleted. Your companion has departed.",
        "delete_cancelled": "Action cancelled. Your goal remains active.",
        "settings_main": "⚙️ <b>Settings & Preferences</b>\n\nManage your notifications, adjust timezone, or manage account data.",
        "settings_goals_pick": "🔔 Select which goal's notifications to configure:",
        "settings_goal_detail": (
            "⚙️ <b>Notification Settings: {pet_name}</b>\n\n"
            "• Goal: <b>{name}</b>\n"
            "• Notifications: <b>{status}</b>\n"
            "• Rhythm: <b>{frequency}</b>\n"
            "• Reminder: <b>{reminder_info}</b>"
        ),
        "settings_notif_updated": "✅ Notification settings updated!",
        "settings_wipe_prompt": "⚠️ <b>Delete All My Data</b>\n\nThis will permanently delete your account, all goals, and history.\n\nAre you sure you want to proceed?",
        "settings_wipe_confirm_text": "⚠️ <b>FINAL CONFIRMATION</b>\n\nTo permanently delete all your data, please type the word <code>DELETE</code>.\n\nType /cancel to abort.",
        "settings_wipe_success": "👋 All your data has been permanently deleted from Budget Care. Goodbye!",
        "err_amount": "⚠️ Invalid amount. Please enter a valid number (e.g. <code>10</code>, <code>$10</code>, <code>10.50</code>).",
        "err_name_len": "⚠️ Goal name must be between 1 and 60 characters and cannot start with '/'.",
        "err_period_range": "⚠️ Please enter a whole number of days between 2 and 365.",
        "err_no_freq": "⚠️ No valid schedule could be generated for this budget and duration. Try a longer period or a higher budget.",
        "err_no_tz": "⚠️ Please set your timezone first using /start before creating a goal.",
        "err_no_goal": "⚠️ You don't have any active goals. Type /newgoal to create one!",
        "err_expired_flow": "⚠️ This wizard session has expired. Please type /newgoal to start a new one.",
        "err_generic": "⚠️ Something went wrong on our end. Please try again.",
    },
    "plain": {
        "welcome": (
            "👋 Welcome to <b>Budget Care</b>!\n\n"
            "A lightweight savings habit tracker for near-term goals.\n"
            "Type /newgoal to start saving!"
        ),
        "ask_location": (
            "📍 To configure your schedule cut-offs at 23:59 local time, please share your location.\n\n"
            "<i>Coordinates are used only to detect your timezone and are immediately discarded.</i>"
        ),
        "tz_saved": "✅ Timezone set to <b>{tz}</b>. Ready to start!",
        "ask_name": "🎯 What are you saving for?",
        "ask_budget": "💰 What is your target budget in dollars? (e.g. <code>70</code>)",
        "ask_period": "📅 Over how many days? (2 to 365 days)",
        "pet_reveal": "✨ Goal initialized: <b>{name}</b>.",
        "pick_frequency": "⏰ Choose your deposit frequency:",
        "schedule_summary": (
            "📋 <b>Schedule Summary</b>:\n"
            "• Total deposits: <b>{total_feedings}</b>\n"
            "• Nominal per deposit: <b>{nominal}</b>\n"
            "• First due date: <b>{first_cutoff}</b> (23:59 local)\n"
        ),
        "ask_notifications": "🔔 Would you like deposit reminders?",
        "pick_weekday": "📅 Pick your reminder day of the week:",
        "pick_dom": "📅 Pick your reminder date of the month:",
        "confirm_goal": (
            "🔎 <b>Confirm Savings Goal</b>:\n\n"
            "• Goal: <b>{name}</b>\n"
            "• Target: <b>{target}</b> over <b>{period_days} days</b>\n"
            "• Frequency: <b>{frequency}</b>\n"
            "• First due: <b>{first_cutoff}</b>\n\n"
            "Confirm creation?"
        ),
        "goal_created": "🎉 <b>Goal created!</b> You can record your first deposit today, or before the first cut-off tomorrow night (23:59). Type an amount (e.g. <code>10</code>) or use /goals.",
        "cancelled": "❌ Action cancelled.",
        "help": (
            "ℹ️ <b>Budget Care Help</b>\n\n"
            "/newgoal - Create a new goal\n"
            "/feed [amount] - Log a deposit\n"
            "/goals - View goals\n"
            "/undo - Revert last deposit within 24 hours\n"
            "/settings - Preferences and data wipe\n"
            "/delete - Delete a goal\n"
            "/cancel - Cancel active action\n\n"
            "🔒 <b>Privacy Note:</b>\n"
            "We only store your Telegram ID, timezone, and savings schedule. "
            "You can permanently delete all your data at any time via /settings."
        ),
        "feed_success": (
            "✅ <b>Deposit recorded!</b>\n\n"
            "• Amount: <b>{amount}</b>\n"
            "• Streak: <b>{condition}%</b>\n"
            "• Saved: <b>{deposited}</b> / {target} ({progress_pct}%)\n"
            "• Quality: <b>{quality}%</b>\n\n"
            "<i>Next due date: {next_cutoff}</i>"
        ),
        "feed_extra": (
            "💰 <b>Extra deposit saved!</b>\n\n"
            "• Amount: <b>{amount}</b>\n"
            "• Total saved: <b>{deposited}</b> / {target} ({progress_pct}%)\n"
            "• Quality: <b>{quality}%</b>"
        ),
        "feed_free_food": (
            "🥣 <b>Check-in logged ($0)!</b>\n\n"
            "Streak maintained at <b>{condition}%</b>.\n"
            "• Quality: <b>{quality}%</b>"
        ),
        "feed_graduated": (
            "🎓 <b>GOAL COMPLETED!</b> 🏆\n\n"
            "Target reached for <b>{name}</b>!\n\n"
            "• Result: <b>{title}</b>\n"
            "• Final Quality: <b>{final_quality}%</b>\n"
            "• Total Saved: <b>{deposited}</b> (Surplus: {surplus})\n"
            "• Days Taken: <b>{days_taken} days</b>"
        ),
        "feed_pick_pet": "🎯 Select which goal to deposit into:",
        "feed_err_goal_closed": "⚠️ This goal is closed ({status}).",
        "feed_err_already_fed": "⚠️ Period already completed. Cannot log zero check-in twice.",
        "feed_err_not_started": "⚠️ Day 1 has not started yet.",
        "undo_prompt": (
            "↩️ <b>Undo Deposit</b>\n\n"
            "Revert your most recent deposit?\n"
            "• Goal: <b>{name}</b>\n"
            "• Amount: <b>{amount}</b>\n"
            "• Date: <b>{occurred_at}</b>"
        ),
        "undo_success": (
            "✅ <b>Deposit undone.</b>\n\n"
            "Entry of <b>{amount}</b> reverted.\n"
            "• Total Saved: <b>{deposited}</b> / {target}\n"
            "• Quality: <b>{quality}%</b>"
        ),
        "undo_reopened": "🔄 <b>Goal reopened!</b> Goal <b>{name}</b> is active again.",
        "undo_err_none": "ℹ️ No eligible deposits found within 24 hours.",
        "digest_title": "🔔 <b>{count} goal{s} {verb} due for deposit!</b>\n",
        "digest_item": "• <b>{name}</b>: due {cutoff}, ~{nominal}",
        "notif_reminder_single": (
            "🔔 <b>Savings reminder!</b>\n\n"
            "• Goal: <b>{name}</b>\n"
            "• Due: <b>{cutoff}</b> (23:59 local)\n"
            "• Target deposit: ~<b>{nominal}</b>"
        ),
        "notif_followup_single": (
            "⏰ <b>Follow-up reminder: deposit pending!</b>\n\n"
            "• Goal: <b>{name}</b>\n"
            "• Due: <b>{cutoff}</b> (23:59 local)\n"
            "• Target deposit: ~<b>{nominal}</b>"
        ),
        "notif_early_warning_single": (
            "⚠️ <b>Upcoming cut-off tomorrow!</b>\n\n"
            "• Goal: <b>{name}</b>\n"
            "• Target deposit: ~<b>{nominal}</b>"
        ),
        "notif_result_expired": (
            "🏁 <b>Goal Completed: {name}</b>\n\n"
            "The savings period has ended.\n\n"
            "• Total Saved: <b>{deposited}</b> / {target}\n"
            "• Final Quality: <b>{final_quality}%</b>\n"
            "• Result: <b>{title}</b>\n\n"
            "Type /newgoal to set up your next savings goal."
        ),
        "delete_pick": "🗑 Which goal would you like to delete?",
        "delete_prompt": (
            "⚠️ <b>Delete Goal: {name}</b>\n\n"
            "Are you sure you want to delete this goal?\n"
            "All progress and ledger entries will be permanently removed."
        ),
        "delete_done": "🗑 <b>{name}</b> has been deleted.",
        "delete_cancelled": "Action cancelled. Goal remains active.",
        "settings_main": "⚙️ <b>Settings & Preferences</b>\n\nManage notifications, timezone, or account data.",
        "settings_goals_pick": "🔔 Select which goal's notifications to configure:",
        "settings_goal_detail": (
            "⚙️ <b>Notification Settings: {name}</b>\n\n"
            "• Goal: <b>{name}</b>\n"
            "• Notifications: <b>{status}</b>\n"
            "• Frequency: <b>{frequency}</b>\n"
            "• Reminder: <b>{reminder_info}</b>"
        ),
        "settings_notif_updated": "✅ Notification settings updated.",
        "settings_wipe_prompt": "⚠️ <b>Delete All My Data</b>\n\nThis will permanently delete your account and all goals.\n\nProceed?",
        "settings_wipe_confirm_text": "⚠️ <b>FINAL CONFIRMATION</b>\n\nTo delete all data, type <code>DELETE</code>.\n\nType /cancel to abort.",
        "settings_wipe_success": "👋 All your data has been permanently deleted. Goodbye!",
        "err_amount": "⚠️ Invalid amount. Please enter a valid number.",
        "err_name_len": "⚠️ Name must be between 1 and 60 characters.",
        "err_period_range": "⚠️ Period must be between 2 and 365 days.",
        "err_no_freq": "⚠️ No valid schedule for this budget and period.",
        "err_no_tz": "⚠️ Please set your timezone first using /start.",
        "err_no_goal": "⚠️ No active goal found. Type /newgoal to create one.",
        "err_expired_flow": "⚠️ Session expired. Type /newgoal to start over.",
        "err_generic": "⚠️ An error occurred. Please try again.",
    },
}


def get_text(key: str, variant: str = "pet", **kwargs: object) -> str:
    """Retrieve text template and format with kwargs.

    String values in kwargs are HTML-escaped before insertion.
    """
    variant_set = COPY.get(variant, COPY["pet"])
    template = variant_set.get(key, COPY["pet"].get(key, ""))

    escaped_kwargs = {
        k: html.escape(str(v)) if isinstance(v, str) else v for k, v in kwargs.items()
    }
    return template.format(**escaped_kwargs)
