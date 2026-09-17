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


def test_coverage_endpoint_without_a_connection_returns_400(client):
    response = client.get("/api/coverage", params={"project_key": "KAN"})
    assert response.status_code == 400


def test_coverage_endpoint_reports_uncovered_and_covered_requirements(client, monkeypatch):
    _set_up_connection(client)
    monkeypatch.setenv("INGEST_API_KEY", "test-key")

    # One test, linked to KAN-4 only.
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
                    "jira_keys": ["KAN-4"],
                }
            ]
        },
        headers={"Authorization": "Bearer test-key"},
    )

    search_response = {
        "issues": [
            {"key": "KAN-4", "fields": {"summary": "Homepage loads", "description": None}},
            {"key": "KAN-14", "fields": {"summary": "Scratch issue", "description": None}},
        ],
        "isLast": True,
    }
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        response = client.get("/api/coverage", params={"project_key": "KAN"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["covered"] == 1
    assert body["uncovered"] == 1

    by_key = {r["key"]: r for r in body["requirements"]}
    assert by_key["KAN-4"]["covered"] is True
    assert by_key["KAN-4"]["linked_test_count"] == 1
    assert by_key["KAN-14"]["covered"] is False
    assert by_key["KAN-14"]["linked_test_count"] == 0


def test_coverage_endpoint_propagates_auth_failure(client):
    _set_up_connection(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(401)
        response = client.get("/api/coverage", params={"project_key": "KAN"})

    assert response.status_code == 401
