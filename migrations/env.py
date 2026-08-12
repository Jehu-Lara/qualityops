"""Online-only Alembic environment for the QualityOps-owned schema."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


def _database_url():
    raw_url = os.environ.get("QUALITYOPS_DATABASE_URL")
    if not raw_url:
        raise RuntimeError("QUALITYOPS_DATABASE_URL is required for migrations")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Only PostgreSQL migration URLs are supported")
    return url.set(drivername="postgresql+psycopg")


def run_migrations_online() -> None:
    engine = create_engine(
        _database_url(),
        echo=False,
        poolclass=NullPool,
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=None,
                transactional_ddl=True,
                version_table="alembic_version",
                version_table_schema="public",
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("QualityOps migrations require an online PostgreSQL connection")

run_migrations_online()
