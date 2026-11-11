import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from backend.forge_auth import EXPECTED_ISSUER, require_forge_invocation_token

APP_ID = "test-app-id"


def _keypair():
    """Generate a fresh RSA keypair for one test - mirrors how Atlassian's
    real JWKS holds a public key we verify FITs' signatures against."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_pem, private_key.public_key()


def _make_token(private_pem, *, app_id=APP_ID, aud=APP_ID, iss=EXPECTED_ISSUER, exp_delta=300, algorithm="RS256"):
    payload = {"iss": iss, "aud": aud, "app": {"id": app_id}, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, private_pem, algorithm=algorithm)


def _patched_jwk_client(public_key):
    """Patch backend.forge_auth._jwk_client so get_signing_key_from_jwt
    returns our test keypair's public key instead of fetching Atlassian's
    real JWKS over the network."""
    fake_signing_key = MagicMock(key=public_key)
    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = fake_signing_key
    return patch("backend.forge_auth._jwk_client", mock_client)


def test_noop_when_require_forge_auth_is_unset(monkeypatch):
    monkeypatch.delenv("REQUIRE_FORGE_AUTH", raising=False)
    require_forge_invocation_token(authorization=None)  # must not raise


def test_noop_when_require_forge_auth_is_false(monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "false")
    require_forge_invocation_token(authorization=None)  # must not raise


def test_fails_closed_without_forge_app_id(monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.delenv("FORGE_APP_ID", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        require_forge_invocation_token(authorization="Bearer anything")
    assert exc_info.value.status_code == 500


def test_missing_authorization_header_rejected(monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", APP_ID)
    with pytest.raises(HTTPException) as exc_info:
        require_forge_invocation_token(authorization=None)
    assert exc_info.value.status_code == 401


def test_non_bearer_authorization_header_rejected(monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", APP_ID)
    with pytest.raises(HTTPException) as exc_info:
        require_forge_invocation_token(authorization="Basic anything")
    assert exc_info.value.status_code == 401


def test_valid_token_is_accepted(monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", APP_ID)
    private_pem, public_key = _keypair()
    token = _make_token(private_pem)

    with _patched_jwk_client(public_key):
        require_forge_invocation_token(authorization=f"Bearer {token}")  # must not raise


def test_wrong_audience_rejected(monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", APP_ID)
    private_pem, public_key = _keypair()
    token = _make_token(private_pem, aud="some-other-app")

    with _patched_jwk_client(public_key):
        with pytest.raises(HTTPException) as exc_info:
            require_forge_invocation_token(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_wrong_issuer_rejected(monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", APP_ID)
    private_pem, public_key = _keypair()
    token = _make_token(private_pem, iss="someone-else")

    with _patched_jwk_client(public_key):
        with pytest.raises(HTTPException) as exc_info:
            require_forge_invocation_token(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_app_id_claim_mismatch_rejected_even_with_matching_audience(monkeypatch):
    # aud matches FORGE_APP_ID, but the app.id claim itself doesn't -
    # Atlassian's own guidance is to check this explicitly rather than
    # trusting aud alone.
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", APP_ID)
    private_pem, public_key = _keypair()
    token = _make_token(private_pem, app_id="a-different-app-id", aud=APP_ID)

    with _patched_jwk_client(public_key):
        with pytest.raises(HTTPException) as exc_info:
            require_forge_invocation_token(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", APP_ID)
    private_pem, public_key = _keypair()
    token = _make_token(private_pem, exp_delta=-300)

    with _patched_jwk_client(public_key):
        with pytest.raises(HTTPException) as exc_info:
            require_forge_invocation_token(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_token_signed_by_a_different_key_rejected(monkeypatch):
    # Simulates a forged/tampered token: signed with a key that doesn't
    # match the one our (mocked) JWKS client returns.
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", APP_ID)
    attacker_private_pem, _ = _keypair()
    _, real_public_key = _keypair()
    token = _make_token(attacker_private_pem)

    with _patched_jwk_client(real_public_key):
        with pytest.raises(HTTPException) as exc_info:
            require_forge_invocation_token(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401
