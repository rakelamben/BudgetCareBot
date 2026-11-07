from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from budgetcare.db.tables import EventTable


class EventsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    def record(
        self,
        name: str,
        user_id: int | None = None,
        goal_id: int | None = None,
        props: dict[str, Any] | None = None,
    ) -> EventTable:
        event = EventTable(
            user_id=user_id,
            goal_id=goal_id,
            name=name,
            props=props or {},
        )
        self.session.add(event)
        return event
