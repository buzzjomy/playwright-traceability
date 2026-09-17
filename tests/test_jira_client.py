from unittest.mock import patch

import pytest
import requests

from backend.jira_client import JiraAuthError, JiraClient


def _fake_response(status_code: int, json_body: dict | None = None) -> requests.Response:
    """Build a minimal requests.Response for mocking JiraClient's HTTP calls."""
    response = requests.Response()
    response.status_code = status_code
    if json_body is not None:
        import json

        response._content = json.dumps(json_body).encode("utf-8")
    return response


def test_get_current_user_returns_parsed_json():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token123")
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"accountId": "abc", "displayName": "Jane Doe"})
        result = client.get_current_user()

    assert result == {"accountId": "abc", "displayName": "Jane Doe"}


def test_get_current_user_sends_basic_auth_to_correct_url():
    client = JiraClient("https://example.atlassian.net/", "me@example.com", "token123")
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {})
        client.get_current_user()

    args, kwargs = mock_get.call_args
    assert args[0] == "https://example.atlassian.net/rest/api/3/myself"
    assert kwargs["auth"] == ("me@example.com", "token123")


def test_unauthorized_response_raises_jira_auth_error():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "wrong-token")
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(401)
        with pytest.raises(JiraAuthError):
            client.get_current_user()


def test_other_http_errors_propagate():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token123")
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(500)
        with pytest.raises(requests.exceptions.HTTPError):
            client.get_current_user()
