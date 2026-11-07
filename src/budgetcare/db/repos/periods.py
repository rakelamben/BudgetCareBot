from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import FeedingPeriodTable, GoalTable


class PeriodsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_period(self, goal_id: int, idx: int) -> FeedingPeriodTable | None:
        stmt = select(FeedingPeriodTable).where(
            FeedingPeriodTable.goal_id == goal_id,
            FeedingPeriodTable.idx == idx,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_goal(self, goal_id: int) -> Sequence[FeedingPeriodTable]:
        stmt = (
            select(FeedingPeriodTable)
            .where(FeedingPeriodTable.goal_id == goal_id)
            .order_by(FeedingPeriodTable.idx.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_due_open(
        self, goal_id: int, cutoff_threshold: datetime
    ) -> Sequence[FeedingPeriodTable]:
        stmt = (
            select(FeedingPeriodTable)
            .where(
                FeedingPeriodTable.goal_id == goal_id,
                FeedingPeriodTable.status == "open",
                FeedingPeriodTable.cutoff_at <= cutoff_threshold,
            )
            .order_by(FeedingPeriodTable.idx.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_goal_ids_with_due_periods(
        self, cutoff_threshold: datetime, limit: int = 500
    ) -> Sequence[int]:
        stmt = (
            select(FeedingPeriodTable.goal_id)
            .join(GoalTable, GoalTable.id == FeedingPeriodTable.goal_id)
            .where(
                FeedingPeriodTable.status == "open",
                GoalTable.status == "active",
                FeedingPeriodTable.cutoff_at <= cutoff_threshold,
            )
            .distinct()
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    def add_all(self, periods: list[FeedingPeriodTable]) -> None:
        self.session.add_all(periods)

    async def close_period(self, goal_id: int, idx: int, status: str, closed_at: datetime) -> None:
        period = await self.get_period(goal_id, idx)
        if period:
            period.status = status
            period.closed_at = closed_at
            await self.session.flush()

    async def all_periods_closed(self, goal_id: int) -> bool:
        periods = await self.list_by_goal(goal_id)
        return all(p.status != "open" for p in periods)
