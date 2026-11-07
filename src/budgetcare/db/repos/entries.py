from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import EntryTable, GoalTable


class EntriesRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, entry_id: int) -> EntryTable | None:
        return await self.session.get(EntryTable, entry_id)

    def add(self, entry: EntryTable) -> None:
        self.session.add(entry)

    async def has_active_feeding(self, goal_id: int, period_idx: int) -> bool:
        stmt = (
            select(EntryTable.id)
            .where(
                EntryTable.goal_id == goal_id,
                EntryTable.period_idx == period_idx,
                EntryTable.is_feeding.is_(True),
                EntryTable.undone_at.is_(None),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_by_goal(self, goal_id: int) -> Sequence[EntryTable]:
        stmt = (
            select(EntryTable)
            .where(EntryTable.goal_id == goal_id)
            .order_by(EntryTable.occurred_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_active_by_user(self, user_id: int, since: datetime) -> EntryTable | None:
        """Find user's most recent active entry within since timestamp."""
        stmt = (
            select(EntryTable)
            .join(GoalTable, GoalTable.id == EntryTable.goal_id)
            .where(
                GoalTable.user_id == user_id,
                EntryTable.undone_at.is_(None),
                EntryTable.created_at >= since,
            )
            .order_by(EntryTable.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_undone(self, entry_id: int, undone_at: datetime) -> None:
        entry = await self.get_by_id(entry_id)
        if entry:
            entry.undone_at = undone_at
            await self.session.flush()

    async def sum_deposited_cents(self, goal_id: int) -> int:
        stmt = select(func.coalesce(func.sum(EntryTable.amount_cents), 0)).where(
            EntryTable.goal_id == goal_id,
            EntryTable.undone_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def count_free_food(self, goal_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(EntryTable)
            .where(
                EntryTable.goal_id == goal_id,
                EntryTable.kind == "free_food",
                EntryTable.undone_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
