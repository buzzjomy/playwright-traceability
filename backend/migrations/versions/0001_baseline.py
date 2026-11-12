"""Baseline: the single-tenant schema as it existed before multi-tenancy.

Databases created earlier by `Base.metadata.create_all` already have this
schema; db.init_db() stamps them at this revision instead of re-running it.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the pre-tenancy tables."""
    op.create_table(
        "jira_connections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("site_url", sa.String, nullable=False),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("api_token", sa.String, nullable=False),
    )
    op.create_table(
        "test_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pushed_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "test_run_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("test_runs.id"), nullable=False),
        sa.Column("spec_id", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("full_title", sa.String, nullable=False),
        sa.Column("file", sa.String, nullable=False),
        sa.Column("line", sa.Integer, nullable=False),
        sa.Column("column", sa.Integer, nullable=False),
        sa.Column("project", sa.String, nullable=False),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("jira_keys", sa.JSON, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("retry_count", sa.Integer, nullable=False),
        sa.Column("is_flaky", sa.Boolean, nullable=False),
        sa.Column("error_message", sa.String, nullable=True),
    )
    op.create_index("ix_test_run_records_file_title_project_run_id", "test_run_records", ["file", "title", "project", "run_id"])
    op.create_index("ix_test_run_records_run_id", "test_run_records", ["run_id"])
    op.create_table(
        "source_test_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("full_title", sa.String, nullable=False),
        sa.Column("file", sa.String, nullable=False),
        sa.Column("line", sa.Integer, nullable=False),
        sa.Column("column", sa.Integer, nullable=False),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("jira_keys", sa.JSON, nullable=False),
        sa.Column("assertions", sa.JSON, nullable=False),
    )
    op.create_index("ix_source_test_records_file_title", "source_test_records", ["file", "title"])
    op.create_table(
        "jira_webhook_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("received_at", sa.DateTime, nullable=False),
        sa.Column("issue_key", sa.String, nullable=False),
        sa.Column("webhook_event", sa.String, nullable=False),
        sa.Column("changelog", sa.JSON, nullable=True),
        sa.Column("raw_payload", sa.JSON, nullable=False),
    )
    op.create_table(
        "jira_poll_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_key", sa.String, nullable=False, unique=True),
        sa.Column("last_polled_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "requirement_links",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("jira_key", sa.String, nullable=False),
        sa.Column("test_file", sa.String, nullable=False),
        sa.Column("test_title", sa.String, nullable=False),
        sa.Column("state", sa.String, nullable=False),
        sa.Column("content_hash", sa.String, nullable=False),
        sa.Column("content_snapshot", sa.JSON, nullable=False),
        sa.Column("change_summary", sa.String, nullable=True),
        sa.Column("linked_at", sa.DateTime, nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("jira_key", "test_file", "test_title"),
    )
    op.create_index("ix_requirement_links_jira_key", "requirement_links", ["jira_key"])
    op.create_index("ix_requirement_links_test_file_test_title", "requirement_links", ["test_file", "test_title"])


def downgrade() -> None:
    """Drop everything (only meaningful on a throwaway database)."""
    for table in (
        "requirement_links",
        "jira_poll_state",
        "jira_webhook_events",
        "source_test_records",
        "test_run_records",
        "test_runs",
        "jira_connections",
    ):
        op.drop_table(table)
