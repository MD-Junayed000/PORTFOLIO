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
    # `asyncio.run` cannot be used when there is already a running event loop
    # (e.g. when this script is invoked from inside the FastAPI app's
    # lifespan, where the loop is the one driving uvicorn). In that situation
    # `asyncio.run` raises a DeprecationWarning and silently drops the
    # coroutine -- which is exactly what we saw on Render. Detect the case
    # and use a fresh, dedicated loop in a worker thread instead so the
    # migrations always run to completion regardless of caller context.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop: safe to use asyncio.run.
        asyncio.run(run_migrations_online())
    else:
        # A loop is already running in this thread (FastAPI lifespan hook).
        # Run the migrations in a fresh loop on a worker thread so we do not
        # interfere with the caller's loop.
        import threading

        _migration_error: list = []

        def _runner() -> None:
            try:
                asyncio.run(run_migrations_online())
            except Exception as exc:  # pragma: no cover - defensive
                _migration_error.append(exc)

        t = threading.Thread(target=_runner, name="alembic-upgrade", daemon=True)
        t.start()
        t.join()
        if _migration_error:
            raise _migration_error[0]
