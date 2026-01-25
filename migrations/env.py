import pathlib
import sys
from logging.config import fileConfig
import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from src.db.models import Base

sys.path.append(pathlib.Path.cwd())

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata


def do_run_migrations(connection):
    """
    Execute migrations using a given database connection.

    Args:
        connection: A SQLAlchemy Connection object (synchronous) that is used
                    to run migrations in a transaction.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # проверяем изменения типов
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    """
    Run database migrations in 'online' mode.

    This mode connects to the database asynchronously and applies migrations
    directly to the database.
    """
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline():
    """
    Run database migrations in 'offline' mode.

    This mode does not require a live database connection. SQL statements
    are generated and outputted as a script.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
