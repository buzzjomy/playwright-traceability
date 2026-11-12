"""Which Jira credentials a dashboard request uses (issue #41).

Order of preference, per request:

1. The Forge app system token Forge sent with the call - the product path.
   The app acts as its own bot user, so a customer never hands over an
   email or API token. Used whenever it's present, including for the
   deployment owner's own installation, so that path is exercised for real.
2. The tenant's own stored email + API token (a `JiraConnection`): local
   dev, the standalone frontend/, and the owner's env-bootstrapped one.

A tenant with neither gets a 400 - never another tenant's connection.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.jira_client import JiraClient
from backend.models import JiraConnection
from backend.tenancy import RequestContext, request_context


def jira_client_for(context: RequestContext, db: Session) -> JiraClient | None:
    """The Jira client this request should use, or None if it has no Jira access."""
    if context.system_token and context.jira_api_base_url:
        return JiraClient.with_bearer_token(context.jira_api_base_url, context.system_token)

    connection = db.query(JiraConnection).filter(JiraConnection.tenant_id == context.tenant.id).first()
    if connection is None:
        return None
    return JiraClient(connection.site_url, connection.email, connection.api_token)


def require_jira_client(context: RequestContext = Depends(request_context), db: Session = Depends(get_db)) -> JiraClient:
    """FastAPI dependency: the request's Jira client, or a 400 if it has no Jira access."""
    client = jira_client_for(context, db)
    if client is None:
        raise HTTPException(status_code=400, detail="No Jira connection configured yet")
    return client
