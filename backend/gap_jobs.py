"""Gap analysis as a background job (issue #50).

A gap analysis is a real LLM request that can take 20+ seconds, and Forge
gives a single call only ~25 seconds with no retry. So the dashboard starts
it with one quick request and polls for the result with others:

- POST /api/coverage/gap-analysis/start  -> 202, row is `pending`, work queued
- GET  /api/coverage/gap-analysis/result -> the latest run: pending/done/failed

The result is kept per tenant, so reopening a requirement shows its last
analysis. A pending run older than STALE_AFTER is reported as failed: the
worker may have been stopped mid-run (a deploy, a machine restart) and
nothing would ever finish it. The synchronous POST /api/coverage/gap-analysis
remains for callers with no such time limit (the standalone dashboard).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db, get_session_factory
from backend.jira_access import require_jira_client
from backend.jira_client import JiraAuthError, JiraClient
from backend.jira_requirements import pull_requirement
from backend.models import GapAnalysis, Tenant, utcnow
from backend.schemas import GapAnalysisStatus
from backend.semantic_gap import GapAnalysisError, analyze_gap
from backend.tenancy import current_tenant
from backend.test_inventory import build_inventory, entries_for_jira_key

STALE_AFTER = timedelta(minutes=3)

router = APIRouter()


def _find(db: Session, tenant_id: int, jira_key: str) -> GapAnalysis | None:
    """This tenant's latest gap analysis for a requirement, if any."""
    return db.query(GapAnalysis).filter(GapAnalysis.tenant_id == tenant_id, GapAnalysis.jira_key == jira_key).first()


def _status_of(jira_key: str, row: GapAnalysis | None) -> GapAnalysisStatus:
    """Build the API view of a row (or "none" when there isn't one)."""
    if row is None:
        return GapAnalysisStatus(jira_key=jira_key, status="none")
    return GapAnalysisStatus(
        jira_key=jira_key,
        status=row.status,
        criteria=row.criteria,
        uncovered_count=row.uncovered_count,
        error=row.error,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _fail(row: GapAnalysis, message: str) -> None:
    """Mark a run failed with a message the user can read."""
    row.status = "failed"
    row.error = message
    row.criteria = None
    row.uncovered_count = None
    row.finished_at = utcnow()


def run_gap_job(session_factory: Callable[[], Session], tenant_id: int, client: JiraClient, jira_key: str) -> None:
    """Do the analysis and record the outcome on the tenant's row.

    Never raises: there is no caller left to tell, so every failure becomes a
    `failed` row the dashboard can show. Opens its own session because the
    request's is closed by the time a background task runs.
    """
    db = session_factory()
    try:
        row = _find(db, tenant_id, jira_key)
        if row is None:
            return
        try:
            requirement = pull_requirement(client, jira_key)
            if requirement is None:
                _fail(row, f"{jira_key} does not resolve in Jira")
            else:
                linked = entries_for_jira_key(build_inventory(db, tenant_id), jira_key)
                results = analyze_gap(requirement.acceptance_criteria, linked)
                row.status = "done"
                row.error = None
                row.criteria = [r.to_dict() for r in results]
                row.uncovered_count = sum(1 for r in results if not r.covered)
                row.finished_at = utcnow()
        except JiraAuthError:
            _fail(row, "Jira rejected the app's credentials")
        except GapAnalysisError as exc:
            _fail(row, str(exc))
        except Exception as exc:  # noqa: BLE001 - see docstring
            print(f"gap analysis failed for tenant {tenant_id} {jira_key}: {type(exc).__name__}", file=sys.stderr)
            _fail(row, f"Unexpected error ({type(exc).__name__})")
        db.commit()
    finally:
        db.close()


@router.post("/api/coverage/gap-analysis/start", response_model=GapAnalysisStatus, status_code=202)
def start_gap_analysis(
    project_key: str,
    jira_key: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    client: JiraClient = Depends(require_jira_client),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
) -> GapAnalysisStatus:
    """Start a gap analysis for jira_key and return at once (see module docstring).

    A run already in progress for the same requirement is returned as-is
    rather than started twice - a double click must not pay for two LLM calls.
    """
    if not jira_key.startswith(f"{project_key}-"):
        raise HTTPException(status_code=400, detail=f"{jira_key} does not belong to project {project_key}")

    row = _find(db, tenant.id, jira_key)
    if row is not None and row.status == "pending" and utcnow() - row.started_at < STALE_AFTER:
        return _status_of(jira_key, row)

    if row is None:
        row = GapAnalysis(tenant_id=tenant.id, project_key=project_key, jira_key=jira_key, status="pending")
        db.add(row)
    row.project_key = project_key
    row.status = "pending"
    row.criteria = None
    row.uncovered_count = None
    row.error = None
    row.started_at = utcnow()
    row.finished_at = None
    db.commit()

    background.add_task(run_gap_job, session_factory, tenant.id, client, jira_key)
    return _status_of(jira_key, row)


@router.get("/api/coverage/gap-analysis/result", response_model=GapAnalysisStatus)
def get_gap_analysis_result(
    jira_key: str, db: Session = Depends(get_db), tenant: Tenant = Depends(current_tenant)
) -> GapAnalysisStatus:
    """The latest gap analysis for jira_key: pending, done, failed - or "none".

    A pending run past STALE_AFTER is reported (and recorded) as failed, since
    whatever was running it is gone.
    """
    row = _find(db, tenant.id, jira_key)
    if row is not None and row.status == "pending" and utcnow() - row.started_at >= STALE_AFTER:
        _fail(row, "The analysis was interrupted before it finished - please run it again.")
        db.commit()
    return _status_of(jira_key, row)
