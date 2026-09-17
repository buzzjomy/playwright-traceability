"""Shared API-key auth for endpoints meant to be called externally (e.g.
from a GitHub Action, or Jira itself), unlike the local-only Jira setup
endpoints.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, Query


def require_ingest_api_key(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: require a valid `Authorization: Bearer <key>` header.

    Fails closed if INGEST_API_KEY isn't configured on the server at all,
    rather than silently accepting every request when misconfigured.
    """
    expected_key = os.environ.get("INGEST_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="Server is not configured with INGEST_API_KEY")

    if authorization != f"Bearer {expected_key}":
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


def require_webhook_token(token: str = Query(default="")) -> None:
    """FastAPI dependency: require a valid `?token=...` query param.

    A query param, not a header, because Jira Cloud's classic webhook
    admin UI (Settings > System > WebHooks) - the only registration path
    available without a Connect/OAuth 2.0 app, see main.py's
    receive_jira_webhook - only lets you configure a plain URL, with no
    way to add custom headers. Embed the secret directly in that URL
    instead, e.g. https://host/api/webhooks/jira?token=... Fails closed
    if JIRA_WEBHOOK_SECRET isn't configured on the server at all.
    """
    expected_token = os.environ.get("JIRA_WEBHOOK_SECRET")
    if not expected_token:
        raise HTTPException(status_code=500, detail="Server is not configured with JIRA_WEBHOOK_SECRET")

    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
