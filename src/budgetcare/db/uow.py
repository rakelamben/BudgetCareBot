from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from budgetcare.db.engine import session_factory as default_session_factory
from budgetcare.db.repos.conversations import ConversationsRepo
from budgetcare.db.repos.entries import EntriesRepo
from budgetcare.db.repos.events import EventsRepo
from budgetcare.db.repos.goals import GoalsRepo
from budgetcare.db.repos.locks import LocksRepo
from budgetcare.db.repos.notifications import NotificationsRepo
from budgetcare.db.repos.periods import PeriodsRepo
from budgetcare.db.repos.tick_runs import TickRunsRepo
from budgetcare.db.repos.updates import UpdatesRepo
from budgetcare.db.repos.users import UsersRepo


class UnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UsersRepo(session)
        self.goals = GoalsRepo(session)
        self.periods = PeriodsRepo(session)
        self.entries = EntriesRepo(session)
        self.notifications = NotificationsRepo(session)
        self.conversations = ConversationsRepo(session)
        self.updates = UpdatesRepo(session)
        self.locks = LocksRepo(session)
        self.tick_runs = TickRunsRepo(session)
        self.events = EventsRepo(session)
        self.outgoing_replies: list[dict[str, Any]] = []

    def add_reply(self, chat_id: int, text: str, **kwargs: Any) -> None:
        """Stage an outgoing reply to be sent after transaction commit."""
        self.outgoing_replies.append({"chat_id": chat_id, "text": text, **kwargs})

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


@asynccontextmanager
async def uow_factory(
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncGenerator[UnitOfWork, None]:
    maker = factory or default_session_factory
    async with maker() as session, session.begin():
        uow = UnitOfWork(session)
        try:
            yield uow
        except Exception:
            await session.rollback()
            raise
