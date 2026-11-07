from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import JobLockTable


class LocksRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def acquire_lease(self, name: str, ttl_seconds: int, locked_by: str) -> bool:
        """Acquire lease lock if locked_until < now."""
        now = datetime.now(UTC)
        new_until = now + timedelta(seconds=ttl_seconds)

        stmt = (
            update(JobLockTable)
            .where(
                JobLockTable.name == name,
                JobLockTable.locked_until < now,
            )
            .values(locked_until=new_until, locked_by=locked_by)
            .returning(JobLockTable.name)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def release_lease(self, name: str) -> None:
        stmt = (
            update(JobLockTable)
            .where(JobLockTable.name == name)
            .values(
                locked_until=datetime.fromtimestamp(0, tz=UTC),
                locked_by=None,
            )
        )
        await self.session.execute(stmt)
