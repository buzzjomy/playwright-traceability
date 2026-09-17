"""FastAPI app for the playwright-traceability backend.

Covers Milestone 2, issues #6 (Jira Cloud auth + connection setup), #7
(pulling requirement/story data), #10 (receiving Jira webhook events), and
#11 (polling fallback for instances without webhook access); Milestone 1,
issue #5 (an ingest endpoint for the CLI/GitHub Action snippet at
scripts/push_test_inventory.py to push parsed test inventory data to);
and Milestone 3, issue #12 (the reconciled test inventory view, the first
frontend/dashboard work in the repo - see frontend/).

Run locally with:
    uvicorn backend.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from backend.auth import require_ingest_api_key, require_webhook_token
from backend.db import get_db, init_db
from backend.jira_client import JiraAuthError, JiraClient
from backend.jira_polling import poll_for_changes
from backend.jira_requirements import DEFAULT_ISSUE_TYPES, pull_requirements
from backend.models import (
    JiraConnection,
    JiraPollState,
    JiraWebhookEvent,
    SourceTestRecord,
    TestRun,
    TestRunRecord,
    utcnow,
)
from backend.schemas import (
    IngestRunRequest,
    IngestRunResponse,
    InventoryResponse,
    JiraConnectionCreate,
    JiraConnectionStatus,
    JiraPollResponse,
    JiraRequirementsResponse,
    JiraWebhookAck,
    JiraWebhookEventOut,
)
from backend.test_inventory import build_inventory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create DB tables on startup if they don't exist yet."""
    init_db()
    yield


app = FastAPI(title="Playwright Traceability Backend", lifespan=lifespan)


def _status_from_connection(connection: JiraConnection) -> JiraConnectionStatus:
    """Re-validate a stored connection against the live Jira API and build its status."""
    client = JiraClient(connection.site_url, connection.email, connection.api_token)
    try:
        me = client.get_current_user()
    except JiraAuthError:
        return JiraConnectionStatus(connected=False, site_url=connection.site_url, email=connection.email)

    return JiraConnectionStatus(
        connected=True,
        site_url=connection.site_url,
        email=connection.email,
        account_id=me.get("accountId"),
        display_name=me.get("displayName"),
    )


@app.post("/api/jira/connection", response_model=JiraConnectionStatus)
def create_jira_connection(payload: JiraConnectionCreate, db: Session = Depends(get_db)) -> JiraConnectionStatus:
    """Validate the given Jira credentials against the real API, then store them.

    Replaces any existing connection - this is single-tenant for now.
    """
    client = JiraClient(str(payload.site_url), payload.email, payload.api_token)
    try:
        me = client.get_current_user()
    except JiraAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    db.query(JiraConnection).delete()
    connection = JiraConnection(site_url=str(payload.site_url), email=payload.email, api_token=payload.api_token)
    db.add(connection)
    db.commit()

    return JiraConnectionStatus(
        connected=True,
        site_url=connection.site_url,
        email=connection.email,
        account_id=me.get("accountId"),
        display_name=me.get("displayName"),
    )


@app.get("/api/jira/connection", response_model=JiraConnectionStatus)
def get_jira_connection(db: Session = Depends(get_db)) -> JiraConnectionStatus:
    """Return the current Jira connection status, if one has been set up.

    Never returns the stored API token.
    """
    connection = db.query(JiraConnection).first()
    if connection is None:
        return JiraConnectionStatus(connected=False)
    return _status_from_connection(connection)


@app.delete("/api/jira/connection", status_code=204)
def delete_jira_connection(db: Session = Depends(get_db)) -> None:
    """Remove the current Jira connection, if any."""
    db.query(JiraConnection).delete()
    db.commit()


@app.get("/api/jira/requirements", response_model=JiraRequirementsResponse)
def get_jira_requirements(
    project_key: str,
    issue_types: str | None = Query(default=None, description="Comma-separated, e.g. 'Story,Task'"),
    db: Session = Depends(get_db),
) -> JiraRequirementsResponse:
    """Pull every Story/Task (by default) in a Jira project as requirements.

    Live-fetches from Jira on every call - no caching or persistence yet.
    Requires a Jira connection to already be set up via POST
    /api/jira/connection.
    """
    connection = db.query(JiraConnection).first()
    if connection is None:
        raise HTTPException(status_code=400, detail="No Jira connection configured yet")

    client = JiraClient(connection.site_url, connection.email, connection.api_token)
    types = issue_types.split(",") if issue_types is not None else DEFAULT_ISSUE_TYPES

    try:
        requirements = pull_requirements(client, project_key, issue_types=types)
    except JiraAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return JiraRequirementsResponse(
        project_key=project_key,
        requirements=[r.to_dict() for r in requirements],
    )


def _replace_source_records(db: Session, source_type: str, records: list) -> int:
    """Wipe and re-insert every SourceTestRecord of one source_type ("static"
    or "feature"), leaving the other source_type's rows untouched."""
    db.query(SourceTestRecord).filter(SourceTestRecord.source_type == source_type).delete()
    for record in records:
        db.add(SourceTestRecord(source_type=source_type, **record.model_dump()))
    return len(records)


@app.post("/api/ingest/run", response_model=IngestRunResponse, dependencies=[Depends(require_ingest_api_key)])
def ingest_run(payload: IngestRunRequest, db: Session = Depends(get_db)) -> IngestRunResponse:
    """Ingest test inventory data pushed by scripts/push_test_inventory.py.

    Each of run_report/static_specs/features is independently optional -
    see IngestRunRequest's docstring for the None-vs-[] semantics. Run
    report data is always appended as a new TestRun (kept for future trend
    queries); static/feature source data replaces the prior snapshot for
    just that source_type.
    """
    response = IngestRunResponse()

    if payload.run_report is not None:
        run = TestRun()
        db.add(run)
        db.flush()  # assigns run.id without committing yet
        for record in payload.run_report:
            db.add(TestRunRecord(run_id=run.id, **record.model_dump()))
        response.run_id = run.id
        response.pushed_at = run.pushed_at
        response.run_report_count = len(payload.run_report)

    if payload.static_specs is not None:
        response.static_specs_count = _replace_source_records(db, "static", payload.static_specs)

    if payload.features is not None:
        response.features_count = _replace_source_records(db, "feature", payload.features)

    db.commit()
    return response


@app.post("/api/webhooks/jira", response_model=JiraWebhookAck, dependencies=[Depends(require_webhook_token)])
def receive_jira_webhook(payload: dict, db: Session = Depends(get_db)) -> JiraWebhookAck:
    """Receive one Jira webhook delivery (issue #10), e.g. jira:issue_updated.

    Jira Cloud's webhook self-registration REST API (POST
    /rest/api/3/webhook) rejects Basic Auth outright - confirmed against a
    real site, it returns 403 "Only Connect and OAuth 2.0 apps can use
    this operation." So this endpoint is meant to be registered manually
    by a Jira admin via Settings > System > WebHooks (the older "classic"
    webhook feature), which needs no OAuth - see backend/README.md for the
    exact setup steps and why the secret is a query param, not a header.

    This just records the event; it doesn't itself decide anything
    changed or flip any Suspect state - that's issue #17 (drift
    detection), which will read from this table.
    """
    issue = payload.get("issue") or {}
    webhook_event = payload.get("webhookEvent", "")

    event = JiraWebhookEvent(
        issue_key=issue.get("key", ""),
        webhook_event=webhook_event,
        changelog=payload.get("changelog"),
        raw_payload=payload,
    )
    db.add(event)
    db.commit()

    return JiraWebhookAck(received=True, issue_key=event.issue_key, webhook_event=webhook_event)


@app.get("/api/webhooks/jira/events", response_model=list[JiraWebhookEventOut])
def list_jira_webhook_events(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)) -> list[JiraWebhookEvent]:
    """List the most recently received webhook events, newest first.

    For visibility/debugging while there's no dashboard yet; not
    authenticated (read-only, local-only use, same posture as the Jira
    connection endpoints).
    """
    return (
        db.query(JiraWebhookEvent)
        .order_by(JiraWebhookEvent.received_at.desc())
        .limit(limit)
        .all()
    )


@app.post("/api/jira/poll", response_model=JiraPollResponse, dependencies=[Depends(require_ingest_api_key)])
def poll_jira_for_changes(project_key: str, db: Session = Depends(get_db)) -> JiraPollResponse:
    """Poll Jira for issues changed since the last poll (issue #11).

    Meant to be triggered periodically by an external scheduler (cron, a
    scheduled GitHub Action, etc.) - there's no in-process background
    scheduler here, same posture as scripts/push_test_inventory.py.
    Reuses INGEST_API_KEY auth rather than adding a third shared secret.

    Records one JiraWebhookEvent per changed issue (webhook_event =
    "jira:issue_polled", changelog = None - a JQL search returns current
    state, not a diff - see jira_polling.py), so issue #17 (drift
    detection) can consume poll-sourced and webhook-sourced events
    through the same table.
    """
    connection = db.query(JiraConnection).first()
    if connection is None:
        raise HTTPException(status_code=400, detail="No Jira connection configured yet")

    poll_state = db.query(JiraPollState).filter(JiraPollState.project_key == project_key).first()
    since = poll_state.last_polled_at if poll_state else None
    # Captured before the search runs, not after, so a change that lands
    # mid-poll is caught on the *next* poll rather than silently skipped.
    poll_started_at = utcnow()

    client = JiraClient(connection.site_url, connection.email, connection.api_token)
    try:
        changed_issues = poll_for_changes(client, project_key, since, poll_started_at)
    except JiraAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    for issue in changed_issues:
        db.add(
            JiraWebhookEvent(
                issue_key=issue.get("key", ""),
                webhook_event="jira:issue_polled",
                changelog=None,
                raw_payload=issue,
            )
        )

    if poll_state is None:
        poll_state = JiraPollState(project_key=project_key, last_polled_at=poll_started_at)
        db.add(poll_state)
    else:
        poll_state.last_polled_at = poll_started_at
    db.commit()

    return JiraPollResponse(
        project_key=project_key,
        is_first_poll=since is None,
        changed_issue_count=len(changed_issues),
        polled_at=poll_started_at,
    )


@app.get("/api/inventory", response_model=InventoryResponse)
def get_test_inventory(db: Session = Depends(get_db)) -> InventoryResponse:
    """Return the reconciled test inventory (issue #12).

    Combines TestRunRecord (from pushed runs) and SourceTestRecord (from
    static .spec.ts/.feature scans) by matching (file, title) - see
    backend/test_inventory.py for the reconciliation rules. Not
    authenticated (read-only, local-only use, same posture as the other
    GET endpoints).
    """
    return InventoryResponse(entries=[e.to_dict() for e in build_inventory(db)])
