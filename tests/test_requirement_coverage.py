from unittest.mock import patch

from backend.jira_client import JiraClient
from backend.requirement_coverage import build_coverage
from backend.test_inventory import InventoryEntry


def _fake_response(status_code: int, json_body: dict):
    class _Response:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return json_body

        def raise_for_status(self):
            pass

    return _Response()


def _issue(key: str, summary: str) -> dict:
    return {"key": key, "fields": {"summary": summary, "description": None}}


def _entry(file: str, title: str, jira_keys: list[str], project: str | None = None) -> InventoryEntry:
    return InventoryEntry(
        file=file,
        title=title,
        full_title=title,
        project=project,
        status="passed" if project else None,
        jira_keys=jira_keys,
        in_source=True,
        has_run=project is not None,
    )


def test_requirement_with_a_linked_test_is_covered():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    search_response = {"issues": [_issue("KAN-4", "Homepage loads")], "isLast": True}
    entries = [_entry("homepage.spec.ts", "should load", ["KAN-4"], project="chromium")]

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        coverage = build_coverage(client, "KAN", entries)

    assert len(coverage) == 1
    assert coverage[0].key == "KAN-4"
    assert coverage[0].linked_test_count == 1
    assert coverage[0].covered is True


def test_requirement_with_no_linked_test_is_uncovered():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    search_response = {"issues": [_issue("KAN-14", "Scratch issue")], "isLast": True}

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        coverage = build_coverage(client, "KAN", inventory_entries=[])

    assert coverage[0].linked_test_count == 0
    assert coverage[0].covered is False


def test_multi_project_test_counts_once_per_requirement():
    # Same test, two projects (chromium/firefox) - shouldn't double-count
    # toward the requirement's coverage.
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    search_response = {"issues": [_issue("KAN-5", "Search works")], "isLast": True}
    entries = [
        _entry("search.spec.ts", "should search", ["KAN-5"], project="chromium"),
        _entry("search.spec.ts", "should search", ["KAN-5"], project="firefox"),
    ]

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        coverage = build_coverage(client, "KAN", entries)

    assert coverage[0].linked_test_count == 1


def test_two_different_tests_linking_the_same_requirement_both_count():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    search_response = {"issues": [_issue("KAN-5", "Search works")], "isLast": True}
    entries = [
        _entry("search.spec.ts", "should search by keyword", ["KAN-5"], project="chromium"),
        _entry("search.spec.ts", "should search by voice", ["KAN-5"], project="chromium"),
    ]

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        coverage = build_coverage(client, "KAN", entries)

    assert coverage[0].linked_test_count == 2


def test_a_test_linked_to_an_unrelated_key_does_not_affect_coverage():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    search_response = {"issues": [_issue("KAN-4", "Homepage loads")], "isLast": True}
    entries = [_entry("other.spec.ts", "unrelated test", ["PROJ-999"], project="chromium")]

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        coverage = build_coverage(client, "KAN", entries)

    assert coverage[0].linked_test_count == 0
    assert coverage[0].covered is False
