"""Validates Forge Invocation Tokens (FIT) on requests proxied through a
Forge app's Remote (Milestone 7, issue #25).

A Forge app calling this backend as a Remote attaches a FIT - a JWT signed
by Atlassian, not a shared secret we hand out ourselves - as
`Authorization: Bearer <token>`. Unlike auth.py's two constant-time
string comparisons, verifying one means fetching Atlassian's published
JWKS and checking the token's signature plus several claims; there's no
official Python reference for this (Atlassian ships Node.js/jose and
Java/Spring Boot reference Remote backends only), so this is hand-rolled
against PyJWT.

Gated behind REQUIRE_FORGE_AUTH (default off) rather than always-on, so
existing self-hosted deployments of frontend/ (which call these same
routes unauthenticated) aren't broken by installing a Forge app
somewhere else entirely - this is an explicit per-deployment opt-in.
"""

from __future__ import annotations

import os

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

FORGE_JWKS_URL = "https://forge.cdn.prod.atlassian-dev.net/.well-known/jwks.json"
EXPECTED_ISSUER = "forge/invocation-token"

# Module-level so the fetched JWKS is cached across requests, not
# re-fetched from Atlassian on every single call.
_jwk_client = PyJWKClient(FORGE_JWKS_URL, cache_keys=True)


def require_forge_invocation_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: require a valid Forge Invocation Token.

    A no-op if REQUIRE_FORGE_AUTH isn't set to "true" - this feature is
    off by default so it never affects a deployment that isn't actually
    fronted by a Forge app. Once enabled, fails closed (500) if
    FORGE_APP_ID isn't configured, same posture as auth.py's two
    dependencies.
    """
    if os.environ.get("REQUIRE_FORGE_AUTH", "false").lower() != "true":
        return

    expected_app_id = os.environ.get("FORGE_APP_ID")
    if not expected_app_id:
        raise HTTPException(status_code=500, detail="REQUIRE_FORGE_AUTH is true but FORGE_APP_ID is not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Forge Invocation Token")

    token = authorization.removeprefix("Bearer ")
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=expected_app_id,
            issuer=EXPECTED_ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Forge Invocation Token: {exc}") from exc

    # Atlassian's own guidance: re-check the app id against our own
    # trusted config rather than relying solely on the aud claim already
    # having matched above.
    if claims.get("app", {}).get("id") != expected_app_id:
        raise HTTPException(status_code=401, detail="Forge Invocation Token app id mismatch")
