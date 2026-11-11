"""Confirms require_forge_invocation_token (issue #25) actually guards
the 10 routes it was wired onto in main.py (issue #26) - and, just as
importantly, that it stays a no-op for every existing test/deployment
that doesn't set REQUIRE_FORGE_AUTH, since that's the whole point of
gating it behind an explicit opt-in rather than always-on.
"""

# (method, path) for every route issue #26 added require_forge_invocation_token
# to. Deliberately sent with no body/query params at all - if auth ran
# after argument validation, a missing required query param would surface
# as 422 instead of 401, so getting 401 here is itself proof auth runs
# first.
PROTECTED_ROUTES = [
    ("post", "/api/jira/connection"),
    ("get", "/api/jira/connection"),
    ("delete", "/api/jira/connection"),
    ("get", "/api/jira/requirements"),
    ("get", "/api/webhooks/jira/events"),
    ("get", "/api/inventory"),
    ("get", "/api/coverage"),
    ("get", "/api/requirement-links"),
    ("post", "/api/requirement-links/1/reviewed"),
    ("post", "/api/coverage/gap-analysis"),
]


def test_protected_routes_401_without_a_fit_when_enabled(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", "some-app-id")

    for method, path in PROTECTED_ROUTES:
        response = getattr(client, method)(path)
        assert response.status_code == 401, f"{method.upper()} {path} returned {response.status_code}, expected 401"


def test_protected_routes_401_with_a_garbage_bearer_token_when_enabled(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", "some-app-id")

    for method, path in PROTECTED_ROUTES:
        response = getattr(client, method)(path, headers={"Authorization": "Bearer not-a-real-jwt"})
        assert response.status_code == 401, f"{method.upper()} {path} returned {response.status_code}, expected 401"


def test_protected_routes_unaffected_when_require_forge_auth_is_unset(client, monkeypatch):
    # Confirms the default (off) posture: these routes behave exactly as
    # they did before issue #26 - whatever status they'd naturally return
    # (200, 400, 404, ...), it must not be 401, since there's no auth
    # requirement at all in this mode.
    monkeypatch.delenv("REQUIRE_FORGE_AUTH", raising=False)
    monkeypatch.delenv("FORGE_APP_ID", raising=False)

    for method, path in PROTECTED_ROUTES:
        response = getattr(client, method)(path)
        assert response.status_code != 401, f"{method.upper()} {path} returned 401 even though REQUIRE_FORGE_AUTH is unset"
