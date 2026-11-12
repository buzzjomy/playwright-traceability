"""Alembic environment: runs migrations against backend.db's engine (or an
engine a caller passes in via `config.attributes["engine"]`, which the
migration tests use)."""

from alembic import context

from backend.db import Base, engine as default_engine
import backend.models  # noqa: F401  - registers every table on Base.metadata

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Run all pending migrations in one transaction per migration."""
    engine = config.attributes.get("engine", default_engine)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
