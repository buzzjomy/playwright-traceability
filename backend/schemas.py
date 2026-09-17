"""Pydantic request/response models for the backend API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, HttpUrl


class JiraConnectionCreate(BaseModel):
    """Request body for setting up a Jira Cloud connection."""

    site_url: HttpUrl
    email: str
    api_token: str


class JiraConnectionStatus(BaseModel):
    """Response body describing the current Jira connection, if any.

    Never includes the API token - only enough to confirm what's connected.
    """

    connected: bool
    site_url: str | None = None
    email: str | None = None
    account_id: str | None = None
    display_name: str | None = None


class TestRunRecordIn(BaseModel):
    """One record from parser.report_parser's output (see TestRecord.to_dict)."""

    spec_id: str
    title: str
    full_title: str
    file: str
    line: int
    column: int
    project: str
    tags: list[str] = []
    jira_keys: list[str] = []
    status: str
    duration_ms: int
    retry_count: int
    is_flaky: bool
    error_message: str | None = None


class SourceTestRecordIn(BaseModel):
    """One record from parser.static_parser or parser.feature_parser's
    output (see StaticTestRecord.to_dict / FeatureTestRecord.to_dict -
    identical shape, so one schema covers both)."""

    title: str
    full_title: str
    file: str
    line: int
    column: int
    tags: list[str] = []
    jira_keys: list[str] = []


class IngestRunRequest(BaseModel):
    """Request body for pushing test inventory data to the backend.

    Each field is independently optional and `None` by default: omitting a
    field means "this push doesn't concern that data" and leaves the
    corresponding backend data untouched, whereas an explicit `[]` means
    "this parser found zero tests" and does replace it (e.g. one CI job
    pushes run_report on every test run, while a separate job pushes
    static_specs only when source changes - neither should wipe the
    other's data just because it wasn't part of that particular push).
    """

    run_report: list[TestRunRecordIn] | None = None
    static_specs: list[SourceTestRecordIn] | None = None
    features: list[SourceTestRecordIn] | None = None


class IngestRunResponse(BaseModel):
    """Response body summarizing what an ingest push actually did."""

    run_id: int | None = None
    pushed_at: datetime | None = None
    run_report_count: int | None = None
    static_specs_count: int | None = None
    features_count: int | None = None
