"""The Alembic migrations (multi-tenancy, issue #40): a fresh database must
end up with exactly the schema the models declare, and a database created
before migrations existed must be upgraded without losing its data."""

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from backend.db import Base, alembic_config, migrate
import backend.models  # noqa: F401


def _engine(tmp_path, name="m.db"):
    return create_engine(f"sqlite:///{tmp_path / name}")


def test_fresh_database_matches_the_models_exactly(tmp_path):
    engine = _engine(tmp_path)
    migrate(engine)
    with engine.connect() as connection:
        diffs = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diffs == []


def test_pre_migration_database_is_stamped_and_backfilled_into_the_local_tenant(tmp_path):
    engine = _engine(tmp_path)
    # Build the old (single-tenant) schema, then forget it was ever versioned:
    # that is exactly what a database created by the old create_all looks like.
    command.upgrade(alembic_config(engine), "0001")
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
        now = datetime(2026, 1, 1)
        connection.execute(
            text("INSERT INTO jira_connections (site_url, email, api_token) VALUES ('https://x.atlassian.net', 'a@b.c', 't')")
        )
        connection.execute(text("INSERT INTO test_runs (pushed_at) VALUES (:n)"), {"n": now})
        connection.execute(
            text("INSERT INTO jira_poll_state (project_key, last_polled_at) VALUES ('KAN', :n)"), {"n": now}
        )
        connection.execute(
            text(
                "INSERT INTO requirement_links (jira_key, test_file, test_title, state, content_hash, "
                "content_snapshot, linked_at) VALUES ('KAN-1', 'a.spec.ts', 't', 'covered', 'h', :snap, :n)"
            ),
            {"snap": json.dumps({}), "n": now},
        )

    migrate(engine)

    with engine.connect() as connection:
        local_id = connection.execute(text("SELECT id FROM tenants WHERE key = 'local'")).scalar_one()
        for table in ("jira_connections", "test_runs", "jira_poll_state", "requirement_links"):
            tenant_ids = connection.execute(text(f"SELECT tenant_id FROM {table}")).scalars().all()
            assert tenant_ids == [local_id], table
        diffs = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diffs == []


def test_uniqueness_is_per_tenant_after_migrating(tmp_path):
    engine = _engine(tmp_path)
    migrate(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO tenants (key, created_at) VALUES ('t2', '2026-01-01')"))
        t2 = connection.execute(text("SELECT id FROM tenants WHERE key = 't2'")).scalar_one()
        local = connection.execute(text("SELECT id FROM tenants WHERE key = 'local'")).scalar_one()
        for tenant_id in (local, t2):  # the same project key under two tenants is fine
            connection.execute(
                text("INSERT INTO jira_poll_state (tenant_id, project_key, last_polled_at) VALUES (:t, 'KAN', '2026-01-01')"),
                {"t": tenant_id},
            )
    with engine.begin() as connection:
        try:
            connection.execute(
                text("INSERT INTO jira_poll_state (tenant_id, project_key, last_polled_at) VALUES (:t, 'KAN', '2026-01-01')"),
                {"t": local},
            )
        except sa.exc.IntegrityError:
            return
    raise AssertionError("a duplicate (tenant, project) poll state was accepted")
