from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import ConversationTable


class ConversationsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: int) -> ConversationTable | None:
        return await self.session.get(ConversationTable, user_id)

    async def set_state(
        self, user_id: int, flow: str, step: str, data: dict[str, Any]
    ) -> ConversationTable:
        conv = await self.get(user_id)
        now = datetime.now(UTC)
        if conv is None:
            conv = ConversationTable(
                user_id=user_id,
                flow=flow,
                step=step,
                data=data,
                updated_at=now,
            )
            self.session.add(conv)
        else:
            conv.flow = flow
            conv.step = step
            conv.data = data
            conv.updated_at = now
        await self.session.flush()
        return conv

    async def delete(self, user_id: int) -> None:
        conv = await self.get(user_id)
        if conv:
            await self.session.delete(conv)
            await self.session.flush()
