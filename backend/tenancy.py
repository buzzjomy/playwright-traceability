"""Tenant resolution (Multi-Tenancy milestone, issues #40/#42).

Every row the dashboard reads or writes belongs to a Tenant, and every
route resolves which one *before* touching data. There are two ways in:

- A Forge request (the app's Remote calls): the tenant is the
  `app.installationId` of the verified Forge Invocation Token. Never taken
  from a header, query param or body the caller controls.
- A CI upload (`/api/ingest/run`, `/api/jira/poll`): the tenant owns the
  Bearer key presented (a per-tenant key, issue #42).

With REQUIRE_FORGE_AUTH off (local dev, the standalone frontend/
dashboard) everything resolves to the single LOCAL tenant, so those paths
behave exactly as they did before multi-tenancy.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.forge_auth import forge_auth_enabled, verify_forge_invocation_token
from backend.models import LOCAL_TENANT_KEY, Tenant

INGEST_KEY_PREFIX = "pwt_"


def hash_ingest_key(key: str) -> str:
    """SHA-256 hex digest of an ingest key - what's stored instead of the key.

    The keys are 256 bits of randomness, so a fast unsalted hash is
    appropriate here (unlike a human-chosen password).
    """
    return hashlib.sha256(key.encode()).hexdigest()


def generate_ingest_key() -> str:
    """A new random ingest key. Shown to its owner once, then only its hash is kept."""
    return INGEST_KEY_PREFIX + secrets.token_urlsafe(32)


def get_or_create_tenant(db: Session, key: str, cloud_id: str | None = None) -> Tenant:
    """Return the tenant with this key, creating it on first sight."""
    tenant = db.query(Tenant).filter(Tenant.key == key).first()
    if tenant is None:
        tenant = Tenant(key=key, cloud_id=cloud_id)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    return tenant


def get_local_tenant(db: Session) -> Tenant:
    """The single tenant used when Forge auth is off (and for the legacy webhook)."""
    return get_or_create_tenant(db, LOCAL_TENANT_KEY)


def current_tenant(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Tenant:
    """FastAPI dependency: the tenant making this dashboard (Forge) request.

    With REQUIRE_FORGE_AUTH off this is the LOCAL tenant. With it on, the
    token is verified and its installation id picks the tenant; a token
    without one is rejected rather than defaulted - falling back to a
    shared tenant would be exactly the cross-customer leak this prevents.

    LOCAL_TENANT_INSTALLATION_ID is an explicit opt-in for the deployment
    OWNER's own installation: that one installation is served the LOCAL
    tenant (where the env-bootstrapped Jira connection and any data pushed
    with the legacy global key live). It exists only until issues #41/#42
    give every installation its own Jira access and ingest key.
    """
    if not forge_auth_enabled():
        return get_local_tenant(db)

    claims = verify_forge_invocation_token(authorization)
    installation_id = (claims.get("app") or {}).get("installationId")
    if not installation_id:
        raise HTTPException(status_code=401, detail="Forge Invocation Token has no installation id")

    if installation_id == os.environ.get("LOCAL_TENANT_INSTALLATION_ID"):
        return get_local_tenant(db)

    cloud_id = (claims.get("context") or {}).get("cloudId")
    return get_or_create_tenant(db, installation_id, cloud_id)


def ingest_tenant(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Tenant:
    """FastAPI dependency: the tenant owning the `Authorization: Bearer <key>`
    presented on a CI upload or poll trigger.

    Looks the key up by hash. The legacy global INGEST_API_KEY env var is
    still honoured and maps to the LOCAL tenant, so existing pushes keep
    working until they move to per-tenant keys. Fails closed: no match is
    a 401, never a default tenant. Constant-time compare for the legacy key.
    """
    presented = (authorization or "").removeprefix("Bearer ").strip() if (authorization or "").startswith("Bearer ") else ""
    if presented:
        tenant = db.query(Tenant).filter(Tenant.ingest_key_hash == hash_ingest_key(presented)).first()
        if tenant is not None:
            return tenant

        legacy_key = os.environ.get("INGEST_API_KEY")
        if legacy_key and hmac.compare_digest(presented, legacy_key):
            return get_local_tenant(db)

    raise HTTPException(status_code=401, detail="Missing or invalid API key")
