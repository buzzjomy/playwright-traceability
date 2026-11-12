"""The migrations against a REAL Postgres (production's database), which
SQLite can't stand in for: constraint naming, ALTER semantics and types all
differ. Skipped unless MIGRATION_TEST_DATABASE_URL points at a throwaway
Postgres database - CI provides one (see .github/workflows/ci.yml).
"""

import os
from datetime import datetime

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from backend.db import Base, alembic_config, migrate, normalize_database_url
import backend.models  # noqa: F401

URL = os.environ.get("MIGRATION_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="MIGRATION_TEST_DATABASE_URL not set")


@pytest.fixture()
def engine():
    """An engine on a schema wiped clean before and after the test."""
    engine = create_engine(normalize_database_url(URL))

    def wipe():
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))

    wipe()
    yield engine
    wipe()
    engine.dispose()


def _no_diffs(engine):
    with engine.connect() as connection:
        return compare_metadata(MigrationContext.configure(connection), Base.metadata)


def test_fresh_postgres_database_matches_the_models(engine):
    migrate(engine)
    assert _no_diffs(engine) == []


def test_a_create_all_era_postgres_database_is_stamped_and_backfilled(engine):
    # Exactly what the Fly database looks like: the old schema, no alembic_version.
    command.upgrade(alembic_config(engine), "0001")
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
        now = datetime(2026, 1, 1)
        connection.execute(text("INSERT INTO test_runs (pushed_at) VALUES (:n)"), {"n": now})
        connection.execute(text("INSERT INTO jira_poll_state (project_key, last_polled_at) VALUES ('KAN', :n)"), {"n": now})
        connection.execute(
            text(
                "INSERT INTO requirement_links (jira_key, test_file, test_title, state, content_hash, "
                "content_snapshot, linked_at) VALUES ('KAN-1', 'a.spec.ts', 't', 'covered', 'h', '{}', :n)"
            ),
            {"n": now},
        )

    migrate(engine)

    with engine.connect() as connection:
        local_id = connection.execute(text("SELECT id FROM tenants WHERE key = 'local'")).scalar_one()
        for table in ("test_runs", "jira_poll_state", "requirement_links"):
            assert connection.execute(text(f"SELECT tenant_id FROM {table}")).scalars().all() == [local_id], table
    assert _no_diffs(engine) == []
