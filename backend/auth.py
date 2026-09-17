"""Shared API-key auth for endpoints meant to be called externally (e.g.
from a GitHub Action), unlike the local-only Jira setup endpoints.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


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
