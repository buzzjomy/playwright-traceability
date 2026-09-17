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


def test_search_issues_uses_the_new_search_jql_endpoint():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token123")
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"issues": [], "isLast": True})
        client.search_issues('project = "KAN"')

    args, kwargs = mock_get.call_args
    assert args[0] == "https://example.atlassian.net/rest/api/3/search/jql"
    assert kwargs["params"]["jql"] == 'project = "KAN"'


def test_search_issues_pages_through_nextpagetoken_until_islast():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token123")
    page_1 = {"issues": [{"key": "KAN-1"}], "isLast": False, "nextPageToken": "cursor-abc"}
    page_2 = {"issues": [{"key": "KAN-2"}], "isLast": True}

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.side_effect = [_fake_response(200, page_1), _fake_response(200, page_2)]
        issues = client.search_issues('project = "KAN"')

    assert [i["key"] for i in issues] == ["KAN-1", "KAN-2"]
    assert mock_get.call_count == 2
    second_call_params = mock_get.call_args_list[1].kwargs["params"]
    assert second_call_params["nextPageToken"] == "cursor-abc"
