"""SQLAlchemy ORM models for the backend service."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


def utcnow() -> datetime:
    """Current UTC time, as a plain (non-aware) datetime for DB storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


LOCAL_TENANT_KEY = "local"


class Tenant(Base):
    """One customer installation of the app - the unit every other table is
    isolated by (Multi-Tenancy milestone, issue #40).

    `key` is the Forge installation id (`app.installationId` from the
    verified Forge Invocation Token), the stable per-install identifier.
    `LOCAL_TENANT_KEY` is the single tenant used when no Forge auth is in
    play (local dev, the standalone frontend/ dashboard) - never reachable
    from a Forge request unless explicitly opted in (see tenancy.py).
    `ingest_key_hash` is the SHA-256 of this tenant's CI upload key (issue
    #42); the key itself is shown once and never stored.
    """

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True)
    cloud_id: Mapped[str | None] = mapped_column(String, nullable=True)
    ingest_key_hash: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


def tenant_fk() -> Mapped[int]:
    """A non-null, indexed foreign key to tenants.id - the column every
    tenant-owned table carries, declared once so none can drift."""
    return mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)


class JiraConnection(Base):
    """A configured connection to one Jira Cloud site, one per tenant.

    See jira_client.py for the auth flow this backs. api_token is stored
    as given, not encrypted; this is a known gap to close before any
    production deployment (issue #41 replaces this with Forge's app token).
    """

    __tablename__ = "jira_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = tenant_fk()
    site_url: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    api_token: Mapped[str] = mapped_column(String, nullable=False)


class TestRun(Base):
    """One push of run-report data from `scripts/push_test_inventory.py`.

    Each push creates a new row (never replaced) so pass/fail trends over
    time (Milestone 3, issue #14) are queryable later without needing to
    retrofit history that was never kept.
    """

    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = tenant_fk()
    pushed_at: Mapped[datetime] = mapped_column(default=utcnow)

    records: Mapped[list["TestRunRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class TestRunRecord(Base):
    """One (spec x project) test outcome from one pushed run - mirrors
    parser.models.TestRecord, plus the run it belongs to."""

    __tablename__ = "test_run_records"
    __table_args__ = (
        # Backs build_inventory's windowed per-(file, title, project) history
        # query and reconciliation lookups - without it, both are sequential
        # scans once the table has any real run history.
        Index("ix_test_run_records_tenant_file_title_project_run_id", "tenant_id", "file", "title", "project", "run_id"),
        Index("ix_test_run_records_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = tenant_fk()
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), nullable=False)
    spec_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    full_title: Mapped[str] = mapped_column(String)
    file: Mapped[str] = mapped_column(String)
    line: Mapped[int] = mapped_column()
    column: Mapped[int] = mapped_column()
    project: Mapped[str] = mapped_column(String)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    jira_keys: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String)
    duration_ms: Mapped[int] = mapped_column()
    retry_count: Mapped[int] = mapped_column()
    is_flaky: Mapped[bool] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    run: Mapped[TestRun] = relationship(back_populates="records")


class SourceTestRecord(Base):
    """One test found by statically scanning source (.spec.ts or .feature) -
    mirrors parser.models.StaticTestRecord / FeatureTestRecord, which share
    an identical shape and so share this one table, distinguished by
    `source_type`.

    Unlike TestRunRecord, these are a replace-on-push snapshot of "what the
    source currently looks like" - each push wipes and re-inserts only the
    source_type(s) it actually provided (see the ingest endpoint), since
    there's no equivalent need to keep source-inventory history over time.
    """

    __tablename__ = "source_test_records"
    __table_args__ = (Index("ix_source_test_records_tenant_file_title", "tenant_id", "file", "title"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = tenant_fk()
    source_type: Mapped[str] = mapped_column(String)  # "static" | "feature"
    title: Mapped[str] = mapped_column(String)
    full_title: Mapped[str] = mapped_column(String)
    file: Mapped[str] = mapped_column(String)
    line: Mapped[int] = mapped_column()
    column: Mapped[int] = mapped_column()
    tags: Mapped[list] = mapped_column(JSON, default=list)
    jira_keys: Mapped[list] = mapped_column(JSON, default=list)
    assertions: Mapped[list] = mapped_column(JSON, default=list)  # static-only; always [] for feature rows


class JiraWebhookEvent(Base):
    """One received Jira webhook delivery (issue #10).

    Just a durable record of "this happened" - issue #17 (drift
    detection) is what will actually interpret changelog contents and
    decide whether a linked test should flip to a Suspect state. This
    table exists so that later work has real history to consume instead
    of needing to retrofit it.
    """

    __tablename__ = "jira_webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = tenant_fk()
    received_at: Mapped[datetime] = mapped_column(default=utcnow)
    issue_key: Mapped[str] = mapped_column(String)
    webhook_event: Mapped[str] = mapped_column(String)
    changelog: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON)


class JiraPollState(Base):
    """Tracks the last successful poll per Jira project (issue #11's
    polling fallback, for instances without webhook access).

    One row per project_key so multiple projects can be polled
    independently, at whatever interval an external scheduler (cron, a
    scheduled GitHub Action, etc.) triggers POST /api/jira/poll.
    """

    __tablename__ = "jira_poll_state"
    __table_args__ = (UniqueConstraint("tenant_id", "project_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = tenant_fk()
    project_key: Mapped[str] = mapped_column(String)
    last_polled_at: Mapped[datetime] = mapped_column()


class RequirementLink(Base):
    """One requirement<->test link and its suspect-link state (Milestone 4,
    issues #16/#17/#18/#20).

    Created the first time a test's jira_keys are observed referencing a
    given key (see requirement_links.sync_requirement_links) -
    content_hash/content_snapshot capture the requirement's substantive
    fields at that moment (issue #16, "hash at link time"). Drift detection
    (issue #17) recomputes the hash from live Jira content whenever a
    webhook/poll event reports that issue as changed, and flips state to
    "suspect" on a mismatch. This never auto-clears - only the "reviewed"
    action (issue #20) re-snapshots content and sets state back to
    "covered", on purpose (see CLAUDE.md's differentiator: hiding drift
    automatically would hide the exact problem this feature exists to
    surface).

    "stale" (linked test no longer in the inventory) and "orphaned" (linked
    Jira key no longer resolves) aren't stored here - they're cheap to
    derive from current inventory/Jira data at read time. See
    requirement_links.resolve_effective_state.
    """

    __tablename__ = "requirement_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "jira_key", "test_file", "test_title"),
        Index("ix_requirement_links_tenant_test_file_test_title", "tenant_id", "test_file", "test_title"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = tenant_fk()
    jira_key: Mapped[str] = mapped_column(String, index=True)
    test_file: Mapped[str] = mapped_column(String)
    test_title: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="covered")  # "covered" | "suspect"
    content_hash: Mapped[str] = mapped_column(String)
    content_snapshot: Mapped[dict] = mapped_column(JSON)
    change_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    linked_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
