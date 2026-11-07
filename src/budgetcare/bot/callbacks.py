"""Callback data builder and validator (<64 bytes)."""


def build_callback(prefix: str, action: str, *args: object) -> str:
    parts = [prefix, action] + [str(a) for a in args]
    data = ":".join(parts)
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"Callback data exceeds 64 bytes limit: {data}")
    return data


# Wizard callback prefixes: 'nf' (new goal flow)
CB_FREQ_DAILY = build_callback("nf", "f", "daily")
CB_FREQ_WEEKLY = build_callback("nf", "f", "weekly")
CB_FREQ_MONTHLY = build_callback("nf", "f", "monthly")

CB_NOTIF_ON = build_callback("nf", "n", 1)
CB_NOTIF_OFF = build_callback("nf", "n", 0)

CB_CONFIRM_OK = build_callback("nf", "ok")
CB_CONFIRM_NO = build_callback("nf", "no")


def cb_weekday(day_int: int) -> str:
    return build_callback("nf", "w", day_int)


def cb_dom(day_str: str | int) -> str:
    return build_callback("nf", "d", day_str)


# Feeding callbacks: 'fd'
def cb_feed_goal(goal_id: int, amount_cents: int) -> str:
    return build_callback("fd", "g", goal_id, amount_cents)


def cb_feed_free_food(goal_id: int) -> str:
    return build_callback("fd", "ff", goal_id)


# Undo callbacks: 'un'
def cb_undo_confirm(entry_id: int) -> str:
    return build_callback("un", "ok", entry_id)


CB_UNDO_CANCEL = build_callback("un", "no")
