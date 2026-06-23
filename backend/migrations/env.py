"""Alembic environment.

Reads DATABASE_URL from the application settings (which loads .env) and runs
migrations asynchronously against the same engine the app uses.
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make sure the app package is importable when alembic is invoked from /backend.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings  # noqa: E402  (after sys.path tweak)
from database import Base  # noqa: E402  (metadata target)

# Alembic Config object.
config = context.config

# Inject the runtime URL.
# - Strip `channel_binding` because asyncpg does not understand it.
url = settings.DATABASE_URL.split("?")[0]
qs = settings.DATABASE_URL.split("?")[1] if "?" in settings.DATABASE_URL else ""
params = [p for p in qs.split("&") if p] if qs else []
filtered = [p for p in params if not p.startswith("channel_binding=")]
url = url + ("?" + "&".join(filtered) if filtered else "")
config.set_main_option("sqlalchemy.url", url)

# Configure stdlib logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata target for `alembic revision --autogenerate`.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI)."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
