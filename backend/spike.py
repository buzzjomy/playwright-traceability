"""SPIKE (issue #41) - throwaway. Answers: does a Forge Remote request made
with invokeRemote carry the app system token, and does that token work
against Jira as the app's bot user? Delete once #41 is built.

Reports facts about the token (present? expiry? what Jira says when we use
it) and NEVER returns the token itself.
"""

from __future__ import annotations

import jwt
import requests
from fastapi import APIRouter, Header

from backend.forge_auth import verify_forge_invocation_token

router = APIRouter()


def _token_expiry_seconds(token: str) -> int | None:
    """Seconds until the token's exp claim, read WITHOUT verifying it - only
    to report remaining validity, never to trust the token."""
    try:
        exp = jwt.decode(token, options={"verify_signature": False}).get("exp")
    except jwt.PyJWTError:
        return None
    if not isinstance(exp, (int, float)):
        return None
    import time

    return int(exp - time.time())


@router.get("/api/spike/system-token")
def probe_system_token(
    authorization: str | None = Header(default=None),
    x_forge_oauth_system: str | None = Header(default=None),
) -> dict:
    """Probe the system token Forge attached to this request (see module docstring)."""
    claims = verify_forge_invocation_token(authorization)
    app = claims.get("app") or {}
    api_base_url = app.get("apiBaseUrl")

    result: dict = {
        "token_header_present": x_forge_oauth_system is not None,
        "token_is_jwt": None,
        "token_expires_in_seconds": None,
        "api_base_url": api_base_url,
        "installation_id": app.get("installationId"),
        "fit_claim_keys": sorted(claims.keys()),
        "jira_status": None,
        "jira_projects": None,
        "jira_error": None,
    }
    if x_forge_oauth_system is None or not api_base_url:
        return result

    expires_in = _token_expiry_seconds(x_forge_oauth_system)
    result["token_is_jwt"] = expires_in is not None
    result["token_expires_in_seconds"] = expires_in

    try:
        response = requests.get(
            f"{api_base_url}/rest/api/3/project/search",
            params={"maxResults": 10},
            headers={"Authorization": f"Bearer {x_forge_oauth_system}", "Accept": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        result["jira_error"] = f"request failed: {type(exc).__name__}"
        return result

    result["jira_status"] = response.status_code
    if response.ok:
        result["jira_projects"] = [p.get("key") for p in response.json().get("values", [])]
    else:
        result["jira_error"] = response.text[:300]
    return result
