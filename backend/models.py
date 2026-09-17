"""SQLAlchemy ORM models for the backend service."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


def _utcnow() -> datetime:
    """Current UTC time, as a plain (non-aware) datetime for DB storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class JiraConnection(Base):
    """A configured connection to one Jira Cloud site.

    Single-row-per-deployment for now (a solo builder's MVP, not yet
    multi-tenant) - see jira_client.py for the auth flow this backs.
    api_token is stored as given, not encrypted; this is a known gap to
    close before any multi-user or production deployment.
    """

    __tablename__ = "jira_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
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
    pushed_at: Mapped[datetime] = mapped_column(default=_utcnow)

    records: Mapped[list["TestRunRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class TestRunRecord(Base):
    """One (spec x project) test outcome from one pushed run - mirrors
    parser.models.TestRecord, plus the run it belongs to."""

    __tablename__ = "test_run_records"

    id: Mapped[int] = mapped_column(primary_key=True)
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

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String)  # "static" | "feature"
    title: Mapped[str] = mapped_column(String)
    full_title: Mapped[str] = mapped_column(String)
    file: Mapped[str] = mapped_column(String)
    line: Mapped[int] = mapped_column()
    column: Mapped[int] = mapped_column()
    tags: Mapped[list] = mapped_column(JSON, default=list)
    jira_keys: Mapped[list] = mapped_column(JSON, default=list)
