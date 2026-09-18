"""Pydantic request/response models for the backend API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


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


class JiraRequirementOut(BaseModel):
    """One requirement/story pulled from Jira (see JiraRequirement.to_dict)."""

    key: str
    summary: str
    description_text: str
    acceptance_criteria: list[str] = []


class JiraRequirementsResponse(BaseModel):
    """Response body for GET /api/jira/requirements."""

    project_key: str
    requirements: list[JiraRequirementOut]


class JiraWebhookEventOut(BaseModel):
    """One received webhook event (see JiraWebhookEvent)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    received_at: datetime
    issue_key: str
    webhook_event: str
    changelog: dict | None = None


class JiraWebhookAck(BaseModel):
    """Response body for POST /api/webhooks/jira."""

    received: bool
    issue_key: str
    webhook_event: str


class JiraPollResponse(BaseModel):
    """Response body for POST /api/jira/poll."""

    project_key: str
    is_first_poll: bool
    changed_issue_count: int
    polled_at: datetime


class TrendPointOut(BaseModel):
    """One historical run outcome for a test (see TrendPoint.to_dict)."""

    run_id: int
    pushed_at: datetime
    status: str


class InventoryEntryOut(BaseModel):
    """One reconciled test inventory row (see InventoryEntry.to_dict)."""

    file: str
    title: str
    full_title: str
    project: str | None = None
    status: str | None = None
    tags: list[str] = []
    jira_keys: list[str] = []
    in_source: bool
    has_run: bool
    history: list[TrendPointOut] = []
    is_flaky: bool = False


class InventoryResponse(BaseModel):
    """Response body for GET /api/inventory."""

    entries: list[InventoryEntryOut]


class CoverageEntryOut(BaseModel):
    """One requirement's test coverage (see CoverageEntry.to_dict)."""

    key: str
    summary: str
    linked_test_count: int
    covered: bool


class CoverageResponse(BaseModel):
    """Response body for GET /api/coverage."""

    project_key: str
    requirements: list[CoverageEntryOut]
    total: int
    covered: int
    uncovered: int


class RequirementLinkOut(BaseModel):
    """One requirement<->test link with its effective state (see RequirementLinkView.to_dict)."""

    id: int
    jira_key: str
    test_file: str
    test_title: str
    state: str
    change_summary: str | None = None
    linked_at: str
    last_reviewed_at: str | None = None


class RequirementLinksResponse(BaseModel):
    """Response body for GET /api/requirement-links."""

    project_key: str
    links: list[RequirementLinkOut]
