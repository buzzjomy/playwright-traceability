"""Which Jira credentials a dashboard request uses (issue #41): the Forge app
system token when Forge sent one, else the tenant's own stored connection -
and never anything a caller could forge or borrow from another tenant."""

import json
from unittest.mock import patch

import pytest
import requests

API_BASE = "https://api.atlassian.com/ex/jira/7a1a2d0b-cabf-41a2-bf89-111b2c5e4b57"
ISSUE = {"key": "KAN-4", "fields": {"summary": "Homepage loads", "description": None}}


def _fake_response(status_code, body=None):
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(body or {}).encode()
    return response


@pytest.fixture()
def forge(monkeypatch):
    """Forge auth on; the verified claims carry `base` as app.apiBaseUrl."""
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", "the-app")
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_TENANT_INSTALLATION_ID", raising=False)
    state = {"base": API_BASE}

    def fake_verify(authorization):
        return {"app": {"id": "the-app", "installationId": "A", "apiBaseUrl": state["base"]}, "context": {"cloudId": "c"}}

    with patch("backend.tenancy.verify_forge_invocation_token", side_effect=fake_verify):
        yield state


def _headers(token="system-token"):
    headers = {"Authorization": "Bearer fit"}
    if token:
        headers["x-forge-oauth-system"] = token
    return headers


def _search_returning(issues):
    def handler(url, **kwargs):
        assert url.endswith("/rest/api/3/search/jql"), url
        return _fake_response(200, {"issues": issues, "isLast": True})

    return handler


def test_the_forge_system_token_is_used_as_a_bearer_credential(client, forge):
    with patch("backend.jira_client.requests.get", side_effect=_search_returning([ISSUE])) as mock_get:
        response = client.get("/api/coverage", params={"project_key": "KAN"}, headers=_headers())

    assert response.status_code == 200
    assert [r["key"] for r in response.json()["requirements"]] == ["KAN-4"]
    call = mock_get.call_args
    assert call.args[0] == f"{API_BASE}/rest/api/3/search/jql"
    assert call.kwargs["headers"]["Authorization"] == "Bearer system-token"
    assert call.kwargs["auth"] is None  # not Basic auth


def test_no_stored_connection_is_needed_when_forge_sends_a_token(client, forge):
    with patch("backend.jira_client.requests.get", side_effect=_search_returning([])):
        assert client.get("/api/requirement-links", params={"project_key": "KAN"}, headers=_headers()).status_code == 200
        assert client.get("/api/jira/requirements", params={"project_key": "KAN"}, headers=_headers()).status_code == 200


def test_without_a_token_and_without_a_stored_connection_it_is_a_400(client, forge):
    response = client.get("/api/coverage", params={"project_key": "KAN"}, headers=_headers(token=None))
    assert response.status_code == 400


def test_the_forge_token_is_preferred_over_a_stored_connection(client, forge):
    with patch("backend.jira_client.requests.get", return_value=_fake_response(200, {"accountId": "a"})):
        client.post(
            "/api/jira/connection",
            json={"site_url": "https://stored.atlassian.net", "email": "me@example.com", "api_token": "basic-token"},
            headers=_headers(token=None),
        )
    with patch("backend.jira_client.requests.get", side_effect=_search_returning([])) as mock_get:
        client.get("/api/coverage", params={"project_key": "KAN"}, headers=_headers())
    assert mock_get.call_args.args[0].startswith(API_BASE)
    assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer system-token"


def test_a_stored_connection_still_works_without_a_forge_token(client, forge):
    with patch("backend.jira_client.requests.get", return_value=_fake_response(200, {"accountId": "a"})):
        client.post(
            "/api/jira/connection",
            json={"site_url": "https://stored.atlassian.net", "email": "me@example.com", "api_token": "basic-token"},
            headers=_headers(token=None),
        )
    with patch("backend.jira_client.requests.get", side_effect=_search_returning([])) as mock_get:
        response = client.get("/api/coverage", params={"project_key": "KAN"}, headers=_headers(token=None))
    assert response.status_code == 200
    assert mock_get.call_args.args[0].startswith("https://stored.atlassian.net")
    assert mock_get.call_args.kwargs["auth"] == ("me@example.com", "basic-token")


@pytest.mark.parametrize("bad_base", ["https://evil.example.com/ex/jira/x", "http://api.atlassian.com/ex/jira/x", "", None])
def test_a_base_url_that_is_not_atlassians_gateway_is_never_called(client, forge, bad_base):
    forge["base"] = bad_base
    with patch("backend.jira_client.requests.get") as mock_get:
        response = client.get("/api/coverage", params={"project_key": "KAN"}, headers=_headers())
    assert response.status_code == 400  # token ignored -> no Jira access at all
    mock_get.assert_not_called()


def test_forge_headers_are_ignored_when_forge_auth_is_off(client, monkeypatch):
    monkeypatch.delenv("REQUIRE_FORGE_AUTH", raising=False)
    with patch("backend.jira_client.requests.get") as mock_get:
        response = client.get(
            "/api/coverage", params={"project_key": "KAN"}, headers={"x-forge-oauth-system": "forged", "Authorization": "Bearer x"}
        )
    assert response.status_code == 400
    mock_get.assert_not_called()


def test_connection_status_reports_connected_when_a_token_is_sent(client, forge):
    with_token = client.get("/api/jira/connection", headers=_headers()).json()
    without = client.get("/api/jira/connection", headers=_headers(token=None)).json()
    assert with_token["connected"] is True
    assert without["connected"] is False


def test_a_jira_rejection_of_the_token_is_a_401_not_a_crash(client, forge):
    with patch("backend.jira_client.requests.get", return_value=_fake_response(401)):
        response = client.get("/api/coverage", params={"project_key": "KAN"}, headers=_headers())
    assert response.status_code == 401
