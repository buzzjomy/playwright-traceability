import json
from unittest.mock import patch

import requests


def _fake_response(status_code: int, json_body: dict | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(json_body or {}).encode("utf-8")
    return response


def _set_up_connection(client):
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"accountId": "abc", "displayName": "Jane Doe"})
        client.post(
            "/api/jira/connection",
            json={"site_url": "https://example.atlassian.net", "email": "me@example.com", "api_token": "token123"},
        )


def _push_static_spec(client, jira_keys=("KAN-4",)):
    client.post(
        "/api/ingest/run",
        json={
            "static_specs": [
                {
                    "title": "should load",
                    "full_title": "should load",
                    "file": "homepage.spec.ts",
                    "line": 1,
                    "column": 1,
                    "tags": [],
                    "jira_keys": list(jira_keys),
                }
            ]
        },
        headers={"Authorization": "Bearer test-key"},
    )


def _dispatch(*, search_result=None, issue_result=None, issue_status=200):
    """Route a mocked requests.get call by URL path, the way a single
    Jira connection actually serves both search and single-issue fetches
    from different endpoints."""

    def _handler(url, **kwargs):
        if url.endswith("/rest/api/3/search/jql"):
            return _fake_response(200, search_result or {"issues": [], "isLast": True})
        if "/rest/api/3/issue/" in url:
            return _fake_response(issue_status, issue_result)
        raise AssertionError(f"Unexpected URL in test: {url}")

    return _handler


def _issue(key: str, summary: str) -> dict:
    return {"key": key, "fields": {"summary": summary, "description": None}}


def test_requirement_links_without_a_connection_returns_400(client):
    response = client.get("/api/requirement-links", params={"project_key": "KAN"})
    assert response.status_code == 400


def test_requirement_links_syncs_a_new_covered_link(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    _set_up_connection(client)
    _push_static_spec(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(search_result={"issues": [_issue("KAN-4", "Homepage loads")], "isLast": True})
        response = client.get("/api/requirement-links", params={"project_key": "KAN"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["links"]) == 1
    link = body["links"][0]
    assert link["jira_key"] == "KAN-4"
    assert link["test_file"] == "homepage.spec.ts"
    assert link["state"] == "covered"


def test_requirement_links_marks_orphaned_when_jira_key_no_longer_resolves(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    _set_up_connection(client)
    _push_static_spec(client, jira_keys=("KAN-4",))

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(search_result={"issues": [_issue("KAN-4", "Homepage loads")], "isLast": True})
        client.get("/api/requirement-links", params={"project_key": "KAN"})

    # The requirement is gone from the next pull (deleted, or search no
    # longer returns it) - the link should now read as orphaned.
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(search_result={"issues": [], "isLast": True})
        response = client.get("/api/requirement-links", params={"project_key": "KAN"})

    assert response.json()["links"][0]["state"] == "orphaned"


def test_drift_detection_flips_link_to_suspect_via_webhook(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("JIRA_WEBHOOK_SECRET", "webhook-secret")
    _set_up_connection(client)
    _push_static_spec(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(search_result={"issues": [_issue("KAN-4", "Homepage loads")], "isLast": True})
        client.get("/api/requirement-links", params={"project_key": "KAN"})

    # A webhook says KAN-4 changed - drift detection re-pulls it and finds
    # a different summary than what was hashed at link time.
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(issue_result=_issue("KAN-4", "Homepage loads fast now"))
        webhook_response = client.post(
            "/api/webhooks/jira?token=webhook-secret",
            json={"webhookEvent": "jira:issue_updated", "issue": {"key": "KAN-4", "fields": {"summary": "x"}}},
        )
    assert webhook_response.status_code == 200

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(search_result={"issues": [_issue("KAN-4", "Homepage loads fast now")], "isLast": True})
        response = client.get("/api/requirement-links", params={"project_key": "KAN"})

    assert response.json()["links"][0]["state"] == "suspect"


def test_reviewed_action_clears_suspect_state(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("JIRA_WEBHOOK_SECRET", "webhook-secret")
    _set_up_connection(client)
    _push_static_spec(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(search_result={"issues": [_issue("KAN-4", "Homepage loads")], "isLast": True})
        client.get("/api/requirement-links", params={"project_key": "KAN"})

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(issue_result=_issue("KAN-4", "Homepage loads fast now"))
        client.post(
            "/api/webhooks/jira?token=webhook-secret",
            json={"webhookEvent": "jira:issue_updated", "issue": {"key": "KAN-4", "fields": {"summary": "x"}}},
        )

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(search_result={"issues": [_issue("KAN-4", "Homepage loads fast now")], "isLast": True})
        listing = client.get("/api/requirement-links", params={"project_key": "KAN"}).json()
    link_id = listing["links"][0]["id"]
    assert listing["links"][0]["state"] == "suspect"

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(issue_result=_issue("KAN-4", "Homepage loads fast now"))
        response = client.post(f"/api/requirement-links/{link_id}/reviewed")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "covered"
    assert body["last_reviewed_at"] is not None


def test_reviewed_action_on_orphaned_link_returns_400(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    _set_up_connection(client)
    _push_static_spec(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(search_result={"issues": [_issue("KAN-4", "Homepage loads")], "isLast": True})
        listing = client.get("/api/requirement-links", params={"project_key": "KAN"}).json()
    link_id = listing["links"][0]["id"]

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = _dispatch(issue_status=404, issue_result=None)
        response = client.post(f"/api/requirement-links/{link_id}/reviewed")

    assert response.status_code == 400


def test_reviewed_action_on_unknown_link_returns_404(client):
    _set_up_connection(client)
    response = client.post("/api/requirement-links/999/reviewed")
    assert response.status_code == 404
