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


def _push_static_spec(client, jira_keys=("KAN-5",), assertions=None):
    client.post(
        "/api/ingest/run",
        json={
            "static_specs": [
                {
                    "title": "should show search results",
                    "full_title": "should show search results",
                    "file": "search.spec.ts",
                    "line": 1,
                    "column": 1,
                    "tags": [],
                    "jira_keys": list(jira_keys),
                    "assertions": assertions or ["expect(page.getByTestId('results')).toBeVisible()"],
                }
            ]
        },
        headers={"Authorization": "Bearer test-key"},
    )


def _issue_with_ac(key: str, summary: str, criteria: list[str]) -> dict:
    description = {
        "type": "doc",
        "content": [
            {"type": "heading", "content": [{"type": "text", "text": "Acceptance Criteria"}]},
            {
                "type": "bulletList",
                "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": c}]}]}
                    for c in criteria
                ],
            },
        ],
    }
    return {"key": key, "fields": {"summary": summary, "description": description}}


def test_gap_analysis_without_a_connection_returns_400(client):
    response = client.post("/api/coverage/gap-analysis", params={"project_key": "KAN", "jira_key": "KAN-5"})
    assert response.status_code == 400


def test_gap_analysis_rejects_a_jira_key_outside_the_project(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    _set_up_connection(client)
    response = client.post("/api/coverage/gap-analysis", params={"project_key": "KAN", "jira_key": "OTHER-1"})
    assert response.status_code == 400


def test_gap_analysis_on_unresolvable_key_returns_404(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    _set_up_connection(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(404, None)
        response = client.post("/api/coverage/gap-analysis", params={"project_key": "KAN", "jira_key": "KAN-5"})

    assert response.status_code == 404


def test_gap_analysis_without_api_key_returns_400(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _set_up_connection(client)
    _push_static_spec(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(
            200, _issue_with_ac("KAN-5", "Search works", ["Results are shown", "Results can be filtered"])
        )
        response = client.post("/api/coverage/gap-analysis", params={"project_key": "KAN", "jira_key": "KAN-5"})

    assert response.status_code == 400


def test_gap_analysis_with_no_linked_tests_skips_the_llm_entirely(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _set_up_connection(client)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, _issue_with_ac("KAN-14", "Scratch issue", ["Some criterion"]))
        with patch("backend.semantic_gap.anthropic.Anthropic") as mock_anthropic:
            response = client.post("/api/coverage/gap-analysis", params={"project_key": "KAN", "jira_key": "KAN-14"})

    mock_anthropic.assert_not_called()
    assert response.status_code == 200
    body = response.json()
    assert body["uncovered_count"] == 1
    assert body["criteria"][0]["covered"] is False


def test_gap_analysis_returns_per_criterion_results(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _set_up_connection(client)
    _push_static_spec(client)

    from unittest.mock import MagicMock

    mock_llm_client = MagicMock()
    mock_llm_client.messages.create.return_value = MagicMock(
        content=[
            MagicMock(
                type="text",
                text=json.dumps(
                    [
                        {"covered": True, "reasoning": "Matches the assertion."},
                        {"covered": False, "reasoning": "No evidence of filtering."},
                    ]
                ),
            )
        ]
    )

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(
            200, _issue_with_ac("KAN-5", "Search works", ["Results are shown", "Results can be filtered"])
        )
        with patch("backend.semantic_gap.anthropic.Anthropic", return_value=mock_llm_client):
            response = client.post("/api/coverage/gap-analysis", params={"project_key": "KAN", "jira_key": "KAN-5"})

    assert response.status_code == 200
    body = response.json()
    assert body["jira_key"] == "KAN-5"
    assert body["uncovered_count"] == 1
    assert body["criteria"][0] == {
        "criterion": "Results are shown",
        "covered": True,
        "reasoning": "Matches the assertion.",
    }
    assert body["criteria"][1]["covered"] is False


def test_gap_analysis_llm_failure_returns_502(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _set_up_connection(client)
    _push_static_spec(client)

    from unittest.mock import MagicMock

    mock_llm_client = MagicMock()
    mock_llm_client.messages.create.return_value = MagicMock(content=[MagicMock(type="text", text="not json")])

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, _issue_with_ac("KAN-5", "Search works", ["Results are shown"]))
        with patch("backend.semantic_gap.anthropic.Anthropic", return_value=mock_llm_client):
            response = client.post("/api/coverage/gap-analysis", params={"project_key": "KAN", "jira_key": "KAN-5"})

    assert response.status_code == 502
