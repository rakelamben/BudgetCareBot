import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection

from budgetcare.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Determine database migration URL
db_url = settings.DATABASE_URL_MIGRATIONS or settings.DATABASE_URL
if not db_url:
    db_url = os.getenv("DATABASE_URL_MIGRATIONS", os.getenv("DATABASE_URL", ""))

# Ensure asyncpg driver prefix
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Escape % characters for Alembic ConfigParser interpolation
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

target_metadata = None

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


def run_migrations_offline() -> None:
    url = db_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="budget_care",
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    connection.execute(sa.text("create schema if not exists budget_care;"))
    connection.execute(sa.text("set search_path to budget_care, public;"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema="budget_care",
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        db_url,
        poolclass=pool.NullPool,
        connect_args={
            "server_settings": {"search_path": "budget_care,public"},
        },
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
        await connection.commit()

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
