"""FastAPI app for the playwright-traceability backend.

Currently covers Milestone 2, issue #6: authenticating against a Jira
Cloud site (email + API token) and persisting that connection. Later
issues (pulling requirement data, linking tests, the dashboard) build on
this same app.

Run locally with:
    uvicorn backend.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db, init_db
from backend.jira_client import JiraAuthError, JiraClient
from backend.models import JiraConnection
from backend.schemas import JiraConnectionCreate, JiraConnectionStatus


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
