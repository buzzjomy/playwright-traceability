"""Forge-driven change detection (issue #41): the pieces that keep Suspect
links current for a Marketplace customer with no webhook to configure and no
polling script to run.

Two triggers call this backend directly (see forge-app/manifest.yml), each
carrying a fresh app system token - nothing is ever stored:

- an `avi:jira:updated:issue` event: drift detection for that one issue,
  within seconds of an edit;
- an hourly scheduled trigger: a safety-net poll of every project the
  tenant has links in, in case an event was missed.

Forge gives an event delivery only 5 seconds and retries any non-2xx up to 4
times, while drift detection can mean a Jira call plus an LLM summary - so
both routes acknowledge immediately and do the work after the response.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from backend.db import get_db, get_session_factory
from backend.drift_detection import detect_drift_for_issue
from backend.jira_access import jira_client_for
from backend.jira_client import JiraClient
from backend.jira_polling import poll_for_changes
from backend.models import JiraPollState, JiraWebhookEvent, RequirementLink, utcnow
from backend.tenancy import RequestContext, request_context

FORGE_EVENT_TYPE = "forge:avi:jira:updated:issue"

router = APIRouter()


def poll_project(db: Session, tenant_id: int, client: JiraClient, project_key: str) -> tuple[bool, int, datetime]:
    """Poll one project for issues changed since this tenant's last poll,
    record an event per change and run drift detection on each (issue #11).

    Returns (is_first_poll, changed_issue_count, polled_at). Does not
    commit - the caller shares a transaction with whatever else it does.
    A first poll only sets the baseline: it can't know what changed before it.
    """
    poll_state = (
        db.query(JiraPollState)
        .filter(JiraPollState.tenant_id == tenant_id, JiraPollState.project_key == project_key)
        .first()
    )
    since = poll_state.last_polled_at if poll_state else None
    # Captured before the search runs, not after, so a change that lands
    # mid-poll is caught on the *next* poll rather than silently skipped.
    poll_started_at = utcnow()

    changed_issues = poll_for_changes(client, project_key, since, poll_started_at)
    for issue in changed_issues:
        db.add(
            JiraWebhookEvent(
                tenant_id=tenant_id,
                issue_key=issue.get("key", ""),
                webhook_event="jira:issue_polled",
                changelog=None,
                raw_payload=issue,
            )
        )
        if issue.get("key"):
            detect_drift_for_issue(db, tenant_id, client, issue["key"])

    if poll_state is None:
        db.add(JiraPollState(tenant_id=tenant_id, project_key=project_key, last_polled_at=poll_started_at))
    else:
        poll_state.last_polled_at = poll_started_at
    return since is None, len(changed_issues), poll_started_at


def tracked_project_keys(db: Session, tenant_id: int) -> list[str]:
    """Projects worth polling for a tenant: every one it already has links
    in or has polled before. (A project with no links has nothing to go
    Suspect, so there's nothing to watch there.)"""
    keys = {
        jira_key.split("-", 1)[0]
        for (jira_key,) in db.query(RequirementLink.jira_key).filter(RequirementLink.tenant_id == tenant_id).distinct()
    }
    keys |= {k for (k,) in db.query(JiraPollState.project_key).filter(JiraPollState.tenant_id == tenant_id)}
    return sorted(k for k in keys if k)


def issue_key_from_event(body: object) -> str | None:
    """The issue key in a Jira issue event body, tolerating it being nested
    under `payload` (the delivery envelope's exact shape isn't pinned down)."""
    if not isinstance(body, dict):
        return None
    for candidate in (body, body.get("payload")):
        if isinstance(candidate, dict):
            issue = candidate.get("issue")
            if isinstance(issue, dict) and isinstance(issue.get("key"), str):
                return issue["key"]
    return None


def process_issue_updated(session_factory: Callable[[], Session], tenant_id: int, client: JiraClient, issue_key: str) -> None:
    """Background work for an issue event: drift detection for one issue.
    Never raises - there's no caller left to tell, and it must not take the
    worker down; a failure is logged and the hourly poll is the backstop."""
    db = session_factory()
    try:
        detect_drift_for_issue(db, tenant_id, client, issue_key)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"drift detection failed for tenant {tenant_id} issue {issue_key}: {type(exc).__name__}", file=sys.stderr)
    finally:
        db.close()


def process_scheduled_poll(session_factory: Callable[[], Session], tenant_id: int, client: JiraClient) -> None:
    """Background work for the hourly trigger: poll each tracked project.
    One project failing doesn't stop the rest."""
    db = session_factory()
    try:
        for project_key in tracked_project_keys(db, tenant_id):
            try:
                poll_project(db, tenant_id, client, project_key)
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                print(f"scheduled poll failed for tenant {tenant_id} project {project_key}: {type(exc).__name__}", file=sys.stderr)
    finally:
        db.close()


@router.post("/api/forge/events/issue-updated")
def receive_issue_updated(
    body: dict,
    background: BackgroundTasks,
    context: RequestContext = Depends(request_context),
    db: Session = Depends(get_db),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
) -> dict:
    """Receive an `avi:jira:updated:issue` event from Forge (see module docstring).

    Records a minimal audit row (the issue key only - not the event's user
    data) and queues drift detection. Always 2xx once the token verified, even
    with no Jira access: Forge would just retry an event we can't act on.
    """
    issue_key = issue_key_from_event(body)
    db.add(
        JiraWebhookEvent(
            tenant_id=context.tenant.id,
            issue_key=issue_key or "",
            webhook_event=FORGE_EVENT_TYPE,
            changelog=None,
            raw_payload={"issue_key": issue_key},
        )
    )
    db.commit()

    client = jira_client_for(context, db)
    if issue_key and client is not None:
        background.add_task(process_issue_updated, session_factory, context.tenant.id, client, issue_key)
    return {"received": True, "issue_key": issue_key, "queued": bool(issue_key and client is not None)}


@router.post("/api/forge/scheduled/poll")
def receive_scheduled_poll(
    background: BackgroundTasks,
    context: RequestContext = Depends(request_context),
    db: Session = Depends(get_db),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
) -> dict:
    """Receive the hourly scheduled trigger from Forge: queue a poll of this
    tenant's tracked projects. Needs the system token Forge sends with it."""
    client = jira_client_for(context, db)
    if client is not None:
        background.add_task(process_scheduled_poll, session_factory, context.tenant.id, client)
    return {"queued": client is not None}
