from collections.abc import AsyncGenerator

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from budgetcare.config import settings


def create_engine(url: str | None = None) -> AsyncEngine:
    db_url = url or settings.DATABASE_URL
    if not db_url:
        # Fallback for local initialization if not configured yet
        db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"

    # Normalize url for asyncpg
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return create_async_engine(
        db_url,
        poolclass=pool.NullPool,
        echo=(settings.LOG_LEVEL.upper() == "DEBUG"),
        connect_args={
            "server_settings": {"search_path": "budget_care,public"},
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Module-level default engine and sessionmaker
default_engine = create_engine()
session_factory = create_session_factory(default_engine)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
