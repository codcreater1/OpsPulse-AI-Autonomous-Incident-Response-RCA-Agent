"""Alembic environment: uses the application's engine configuration (DATABASE_URL)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from src.db.client import get_engine
from src.db.models import Base

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(get_engine().url), target_metadata=target_metadata, literal_binds=True, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    # render_as_batch lets ALTER TABLE work on SQLite (used by the migration test); no effect on PostgreSQL.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied = context.config.attributes.get("connection")  # tests pass their own connection
    if supplied is not None:
        _run(supplied)
        return
    with get_engine().connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
