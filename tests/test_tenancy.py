"""Multi-tenancy (issues #40/#42): one customer's data must never be
visible to, or modifiable by, another. Forge calls are simulated by patching
the token verification to return claims for a chosen installation."""

import json
from unittest.mock import patch

import pytest
import requests

RUN_RECORD = {
    "spec_id": "s",
    "title": "should load",
    "full_title": "should load",
    "file": "homepage.spec.ts",
    "line": 1,
    "column": 1,
    "project": "chromium",
    "tags": [],
    "jira_keys": ["KAN-4"],
    "status": "passed",
    "duration_ms": 1,
    "retry_count": 0,
    "is_flaky": False,
    "error_message": None,
}


def _claims_for(installation_id, cloud_id="cloud-1"):
    return {"app": {"id": "the-app", "installationId": installation_id}, "context": {"cloudId": cloud_id}}


@pytest.fixture()
def forge(monkeypatch):
    """Turn Forge auth on; a request's tenant is chosen by its bearer token,
    'Bearer fit-<installation id>' (standing in for a verified FIT)."""
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", "the-app")
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_TENANT_INSTALLATION_ID", raising=False)

    def fake_verify(authorization):
        token = (authorization or "").removeprefix("Bearer ")
        if not token.startswith("fit-"):
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="bad token")
        installation = token.removeprefix("fit-")
        return _claims_for(installation or None)

    with patch("backend.tenancy.verify_forge_invocation_token", side_effect=fake_verify):
        yield


def _as(installation_id):
    return {"Authorization": f"Bearer fit-{installation_id}"}


def _new_ingest_key(client, installation_id):
    response = client.post("/api/tenant/ingest-key", headers=_as(installation_id))
    assert response.status_code == 200
    return response.json()["ingest_key"]


def _push(client, ingest_key, jira_keys=("KAN-4",), title="should load"):
    record = {**RUN_RECORD, "jira_keys": list(jira_keys), "title": title, "full_title": title}
    response = client.post(
        "/api/ingest/run",
        json={"run_report": [record], "static_specs": [{k: record[k] for k in ("title", "full_title", "file", "line", "column", "tags", "jira_keys")}]},
        headers={"Authorization": f"Bearer {ingest_key}"},
    )
    assert response.status_code == 200, response.text


def _fake_response(status_code, body=None):
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(body or {}).encode()
    return response


def _connect(client, installation_id, site="https://example.atlassian.net"):
    with patch("backend.jira_client.requests.get", return_value=_fake_response(200, {"accountId": "a", "displayName": "D"})):
        response = client.post(
            "/api/jira/connection",
            json={"site_url": site, "email": "me@example.com", "api_token": "tok"},
            headers=_as(installation_id),
        )
    assert response.status_code == 200, response.text


def _jira_dispatch(issues):
    def handler(url, **kwargs):
        if url.endswith("/rest/api/3/search/jql"):
            return _fake_response(200, {"issues": issues, "isLast": True})
        if "/rest/api/3/issue/" in url:
            key = url.rsplit("/", 1)[-1].split("?")[0]
            match = next((i for i in issues if i["key"] == key), None)
            return _fake_response(200 if match else 404, match)
        raise AssertionError(url)

    return handler


ISSUE = {"key": "KAN-4", "fields": {"summary": "Homepage loads", "description": None}}


# -- who the caller is ------------------------------------------------------


def test_a_token_without_an_installation_id_is_rejected(client, forge):
    with patch("backend.tenancy.verify_forge_invocation_token", return_value={"app": {"id": "the-app"}}):
        response = client.get("/api/inventory", headers=_as("x"))
    assert response.status_code == 401


def test_without_forge_auth_everything_is_the_local_tenant(client, monkeypatch):
    monkeypatch.delenv("REQUIRE_FORGE_AUTH", raising=False)
    monkeypatch.setenv("INGEST_API_KEY", "legacy")
    client.post("/api/ingest/run", json={"run_report": [RUN_RECORD]}, headers={"Authorization": "Bearer legacy"})
    assert len(client.get("/api/inventory").json()["entries"]) == 1


def test_the_owner_installation_can_be_mapped_to_the_local_tenant(client, forge, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "legacy")
    monkeypatch.setenv("LOCAL_TENANT_INSTALLATION_ID", "owner-install")
    client.post("/api/ingest/run", json={"run_report": [RUN_RECORD]}, headers={"Authorization": "Bearer legacy"})

    assert len(client.get("/api/inventory", headers=_as("owner-install")).json()["entries"]) == 1
    # ...and only that installation: any other customer still sees nothing.
    assert client.get("/api/inventory", headers=_as("someone-else")).json()["entries"] == []


# -- isolation ---------------------------------------------------------------


def test_each_tenant_only_sees_its_own_inventory(client, forge):
    key_a, key_b = _new_ingest_key(client, "A"), _new_ingest_key(client, "B")
    _push(client, key_a, title="only A has this")
    _push(client, key_b, title="only B has this")

    titles_a = [e["title"] for e in client.get("/api/inventory", headers=_as("A")).json()["entries"]]
    titles_b = [e["title"] for e in client.get("/api/inventory", headers=_as("B")).json()["entries"]]
    assert titles_a == ["only A has this"]
    assert titles_b == ["only B has this"]


def test_a_source_scan_replaces_only_the_pushing_tenants_records(client, forge):
    key_a, key_b = _new_ingest_key(client, "A"), _new_ingest_key(client, "B")
    _push(client, key_a, title="A's test")
    _push(client, key_b, title="B's test")
    # A pushes again with a different test: that replaces A's source snapshot,
    # and must leave B's untouched.
    _push(client, key_a, title="A's renamed test")

    titles_b = [e["title"] for e in client.get("/api/inventory", headers=_as("B")).json()["entries"]]
    assert titles_b == ["B's test"]


def test_each_tenant_has_its_own_jira_connection(client, forge):
    _connect(client, "A", site="https://a.atlassian.net")

    with patch("backend.jira_client.requests.get", return_value=_fake_response(200, {"accountId": "a"})):
        a = client.get("/api/jira/connection", headers=_as("A")).json()
        b = client.get("/api/jira/connection", headers=_as("B")).json()
    assert a["connected"] is True and a["site_url"].startswith("https://a.atlassian.net")
    assert b["connected"] is False

    # B never inherits A's credentials: a Jira-backed call is refused, not
    # served through A's connection.
    assert client.get("/api/coverage", params={"project_key": "KAN"}, headers=_as("B")).status_code == 400


def test_deleting_one_tenants_connection_leaves_the_others(client, forge):
    _connect(client, "A")
    _connect(client, "B")
    assert client.delete("/api/jira/connection", headers=_as("A")).status_code == 204

    with patch("backend.jira_client.requests.get", return_value=_fake_response(200, {"accountId": "a"})):
        assert client.get("/api/jira/connection", headers=_as("A")).json()["connected"] is False
        assert client.get("/api/jira/connection", headers=_as("B")).json()["connected"] is True


def test_requirement_links_are_per_tenant_and_a_foreign_link_cannot_be_reviewed(client, forge):
    key_a = _new_ingest_key(client, "A")
    _connect(client, "A")
    _push(client, key_a)
    with patch("backend.jira_client.requests.get", side_effect=_jira_dispatch([ISSUE])):
        links_a = client.get("/api/requirement-links", params={"project_key": "KAN"}, headers=_as("A")).json()["links"]
    assert len(links_a) == 1
    link_id = links_a[0]["id"]

    _connect(client, "B")
    with patch("backend.jira_client.requests.get", side_effect=_jira_dispatch([ISSUE])):
        assert client.get("/api/requirement-links", params={"project_key": "KAN"}, headers=_as("B")).json()["links"] == []
        # B cannot act on A's link, and is told it doesn't exist (not "forbidden").
        assert client.post(f"/api/requirement-links/{link_id}/reviewed", headers=_as("B")).status_code == 404
        assert client.post(f"/api/requirement-links/{link_id}/reviewed", headers=_as("A")).status_code == 200


def test_the_same_requirement_and_test_can_be_linked_by_two_tenants(client, forge):
    for installation in ("A", "B"):
        key = _new_ingest_key(client, installation)
        _connect(client, installation)
        _push(client, key)
        with patch("backend.jira_client.requests.get", side_effect=_jira_dispatch([ISSUE])):
            links = client.get("/api/requirement-links", params={"project_key": "KAN"}, headers=_as(installation)).json()["links"]
        assert len(links) == 1


def test_webhook_events_are_listed_per_tenant(client, forge, monkeypatch):
    monkeypatch.setenv("JIRA_WEBHOOK_SECRET", "s3cret")
    client.post("/api/webhooks/jira?token=s3cret", json={"webhookEvent": "jira:issue_updated", "issue": {"key": "KAN-4"}})
    # The shared-secret webhook only serves the local (owner) tenant.
    assert client.get("/api/webhooks/jira/events", headers=_as("A")).json() == []


def test_poll_state_is_tracked_per_tenant(client, forge):
    key_a, key_b = _new_ingest_key(client, "A"), _new_ingest_key(client, "B")
    _connect(client, "A")
    _connect(client, "B")
    with patch("backend.jira_client.requests.get", side_effect=_jira_dispatch([])):
        first_a = client.post("/api/jira/poll", params={"project_key": "KAN"}, headers={"Authorization": f"Bearer {key_a}"})
        first_b = client.post("/api/jira/poll", params={"project_key": "KAN"}, headers={"Authorization": f"Bearer {key_b}"})
        second_a = client.post("/api/jira/poll", params={"project_key": "KAN"}, headers={"Authorization": f"Bearer {key_a}"})
    assert first_a.json()["is_first_poll"] is True
    assert first_b.json()["is_first_poll"] is True  # B's baseline isn't A's
    assert second_a.json()["is_first_poll"] is False


# -- per-tenant ingest keys (#42) --------------------------------------------


def test_tenant_info_describes_only_the_caller(client, forge):
    info = client.get("/api/tenant", headers=_as("A")).json()
    assert info == {"installation_id": "A", "cloud_id": "cloud-1", "has_ingest_key": False}
    _new_ingest_key(client, "A")
    assert client.get("/api/tenant", headers=_as("A")).json()["has_ingest_key"] is True
    assert client.get("/api/tenant", headers=_as("B")).json()["has_ingest_key"] is False


def test_generating_a_key_invalidates_the_previous_one(client, forge):
    old = _new_ingest_key(client, "A")
    new = _new_ingest_key(client, "A")
    assert old != new and new.startswith("pwt_")

    body = {"run_report": []}
    assert client.post("/api/ingest/run", json=body, headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.post("/api/ingest/run", json=body, headers={"Authorization": f"Bearer {new}"}).status_code == 200


def test_the_plaintext_key_is_never_stored(client, forge):
    from backend.models import Tenant

    key = _new_ingest_key(client, "A")
    from backend.main import app
    from backend.db import get_db

    db = next(app.dependency_overrides[get_db]())
    stored = db.query(Tenant).filter(Tenant.key == "A").one()
    assert stored.ingest_key_hash is not None and key not in stored.ingest_key_hash
    db.close()


def test_an_unknown_key_is_rejected(client, forge):
    response = client.post("/api/ingest/run", json={"run_report": []}, headers={"Authorization": "Bearer pwt_nope"})
    assert response.status_code == 401


def test_the_legacy_global_key_maps_to_the_local_tenant_only(client, forge, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "legacy")
    client.post("/api/ingest/run", json={"run_report": [RUN_RECORD]}, headers={"Authorization": "Bearer legacy"})
    # A customer installation does not see what the legacy key pushed.
    assert client.get("/api/inventory", headers=_as("customer")).json()["entries"] == []


def test_dashboard_routes_do_not_accept_an_ingest_key(client, forge):
    key = _new_ingest_key(client, "A")
    assert client.get("/api/inventory", headers={"Authorization": f"Bearer {key}"}).status_code == 401
