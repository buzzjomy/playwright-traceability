"""Shared-secret auth for the one endpoint Jira itself calls (the classic
webhook). CI upload keys are per-tenant and live in tenancy.py.
"""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Query


def require_webhook_token(token: str = Query(default="")) -> None:
    """FastAPI dependency: require a valid `?token=...` query param.

    A query param, not a header, because Jira Cloud's classic webhook
    admin UI (Settings > System > WebHooks) - the only registration path
    available without a Connect/OAuth 2.0 app, see main.py's
    receive_jira_webhook - only lets you configure a plain URL, with no
    way to add custom headers. Embed the secret directly in that URL
    instead, e.g. https://host/api/webhooks/jira?token=... Fails closed
    if JIRA_WEBHOOK_SECRET isn't configured on the server at all. Uses a
    constant-time comparison so a caller can't recover the token byte by
    byte from response-timing differences.
    """
    expected_token = os.environ.get("JIRA_WEBHOOK_SECRET")
    if not expected_token:
        raise HTTPException(status_code=500, detail="Server is not configured with JIRA_WEBHOOK_SECRET")

    if not hmac.compare_digest(token, expected_token):
        raise HTTPException(status_code=401, detail="Invalid webhook token")
