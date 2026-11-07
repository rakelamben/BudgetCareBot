from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import UserTable


class UsersRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> UserTable | None:
        stmt = select(UserTable).where(UserTable.telegram_user_id == telegram_user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> UserTable | None:
        return await self.session.get(UserTable, user_id)

    async def upsert_user(
        self, telegram_user_id: int, chat_id: int, variant: str = "pet"
    ) -> tuple[UserTable, bool]:
        user = await self.get_by_telegram_id(telegram_user_id)
        is_new = False
        if user is None:
            user = UserTable(
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                variant=variant,
            )
            self.session.add(user)
            await self.session.flush()
            is_new = True
        else:
            user.chat_id = chat_id
            user.blocked_at = None
            await self.session.flush()
        return user, is_new

    async def set_timezone(self, user_id: int, timezone_name: str) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.timezone = timezone_name
            await self.session.flush()

    async def set_blocked(self, user_id: int, blocked: bool) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.blocked_at = datetime.now(UTC) if blocked else None
            await self.session.flush()

    async def delete_user(self, user_id: int) -> None:
        user = await self.get_by_id(user_id)
        if user:
            await self.session.delete(user)
            await self.session.flush()
