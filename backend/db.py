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


def init_db() -> None:
    """Create all tables that don't exist yet. Called once at app startup."""
    Base.metadata.create_all(bind=engine)
