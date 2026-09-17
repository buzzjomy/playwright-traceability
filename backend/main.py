"""FastAPI app for the playwright-traceability backend.

Covers Milestone 2, issues #6 (Jira Cloud auth + connection setup) and #7
(pulling requirement/story data), plus Milestone 1, issue #5 (an ingest
endpoint for the CLI/GitHub Action snippet at
scripts/push_test_inventory.py to push parsed test inventory data to).
Later issues (linking tests, the dashboard) build on this same app.

Run locally with:
    uvicorn backend.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from backend.auth import require_ingest_api_key
from backend.db import get_db, init_db
from backend.jira_client import JiraAuthError, JiraClient
from backend.jira_requirements import DEFAULT_ISSUE_TYPES, pull_requirements
from backend.models import JiraConnection, SourceTestRecord, TestRun, TestRunRecord
from backend.schemas import (
    IngestRunRequest,
    IngestRunResponse,
    JiraConnectionCreate,
    JiraConnectionStatus,
    JiraRequirementsResponse,
)


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
