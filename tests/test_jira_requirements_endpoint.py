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


def test_requirements_endpoint_without_a_connection_returns_400(client):
    response = client.get("/api/jira/requirements", params={"project_key": "KAN"})
    assert response.status_code == 400


def test_requirements_endpoint_returns_parsed_requirements(client):
    _set_up_connection(client)

    search_response = {
        "issues": [
            {
                "key": "KAN-4",
                "fields": {
                    "summary": "Homepage loads",
                    "description": {
                        "type": "doc",
                        "content": [
                            {"type": "heading", "content": [{"type": "text", "text": "Acceptance Criteria"}]},
                            {
                                "type": "bulletList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [
                                            {"type": "paragraph", "content": [{"type": "text", "text": "It loads."}]}
                                        ],
                                    }
                                ],
                            },
                        ],
                    },
                },
            }
        ],
        "isLast": True,
    }

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        response = client.get("/api/jira/requirements", params={"project_key": "KAN"})

    assert response.status_code == 200
    body = response.json()
    assert body["project_key"] == "KAN"
    assert len(body["requirements"]) == 1
    assert body["requirements"][0]["key"] == "KAN-4"
    assert body["requirements"][0]["acceptance_criteria"] == ["It loads."]


def test_requirements_endpoint_respects_custom_issue_types(client):
    _set_up_connection(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"issues": [], "isLast": True})
        client.get("/api/jira/requirements", params={"project_key": "KAN", "issue_types": "Epic"})

    _, kwargs = mock_get.call_args
    assert '"Epic"' in kwargs["params"]["jql"]


def test_requirements_endpoint_propagates_auth_failure(client):
    _set_up_connection(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(401)
        response = client.get("/api/jira/requirements", params={"project_key": "KAN"})

    assert response.status_code == 401
