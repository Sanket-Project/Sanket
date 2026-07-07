"""Alembic env — async-aware, reads DATABASE_URL from app.config.

Migrations run with the sanket_app role; SET LOCAL app.current_tenant_id = ''
is configured so that RLS doesn't prevent schema operations.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Importing all models so Base.metadata is fully populated.
from app import models  # noqa: F401
from app.config import get_settings
from app.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


settings = get_settings()
db_url = os.getenv("MIGRATION_DATABASE_URL") or settings.database_url
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Commit after each migration instead of wrapping the whole `upgrade`
        # in a single transaction. Required so a migration that runs
        # `ALTER TYPE ... ADD VALUE` (enum extension) commits before a later
        # migration uses the new label — Postgres forbids using a freshly-added
        # enum value in the same transaction it was added in.
        transaction_per_migration=True,
    )
    # Suspend RLS for migrations
    connection.exec_driver_sql("SET LOCAL app.current_tenant_id = ''")
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
