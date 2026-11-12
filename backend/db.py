"""SQLAlchemy engine and session setup for the backend service.

Defaults to a local SQLite file for zero-setup local development; set the
DATABASE_URL environment variable to a Postgres connection string for
anything beyond that (see CLAUDE.md for why Postgres is the target
production database - SQLAlchemy's column types are portable across both).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

def normalize_database_url(url: str) -> str:
    """Normalize a DATABASE_URL to name the psycopg (v3) driver explicitly.

    Fly.io (and Heroku-style platforms before it) hand out `postgres://`
    URLs - SQLAlchemy 2.0 needs an explicit driver in the scheme, and we
    ship psycopg (v3) rather than the older psycopg2, so both the bare
    `postgres://` and plain `postgresql://` forms get it named. Anything
    else (sqlite, an already-explicit `postgresql+...://`) passes through
    unchanged.
    """
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = normalize_database_url(os.environ.get("DATABASE_URL", "sqlite:///./traceability.db"))

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def alembic_config(target_engine=None):
    """An Alembic Config pointed at backend/migrations (and optionally at a
    specific engine - the migration tests pass their own)."""
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "migrations"))
    if target_engine is not None:
        config.attributes["engine"] = target_engine
    return config


def migrate(target_engine=None) -> None:
    """Bring a database up to the latest schema with Alembic.

    A database created before migrations existed (by the old
    `create_all`) already has the baseline schema but no alembic_version
    table - it's stamped at the baseline revision first, so only the newer
    migrations run against it instead of trying to re-create its tables.
    """
    from alembic import command
    from sqlalchemy import inspect

    target = target_engine or engine
    config = alembic_config(target)
    tables = set(inspect(target).get_table_names())
    if "alembic_version" not in tables and "test_runs" in tables:
        command.stamp(config, "0001")
    command.upgrade(config, "head")


def init_db() -> None:
    """Migrate the database to the latest schema. Called once at app startup."""
    migrate()
