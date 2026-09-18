"""FastAPI app for the playwright-traceability backend.

Covers Milestone 2, issues #6 (Jira Cloud auth + connection setup), #7
(pulling requirement/story data), #10 (receiving Jira webhook events), and
#11 (polling fallback for instances without webhook access); Milestone 1,
issue #5 (an ingest endpoint for the CLI/GitHub Action snippet at
scripts/push_test_inventory.py to push parsed test inventory data to);
and Milestone 3, issues #12 (the reconciled test inventory view, the
first frontend/dashboard work in the repo - see frontend/) and #13 (the
requirement coverage view).

Run locally with:
    uvicorn backend.main:app --reload
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.auth import require_ingest_api_key, require_webhook_token
from backend.db import SessionLocal, get_db, init_db
from backend.drift_detection import detect_drift_for_issue
from backend.jira_client import JiraAuthError, JiraClient
from backend.jira_polling import poll_for_changes
from backend.jira_requirements import DEFAULT_ISSUE_TYPES, pull_requirement, pull_requirements
from backend.models import (
    JiraConnection,
    JiraPollState,
    JiraWebhookEvent,
    RequirementLink,
    SourceTestRecord,
    TestRun,
    TestRunRecord,
    utcnow,
)
from backend.requirement_coverage import build_coverage
from backend.requirement_links import list_requirement_links, mark_reviewed, sync_requirement_links
from backend.schemas import (
    CoverageResponse,
    GapAnalysisResponse,
    IngestRunRequest,
    IngestRunResponse,
    InventoryResponse,
    JiraConnectionCreate,
    JiraConnectionStatus,
    JiraPollResponse,
    JiraRequirementsResponse,
    JiraWebhookAck,
    JiraWebhookEventOut,
    RequirementLinkOut,
    RequirementLinksResponse,
)
from backend.semantic_gap import GapAnalysisError, LLMNotConfiguredError, analyze_gap
from backend.test_inventory import build_inventory, entries_for_jira_key


def _connect_jira(db: Session, site_url: str, email: str, api_token: str) -> tuple[JiraConnection, dict]:
    """Validate Jira credentials against the live API, replace any existing
    connection with them, and return the new connection row plus the
    validated `/myself` response. Raises JiraAuthError if Jira rejects them.
    Shared by the manual POST /api/jira/connection endpoint and the
    env-var bootstrap below, so both go through the same validate-then-
    persist path.
    """
    client = JiraClient(site_url, email, api_token)
    me = client.get_current_user()
    db.query(JiraConnection).delete()
    connection = JiraConnection(site_url=site_url, email=email, api_token=api_token)
    db.add(connection)
    db.commit()
    return connection, me


def _bootstrap_jira_connection_from_env() -> None:
    """Auto-create a Jira connection from JIRA_SITE_URL/JIRA_EMAIL/
    JIRA_API_TOKEN env vars on startup, if all three are set and no
    connection exists yet.

    Lets a self-hosted deployment configure Jira once via its environment
    (matching DATABASE_URL/INGEST_API_KEY/etc.) instead of always needing
    a manual POST /api/jira/connection call. Does nothing if any of the
    three env vars are missing or a connection already exists; logs a
    warning rather than raising if the env credentials are malformed or
    rejected by Jira, so a bad env var can't crash startup.
    """
    site_url = os.environ.get("JIRA_SITE_URL")
    email = os.environ.get("JIRA_EMAIL")
    api_token = os.environ.get("JIRA_API_TOKEN")
    if not (site_url and email and api_token):
        return

    db = SessionLocal()
    try:
        if db.query(JiraConnection).first() is not None:
            return
        try:
            normalized = JiraConnectionCreate(site_url=site_url, email=email, api_token=api_token)
        except ValidationError:
            print("JIRA_SITE_URL is not a valid URL - skipping auto-connect from environment", file=sys.stderr)
            return
        try:
            _connect_jira(db, str(normalized.site_url), normalized.email, normalized.api_token)
        except JiraAuthError:
            print(
                "JIRA_SITE_URL/JIRA_EMAIL/JIRA_API_TOKEN were rejected by Jira - skipping auto-connect",
                file=sys.stderr,
            )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create DB tables on startup if they don't exist yet, then try to
    auto-connect Jira from the environment (see
    _bootstrap_jira_connection_from_env)."""
    init_db()
    _bootstrap_jira_connection_from_env()
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
    try:
        connection, me = _connect_jira(db, str(payload.site_url), payload.email, payload.api_token)
    except JiraAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

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

    This records the event, then runs drift detection (issue #17) for the
    issue it names, if a Jira connection is configured - without one
    there's no way to re-pull the issue's live content to compare against.
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

    if event.issue_key:
        connection = db.query(JiraConnection).first()
        if connection is not None:
            client = JiraClient(connection.site_url, connection.email, connection.api_token)
            try:
                detect_drift_for_issue(db, client, event.issue_key)
            except Exception:
                # Recording that the webhook was delivered must succeed
                # even if re-checking Jira for drift can't (stale stored
                # credentials, Jira briefly unreachable, etc.) - the event
                # is still durably recorded either way, so nothing is lost.
                pass

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
        if issue.get("key"):
            detect_drift_for_issue(db, client, issue["key"])

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


@app.get("/api/coverage", response_model=CoverageResponse)
def get_requirement_coverage(
    project_key: str,
    issue_types: str | None = Query(default=None, description="Comma-separated, e.g. 'Story,Task'"),
    db: Session = Depends(get_db),
) -> CoverageResponse:
    """Return per-requirement test coverage for a Jira project (issue #13).

    Combines a live pull of the project's requirements (see
    /api/jira/requirements) with the reconciled test inventory (issue
    #12) - a requirement with linked_test_count 0 has no test verifying
    it at all. Requires a Jira connection to already be set up via POST
    /api/jira/connection. Not authenticated (read-only, local-only use).
    """
    connection = db.query(JiraConnection).first()
    if connection is None:
        raise HTTPException(status_code=400, detail="No Jira connection configured yet")

    client = JiraClient(connection.site_url, connection.email, connection.api_token)
    types = issue_types.split(",") if issue_types is not None else DEFAULT_ISSUE_TYPES
    inventory_entries = build_inventory(db)

    try:
        coverage = build_coverage(client, project_key, inventory_entries, issue_types=types)
    except JiraAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    covered_count = sum(1 for c in coverage if c.covered)
    return CoverageResponse(
        project_key=project_key,
        requirements=[c.to_dict() for c in coverage],
        total=len(coverage),
        covered=covered_count,
        uncovered=len(coverage) - covered_count,
    )


@app.get("/api/requirement-links", response_model=RequirementLinksResponse)
def get_requirement_links(
    project_key: str,
    issue_types: str | None = Query(default=None, description="Comma-separated, e.g. 'Story,Task'"),
    db: Session = Depends(get_db),
) -> RequirementLinksResponse:
    """Return every requirement<->test link for a Jira project, with its
    suspect-link state (Milestone 4, issue #18).

    Also syncs new links into existence (issue #16): any (jira_key, test)
    pair newly visible in the inventory gets hashed and stored here for
    the first time. Requires a Jira connection to already be set up via
    POST /api/jira/connection. Not authenticated (read-only, local-only
    use, same posture as the other GET endpoints).
    """
    connection = db.query(JiraConnection).first()
    if connection is None:
        raise HTTPException(status_code=400, detail="No Jira connection configured yet")

    client = JiraClient(connection.site_url, connection.email, connection.api_token)
    types = issue_types.split(",") if issue_types is not None else DEFAULT_ISSUE_TYPES
    inventory_entries = build_inventory(db)

    try:
        requirements = pull_requirements(client, project_key, issue_types=types)
    except JiraAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    sync_requirement_links(db, requirements, inventory_entries)
    db.commit()

    links = list_requirement_links(db, project_key, requirements, inventory_entries)
    return RequirementLinksResponse(project_key=project_key, links=[link.to_dict() for link in links])


@app.post("/api/requirement-links/{link_id}/reviewed", response_model=RequirementLinkOut)
def review_requirement_link(link_id: int, db: Session = Depends(get_db)) -> dict:
    """Manually clear a link's Suspect state by re-snapshotting it against
    Jira's current content (Milestone 4, issue #20).

    The only way a Suspect link is ever cleared - deliberately no
    auto-clear path, per CLAUDE.md's differentiator: a human has to look
    at the requirement's current content and decide the linked test still
    covers it. Requires a Jira connection (to re-pull that content) and
    fails if the link's Jira key no longer resolves (an "orphaned" link -
    there's nothing current to review it against).
    """
    link = db.get(RequirementLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="No such requirement link")

    connection = db.query(JiraConnection).first()
    if connection is None:
        raise HTTPException(status_code=400, detail="No Jira connection configured yet")

    client = JiraClient(connection.site_url, connection.email, connection.api_token)
    try:
        requirement = pull_requirement(client, link.jira_key)
    except JiraAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if requirement is None:
        raise HTTPException(
            status_code=400, detail=f"{link.jira_key} no longer resolves in Jira - nothing to review against"
        )

    mark_reviewed(link, requirement, utcnow())
    db.commit()
    db.refresh(link)
    return {
        "id": link.id,
        "jira_key": link.jira_key,
        "test_file": link.test_file,
        "test_title": link.test_title,
        "state": link.state,
        "change_summary": link.change_summary,
        "linked_at": link.linked_at.isoformat(),
        "last_reviewed_at": link.last_reviewed_at.isoformat() if link.last_reviewed_at else None,
    }


@app.post("/api/coverage/gap-analysis", response_model=GapAnalysisResponse)
def get_gap_analysis(project_key: str, jira_key: str, db: Session = Depends(get_db)) -> GapAnalysisResponse:
    """Judge, per acceptance criterion, whether jira_key's linked tests
    actually cover it (Milestone 5, issues #21/#22) - the differentiator
    over coverage's "does at least one test exist" (issue #13).

    On-demand per requirement (not run automatically for a whole project)
    since each call is a real LLM request. Requires a Jira connection (to
    re-pull the requirement's current acceptance criteria) and
    `ANTHROPIC_API_KEY` - there's no non-LLM fallback for this endpoint,
    unlike issue #19's enrichment-only change summary.
    """
    if not jira_key.startswith(f"{project_key}-"):
        raise HTTPException(status_code=400, detail=f"{jira_key} does not belong to project {project_key}")

    connection = db.query(JiraConnection).first()
    if connection is None:
        raise HTTPException(status_code=400, detail="No Jira connection configured yet")

    client = JiraClient(connection.site_url, connection.email, connection.api_token)
    try:
        requirement = pull_requirement(client, jira_key)
    except JiraAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if requirement is None:
        raise HTTPException(status_code=404, detail=f"{jira_key} does not resolve in Jira")

    linked_tests = entries_for_jira_key(build_inventory(db), jira_key)

    try:
        results = analyze_gap(requirement.acceptance_criteria, linked_tests)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GapAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    uncovered_count = sum(1 for r in results if not r.covered)
    return GapAnalysisResponse(
        jira_key=jira_key,
        criteria=[r.to_dict() for r in results],
        uncovered_count=uncovered_count,
    )
