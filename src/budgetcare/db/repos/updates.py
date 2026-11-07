from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import ProcessedUpdateTable


class UpdatesRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_if_not_exists(self, update_id: int) -> bool:
        """Insert update_id into processed_updates.

        Returns True if inserted (new update), False if already existed (conflict).
        """
        stmt = (
            insert(ProcessedUpdateTable)
            .values(update_id=update_id)
            .on_conflict_do_nothing(index_elements=["update_id"])
            .returning(ProcessedUpdateTable.update_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
