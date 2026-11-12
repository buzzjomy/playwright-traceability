"""Multi-tenancy: a tenants table and a tenant_id on every tenant-owned table.

Existing rows (the single-tenant deployment's data) are assigned to the
"local" tenant - the deployment owner's own - so nothing is lost.
Uniqueness that was global (poll state per project, links per
key/test) becomes per-tenant, via table rebuilds so it works identically on
SQLite and Postgres without depending on auto-generated constraint names.

Revision ID: 0002
Revises: 0001
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

LOCAL_TENANT_KEY = "local"
# Tables that just gain a tenant_id column (no uniqueness change).
SIMPLE_TABLES = ["jira_connections", "test_runs", "test_run_records", "source_test_records", "jira_webhook_events"]


def _local_tenant_id(bind) -> int:
    """Insert the 'local' tenant and return its id."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    bind.execute(
        sa.text("INSERT INTO tenants (key, created_at) VALUES (:key, :now)"), {"key": LOCAL_TENANT_KEY, "now": now}
    )
    return bind.execute(sa.text("SELECT id FROM tenants WHERE key = :key"), {"key": LOCAL_TENANT_KEY}).scalar_one()


def upgrade() -> None:
    """Add tenancy, backfilling existing rows into the local tenant."""
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String, nullable=False, unique=True),
        sa.Column("cloud_id", sa.String, nullable=True),
        sa.Column("ingest_key_hash", sa.String, nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    bind = op.get_bind()
    local_id = _local_tenant_id(bind)

    for table in SIMPLE_TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.Integer, nullable=True))
        bind.execute(sa.text(f"UPDATE {table} SET tenant_id = :t"), {"t": local_id})
        with op.batch_alter_table(table) as batch:
            batch.alter_column("tenant_id", existing_type=sa.Integer, nullable=False)
            batch.create_foreign_key(f"fk_{table}_tenant_id", "tenants", ["tenant_id"], ["id"])
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])

    op.drop_index("ix_test_run_records_file_title_project_run_id", table_name="test_run_records")
    op.create_index(
        "ix_test_run_records_tenant_file_title_project_run_id",
        "test_run_records",
        ["tenant_id", "file", "title", "project", "run_id"],
    )
    op.drop_index("ix_source_test_records_file_title", table_name="source_test_records")
    op.create_index("ix_source_test_records_tenant_file_title", "source_test_records", ["tenant_id", "file", "title"])

    _rebuild_poll_state(bind, local_id)
    _rebuild_requirement_links(bind, local_id)


def _rebuild_poll_state(bind, local_id: int) -> None:
    """jira_poll_state: unique(project_key) becomes unique(tenant_id, project_key)."""
    op.create_table(
        "jira_poll_state_new",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_key", sa.String, nullable=False),
        sa.Column("last_polled_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("tenant_id", "project_key"),
    )
    bind.execute(
        sa.text(
            "INSERT INTO jira_poll_state_new (id, tenant_id, project_key, last_polled_at) "
            "SELECT id, :t, project_key, last_polled_at FROM jira_poll_state"
        ),
        {"t": local_id},
    )
    op.drop_table("jira_poll_state")
    op.rename_table("jira_poll_state_new", "jira_poll_state")
    op.create_index("ix_jira_poll_state_tenant_id", "jira_poll_state", ["tenant_id"])


def _rebuild_requirement_links(bind, local_id: int) -> None:
    """requirement_links: unique(key, file, title) becomes unique(tenant_id, key, file, title)."""
    op.create_table(
        "requirement_links_new",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("jira_key", sa.String, nullable=False),
        sa.Column("test_file", sa.String, nullable=False),
        sa.Column("test_title", sa.String, nullable=False),
        sa.Column("state", sa.String, nullable=False),
        sa.Column("content_hash", sa.String, nullable=False),
        sa.Column("content_snapshot", sa.JSON, nullable=False),
        sa.Column("change_summary", sa.String, nullable=True),
        sa.Column("linked_at", sa.DateTime, nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("tenant_id", "jira_key", "test_file", "test_title"),
    )
    bind.execute(
        sa.text(
            "INSERT INTO requirement_links_new (id, tenant_id, jira_key, test_file, test_title, state, "
            "content_hash, content_snapshot, change_summary, linked_at, last_reviewed_at) "
            "SELECT id, :t, jira_key, test_file, test_title, state, content_hash, content_snapshot, "
            "change_summary, linked_at, last_reviewed_at FROM requirement_links"
        ),
        {"t": local_id},
    )
    op.drop_table("requirement_links")
    op.rename_table("requirement_links_new", "requirement_links")
    op.create_index("ix_requirement_links_tenant_id", "requirement_links", ["tenant_id"])
    op.create_index("ix_requirement_links_jira_key", "requirement_links", ["jira_key"])
    op.create_index("ix_requirement_links_tenant_test_file_test_title", "requirement_links", ["tenant_id", "test_file", "test_title"])


def downgrade() -> None:
    """Not supported: collapsing tenants back into one would merge their data."""
    raise NotImplementedError("Multi-tenancy cannot be downgraded without merging or losing tenants' data")
