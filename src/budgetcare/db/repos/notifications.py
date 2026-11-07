from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import NotificationTable


class NotificationsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, notif_id: int) -> NotificationTable | None:
        return await self.session.get(NotificationTable, notif_id)

    def add_all(self, notifs: list[NotificationTable]) -> None:
        self.session.add_all(notifs)

    async def claim_due(self, limit: int, now: datetime) -> Sequence[NotificationTable]:
        """Claim due notifications using FOR UPDATE SKIP LOCKED."""
        subquery = (
            select(NotificationTable.id)
            .where(
                NotificationTable.status == "pending",
                NotificationTable.due_at <= now,
            )
            .order_by(NotificationTable.due_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )

        stmt = (
            update(NotificationTable)
            .where(NotificationTable.id.in_(subquery))
            .values(
                status="sending",
                claimed_at=now,
                attempts=NotificationTable.attempts + 1,
            )
            .returning(NotificationTable)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_sent(self, notif_id: int, sent_at: datetime) -> None:
        notif = await self.get_by_id(notif_id)
        if notif:
            notif.status = "sent"
            notif.sent_at = sent_at
            await self.session.flush()

    async def mark_skipped(self, notif_id: int) -> None:
        notif = await self.get_by_id(notif_id)
        if notif:
            notif.status = "skipped"
            await self.session.flush()

    async def mark_failed(self, notif_id: int, error: str) -> None:
        notif = await self.get_by_id(notif_id)
        if notif:
            notif.status = "failed"
            notif.last_error = error
            await self.session.flush()

    async def cancel_pending_by_goal(self, goal_id: int) -> None:
        stmt = (
            update(NotificationTable)
            .where(
                NotificationTable.goal_id == goal_id,
                NotificationTable.status.in_(["pending", "sending"]),
            )
            .values(status="cancelled")
        )
        await self.session.execute(stmt)

    async def delete_pending_by_goal(self, goal_id: int) -> None:
        stmt = select(NotificationTable).where(
            NotificationTable.goal_id == goal_id,
            NotificationTable.status.in_(["pending", "cancelled"]),
        )
        result = await self.session.execute(stmt)
        for n in result.scalars().all():
            await self.session.delete(n)
        await self.session.flush()

    async def reclaim_stale_sending(self, cutoff: datetime, max_attempts: int) -> tuple[int, int]:
        """Reclaim stale sending rows: back to pending or marked failed."""
        # 1. Stale that exceeded max_attempts -> failed
        fail_stmt = (
            update(NotificationTable)
            .where(
                NotificationTable.status == "sending",
                NotificationTable.claimed_at < cutoff,
                NotificationTable.attempts >= max_attempts,
            )
            .values(status="failed", last_error="Max delivery attempts reached")
        )
        fail_res = await self.session.execute(fail_stmt)

        # 2. Stale that can be retried -> pending
        requeue_stmt = (
            update(NotificationTable)
            .where(
                NotificationTable.status == "sending",
                NotificationTable.claimed_at < cutoff,
                NotificationTable.attempts < max_attempts,
            )
            .values(status="pending")
        )
        requeue_res = await self.session.execute(requeue_stmt)

        return fail_res.rowcount, requeue_res.rowcount
