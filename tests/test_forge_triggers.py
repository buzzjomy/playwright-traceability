"""Forge-driven change detection (issue #41): an issue-updated event and an
hourly scheduled poll, each carrying a fresh system token, keep Suspect
links current - tenant by tenant, without a webhook or a polling script."""

import json
from unittest.mock import patch

import pytest
import requests

from backend.forge_triggers import issue_key_from_event, tracked_project_keys

API_BASE = "https://api.atlassian.com/ex/jira/c1"
RUN_RECORD = {
    "spec_id": "s", "title": "should load", "full_title": "should load", "file": "homepage.spec.ts",
    "line": 1, "column": 1, "project": "chromium", "tags": [], "jira_keys": ["KAN-4"], "status": "passed",
    "duration_ms": 1, "retry_count": 0, "is_flaky": False, "error_message": None,
}


def _fake_response(status_code, body=None):
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(body or {}).encode()
    return response


class FakeJira:
    """A tiny Jira: one issue whose summary a test can change, served on the
    search and single-issue endpoints."""

    def __init__(self):
        self.summary = "Homepage loads"
        self.fail = False

    def issue(self):
        return {"key": "KAN-4", "fields": {"summary": self.summary, "description": None}}

    def __call__(self, url, **kwargs):
        if self.fail:
            raise requests.ConnectionError("jira down")
        if url.endswith("/rest/api/3/search/jql"):
            return _fake_response(200, {"issues": [self.issue()], "isLast": True})
        if url.endswith("/rest/api/3/issue/KAN-4"):
            return _fake_response(200, self.issue())
        raise AssertionError(url)


@pytest.fixture()
def jira():
    fake = FakeJira()
    with patch("backend.jira_client.requests.get", side_effect=fake):
        yield fake


@pytest.fixture()
def forge(monkeypatch):
    """Forge auth on; 'Bearer fit-<installation>' picks the tenant. The
    change-summary LLM is off so a flip is purely the hash comparison."""
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", "the-app")
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_TENANT_INSTALLATION_ID", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def fake_verify(authorization):
        token = (authorization or "").removeprefix("Bearer ")
        if not token.startswith("fit-"):
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="bad token")
        return {"app": {"id": "the-app", "installationId": token.removeprefix("fit-"), "apiBaseUrl": API_BASE}}

    with patch("backend.tenancy.verify_forge_invocation_token", side_effect=fake_verify):
        yield


def _as(installation, token="system-token"):
    headers = {"Authorization": f"Bearer fit-{installation}"}
    if token:
        headers["x-forge-oauth-system"] = token
    return headers


def _link_a_test(client, installation, jira):
    """Give a tenant a covered link KAN-4 <-> a test, hashed against the current issue."""
    key = client.post("/api/tenant/ingest-key", headers=_as(installation)).json()["ingest_key"]
    client.post(
        "/api/ingest/run",
        json={"run_report": [RUN_RECORD], "static_specs": [
            {k: RUN_RECORD[k] for k in ("title", "full_title", "file", "line", "column", "tags", "jira_keys")}]},
        headers={"Authorization": f"Bearer {key}"},
    )
    links = client.get("/api/requirement-links", params={"project_key": "KAN"}, headers=_as(installation)).json()["links"]
    assert [l["state"] for l in links] == ["covered"]


def _states(client, installation):
    links = client.get("/api/requirement-links", params={"project_key": "KAN"}, headers=_as(installation)).json()["links"]
    return [l["state"] for l in links]


# -- the issue-updated event ---------------------------------------------------


def test_an_issue_updated_event_flips_a_drifted_link_to_suspect(client, forge, jira):
    _link_a_test(client, "A", jira)
    jira.summary = "Homepage loads - and now does more"

    response = client.post("/api/forge/events/issue-updated", json={"issue": {"key": "KAN-4"}}, headers=_as("A"))

    assert response.status_code == 200
    assert response.json() == {"received": True, "issue_key": "KAN-4", "queued": True}
    # Read straight from the DB: the links endpoint re-pulls but never re-checks drift.
    assert _states(client, "A") == ["suspect"]


def test_an_unchanged_issue_stays_covered(client, forge, jira):
    _link_a_test(client, "A", jira)
    client.post("/api/forge/events/issue-updated", json={"issue": {"key": "KAN-4"}}, headers=_as("A"))
    assert _states(client, "A") == ["covered"]


def test_the_issue_key_is_found_whether_or_not_it_is_nested_under_payload(client, forge, jira):
    _link_a_test(client, "A", jira)
    jira.summary = "Changed"
    client.post("/api/forge/events/issue-updated", json={"payload": {"issue": {"key": "KAN-4"}}}, headers=_as("A"))
    assert _states(client, "A") == ["suspect"]


def test_an_event_for_another_tenant_never_touches_this_tenants_links(client, forge, jira):
    _link_a_test(client, "A", jira)
    jira.summary = "Changed"
    # Tenant B reports the same issue key changed: only B's (empty) links are considered.
    client.post("/api/forge/events/issue-updated", json={"issue": {"key": "KAN-4"}}, headers=_as("B"))
    assert _states(client, "A") == ["covered"]


def test_an_event_without_a_system_token_is_acknowledged_but_not_acted_on(client, forge, jira):
    _link_a_test(client, "A", jira)
    jira.summary = "Changed"
    response = client.post("/api/forge/events/issue-updated", json={"issue": {"key": "KAN-4"}}, headers=_as("A", token=None))
    assert response.status_code == 200  # a non-2xx would just make Forge retry it 4 times
    assert response.json()["queued"] is False
    assert _states(client, "A") == ["covered"]


def test_an_event_with_an_unverified_token_is_rejected(client, forge, jira):
    response = client.post(
        "/api/forge/events/issue-updated", json={"issue": {"key": "KAN-4"}}, headers={"Authorization": "Bearer not-a-fit"}
    )
    assert response.status_code == 401


def test_a_jira_failure_in_the_background_does_not_break_the_acknowledgement(client, forge, jira):
    _link_a_test(client, "A", jira)
    jira.fail = True
    response = client.post("/api/forge/events/issue-updated", json={"issue": {"key": "KAN-4"}}, headers=_as("A"))
    assert response.status_code == 200


def test_only_the_issue_key_is_kept_from_an_event(client, forge, jira):
    from backend.db import get_db
    from backend.main import app
    from backend.models import JiraWebhookEvent

    body = {"issue": {"key": "KAN-4", "fields": {"reporter": {"displayName": "Someone", "emailAddress": "x@y.z"}}}}
    client.post("/api/forge/events/issue-updated", json=body, headers=_as("A"))

    db = next(app.dependency_overrides[get_db]())
    event = db.query(JiraWebhookEvent).one()
    assert event.raw_payload == {"issue_key": "KAN-4"} and event.changelog is None
    db.close()


# -- the hourly scheduled poll -------------------------------------------------


def test_the_scheduled_poll_sets_a_baseline_then_catches_a_later_change(client, forge, jira):
    _link_a_test(client, "A", jira)

    first = client.post("/api/forge/scheduled/poll", headers=_as("A"))
    assert first.json() == {"queued": True}
    assert _states(client, "A") == ["covered"]  # baseline only: nothing is "changed" yet

    jira.summary = "Changed after the baseline"
    client.post("/api/forge/scheduled/poll", headers=_as("A"))
    assert _states(client, "A") == ["suspect"]


def test_the_scheduled_poll_without_a_token_does_nothing(client, forge, jira):
    assert client.post("/api/forge/scheduled/poll", headers=_as("A", token=None)).json() == {"queued": False}


def test_the_scheduled_poll_is_scoped_to_the_calling_tenant(client, forge, jira):
    _link_a_test(client, "A", jira)
    client.post("/api/forge/scheduled/poll", headers=_as("A"))  # A's baseline
    jira.summary = "Changed"
    client.post("/api/forge/scheduled/poll", headers=_as("B"))  # B has no links or poll state
    assert _states(client, "A") == ["covered"]


# -- helpers ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "body, expected",
    [
        ({"issue": {"key": "KAN-1"}}, "KAN-1"),
        ({"payload": {"issue": {"key": "KAN-2"}}}, "KAN-2"),
        ({"issue": {}}, None),
        ({"issue": {"key": 7}}, None),
        ({}, None),
        ("nope", None),
        (None, None),
    ],
)
def test_issue_key_from_event(body, expected):
    assert issue_key_from_event(body) == expected


def test_tracked_projects_are_those_with_links_or_poll_state(client, forge, jira):
    from backend.db import get_db
    from backend.main import app

    _link_a_test(client, "A", jira)
    client.post("/api/forge/scheduled/poll", headers=_as("A"))
    db = next(app.dependency_overrides[get_db]())
    from backend.models import Tenant

    tenant_a = db.query(Tenant).filter(Tenant.key == "A").one()
    assert tracked_project_keys(db, tenant_a.id) == ["KAN"]
    assert tracked_project_keys(db, 9999) == []
    db.close()
