from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import TickRunTable


class TickRunsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def start_run(self) -> int:
        """Record the start of a tick run and return its id."""
        run = TickRunTable(started_at=datetime.now(UTC))
        self.session.add(run)
        await self.session.flush()
        return run.id

    async def finish_run(
        self,
        run_id: int,
        stats: dict[str, Any],
        error: str | None = None,
    ) -> None:
        """Record the completion of a tick run."""
        run = await self.session.get(TickRunTable, run_id)
        if run:
            run.finished_at = datetime.now(UTC)
            run.stats = stats
            run.error = error
            await self.session.flush()
