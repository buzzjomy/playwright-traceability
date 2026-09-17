from datetime import datetime, timedelta
from unittest.mock import patch

from backend.jira_client import JiraClient
from backend.jira_polling import format_jql_relative_window, poll_for_changes


def _fake_response(status_code: int, json_body: dict):
    class _Response:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return json_body

        def raise_for_status(self):
            pass

    return _Response()


def test_format_jql_relative_window_rounds_up_to_the_minute():
    since = datetime(2026, 9, 17, 7, 0, 0)
    now = datetime(2026, 9, 17, 7, 44, 30)  # 44m30s elapsed
    assert format_jql_relative_window(since, now) == "-45m"


def test_format_jql_relative_window_floors_at_one_minute():
    since = datetime(2026, 9, 17, 7, 0, 0)
    now = datetime(2026, 9, 17, 7, 0, 10)  # 10s elapsed - would round to 0m
    assert format_jql_relative_window(since, now) == "-1m"


def test_format_jql_relative_window_exact_minute_boundary():
    since = datetime(2026, 9, 17, 7, 0, 0)
    now = datetime(2026, 9, 17, 7, 5, 0)
    assert format_jql_relative_window(since, now) == "-5m"


def test_poll_for_changes_returns_empty_on_first_poll_with_no_since():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    now = datetime(2026, 9, 17, 7, 0, 0)
    with patch("backend.jira_client.requests.get") as mock_get:
        result = poll_for_changes(client, "KAN", since=None, now=now)

    assert result == []
    mock_get.assert_not_called()


def test_poll_for_changes_builds_relative_jql_not_an_absolute_timestamp():
    # Real Jira Cloud finding: absolute JQL date/time literals (any
    # non-midnight time-of-day, with or without seconds) silently match
    # zero issues - confirmed against a real site. Relative literals
    # ("-Nm") work correctly, so that's what must be sent.
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    since = datetime(2026, 9, 17, 7, 0, 0)
    now = since + timedelta(minutes=10)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"issues": [], "isLast": True})
        poll_for_changes(client, "KAN", since=since, now=now)

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["jql"] == 'project = "KAN" AND updated >= "-10m"'
    assert ":" not in kwargs["params"]["jql"]  # no absolute time-of-day literal


def test_poll_for_changes_returns_matching_issues():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    since = datetime(2026, 9, 17, 7, 0)
    now = since + timedelta(minutes=5)

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(
            200, {"issues": [{"key": "KAN-4"}, {"key": "KAN-5"}], "isLast": True}
        )
        result = poll_for_changes(client, "KAN", since=since, now=now)

    assert [i["key"] for i in result] == ["KAN-4", "KAN-5"]
