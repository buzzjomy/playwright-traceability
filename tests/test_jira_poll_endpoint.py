import json
from unittest.mock import patch

import pytest
import requests


def _fake_response(status_code: int, json_body: dict | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(json_body or {}).encode("utf-8")
    return response


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-secret-key")
    return "test-secret-key"


def _auth_headers(key: str = "test-secret-key") -> dict:
    return {"Authorization": f"Bearer {key}"}


def _set_up_connection(client):
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"accountId": "abc", "displayName": "Jane Doe"})
        client.post(
            "/api/jira/connection",
            json={"site_url": "https://example.atlassian.net", "email": "me@example.com", "api_token": "token123"},
        )


def test_poll_requires_api_key(client):
    response = client.post("/api/jira/poll", params={"project_key": "KAN"})
    assert response.status_code == 401


def test_poll_without_a_connection_returns_400(client):
    response = client.post("/api/jira/poll", params={"project_key": "KAN"}, headers=_auth_headers())
    assert response.status_code == 400


def test_first_poll_finds_no_issues_and_sets_baseline(client):
    _set_up_connection(client)

    response = client.post("/api/jira/poll", params={"project_key": "KAN"}, headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["is_first_poll"] is True
    assert body["changed_issue_count"] == 0

    events = client.get("/api/webhooks/jira/events").json()
    assert events == []


def test_second_poll_finds_changes_and_records_events(client):
    _set_up_connection(client)
    client.post("/api/jira/poll", params={"project_key": "KAN"}, headers=_auth_headers())

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"issues": [{"key": "KAN-4"}], "isLast": True})
        response = client.post("/api/jira/poll", params={"project_key": "KAN"}, headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["is_first_poll"] is False
    assert body["changed_issue_count"] == 1

    events = client.get("/api/webhooks/jira/events").json()
    assert len(events) == 1
    assert events[0]["issue_key"] == "KAN-4"
    assert events[0]["webhook_event"] == "jira:issue_polled"
    assert events[0]["changelog"] is None


def test_poll_uses_updated_since_from_last_poll(client):
    _set_up_connection(client)
    client.post("/api/jira/poll", params={"project_key": "KAN"}, headers=_auth_headers())

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"issues": [], "isLast": True})
        client.post("/api/jira/poll", params={"project_key": "KAN"}, headers=_auth_headers())

    _, kwargs = mock_get.call_args
    assert 'project = "KAN"' in kwargs["params"]["jql"]
    assert "updated >=" in kwargs["params"]["jql"]


def test_poll_propagates_auth_failure(client):
    _set_up_connection(client)
    client.post("/api/jira/poll", params={"project_key": "KAN"}, headers=_auth_headers())

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(401)
        response = client.post("/api/jira/poll", params={"project_key": "KAN"}, headers=_auth_headers())

    assert response.status_code == 401


def test_different_projects_are_polled_independently(client):
    _set_up_connection(client)
    client.post("/api/jira/poll", params={"project_key": "KAN"}, headers=_auth_headers())

    # A different project has no prior poll state, so it's still a first poll.
    response = client.post("/api/jira/poll", params={"project_key": "SAM1"}, headers=_auth_headers())
    assert response.json()["is_first_poll"] is True
