"""Gap analyses: the latest gap-analysis run per (tenant, requirement), so the
analysis can run in the background and be polled for (issue #50).

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create gap_analyses."""
    op.create_table(
        "gap_analyses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_key", sa.String, nullable=False),
        sa.Column("jira_key", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("criteria", sa.JSON, nullable=True),
        sa.Column("uncovered_count", sa.Integer, nullable=True),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("tenant_id", "jira_key"),
    )
    op.create_index("ix_gap_analyses_tenant_id", "gap_analyses", ["tenant_id"])


def downgrade() -> None:
    """Drop gap_analyses (its rows are re-derivable by re-running the analysis)."""
    op.drop_table("gap_analyses")
