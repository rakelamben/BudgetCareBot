from timezonefinder import TimezoneFinder

from budgetcare.db.tables import UserTable
from budgetcare.db.uow import UnitOfWork

tz_finder = TimezoneFinder()


async def get_or_create_user(
    uow: UnitOfWork, telegram_user_id: int, chat_id: int, variant: str = "pet"
) -> tuple[UserTable, bool]:
    user, is_new = await uow.users.upsert_user(telegram_user_id, chat_id, variant=variant)
    if is_new:
        uow.events.record("user_started", user_id=user.id, props={"variant": variant})
    return user, is_new


async def update_timezone_from_coords(
    uow: UnitOfWork, user_id: int, lat: float, lng: float
) -> str | None:
    tz_name = tz_finder.timezone_at(lat=lat, lng=lng)
    if not tz_name:
        return None

    await uow.users.set_timezone(user_id, tz_name)
    uow.events.record("timezone_set", user_id=user_id, props={"timezone": tz_name})
    return tz_name
