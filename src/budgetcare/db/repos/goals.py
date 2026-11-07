from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import GoalTable


class GoalsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, goal_id: int) -> GoalTable | None:
        return await self.session.get(GoalTable, goal_id)

    async def lock_goal(self, goal_id: int) -> GoalTable | None:
        """Lock goal row with SELECT FOR UPDATE to serialize operations."""
        stmt = select(GoalTable).where(GoalTable.id == goal_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def lock_skip_locked(self, goal_id: int) -> GoalTable | None:
        """Lock goal row with SELECT FOR UPDATE SKIP LOCKED for the tick job."""
        stmt = select(GoalTable).where(GoalTable.id == goal_id).with_for_update(skip_locked=True)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_by_user(self, user_id: int) -> Sequence[GoalTable]:
        stmt = (
            select(GoalTable)
            .where(GoalTable.user_id == user_id, GoalTable.status == "active")
            .order_by(GoalTable.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_archived_by_user(self, user_id: int) -> Sequence[GoalTable]:
        stmt = (
            select(GoalTable)
            .where(GoalTable.user_id == user_id, GoalTable.status.in_(["graduated", "expired"]))
            .order_by(GoalTable.closed_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_active_by_user(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(GoalTable)
            .where(GoalTable.user_id == user_id, GoalTable.status == "active")
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    def add(self, goal: GoalTable) -> None:
        self.session.add(goal)

    async def update_status(
        self,
        goal_id: int,
        status: str,
        closed_at: datetime | None = None,
        graduated_at: datetime | None = None,
        result_snapshot: dict[str, Any] | None = None,
    ) -> None:
        goal = await self.get_by_id(goal_id)
        if goal:
            goal.status = status
            if closed_at is not None:
                goal.closed_at = closed_at
            if graduated_at is not None:
                goal.graduated_at = graduated_at
            if result_snapshot is not None:
                goal.result = result_snapshot
            await self.session.flush()

    async def delete_goal(self, goal_id: int) -> None:
        goal = await self.get_by_id(goal_id)
        if goal:
            await self.session.delete(goal)
            await self.session.flush()
