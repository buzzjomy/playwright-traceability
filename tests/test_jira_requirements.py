from unittest.mock import patch

from backend.jira_client import JiraClient
from backend.jira_requirements import (
    extract_acceptance_criteria,
    extract_plain_text,
    pull_requirements,
)

# Real-shaped ADF, matching what demo/google-search's KAN-4 story actually
# looks like on the live Jira site (see backend/jira_requirements.py's
# docstring for why AC is parsed from a heading + list, not a custom field).
REAL_SHAPED_ADF = {
    "type": "doc",
    "version": 1,
    "content": [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "As a visitor, I want the homepage to load, so that I can search."}],
        },
        {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Acceptance Criteria"}]},
        {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "The logo is visible."}]}],
                },
                {
                    "type": "listItem",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "A search box is visible."}]}
                    ],
                },
            ],
        },
    ],
}


def _fake_response(status_code: int, json_body: dict):
    class _Response:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return json_body

        def raise_for_status(self):
            pass

    return _Response()


def _issue(key: str, summary: str, description: dict | None = None) -> dict:
    return {"key": key, "fields": {"summary": summary, "description": description}}


def test_extract_plain_text_renders_paragraphs_headings_and_list_items():
    text = extract_plain_text(REAL_SHAPED_ADF)
    assert "As a visitor, I want the homepage to load, so that I can search." in text
    assert "Acceptance Criteria" in text
    assert "- The logo is visible." in text
    assert "- A search box is visible." in text


def test_extract_plain_text_handles_none():
    assert extract_plain_text(None) == ""


def test_extract_acceptance_criteria_finds_bullets_after_heading():
    acs = extract_acceptance_criteria(REAL_SHAPED_ADF)
    assert acs == ["The logo is visible.", "A search box is visible."]


def test_extract_acceptance_criteria_returns_empty_without_heading():
    adf = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Just a plain description."}]}]}
    assert extract_acceptance_criteria(adf) == []


def test_extract_acceptance_criteria_returns_empty_when_heading_has_no_list():
    adf = {
        "type": "doc",
        "content": [
            {"type": "heading", "content": [{"type": "text", "text": "Acceptance Criteria"}]},
            {"type": "heading", "content": [{"type": "text", "text": "Notes"}]},
        ],
    }
    assert extract_acceptance_criteria(adf) == []


def test_extract_acceptance_criteria_is_case_insensitive():
    adf = {
        "type": "doc",
        "content": [
            {"type": "heading", "content": [{"type": "text", "text": "ACCEPTANCE CRITERIA"}]},
            {
                "type": "bulletList",
                "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "One thing."}]}]}
                ],
            },
        ],
    }
    assert extract_acceptance_criteria(adf) == ["One thing."]


def test_pull_requirements_builds_records_from_search_results():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    search_response = {
        "issues": [_issue("KAN-4", "Homepage loads", REAL_SHAPED_ADF)],
        "isLast": True,
    }

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        requirements = pull_requirements(client, "KAN")

    assert len(requirements) == 1
    req = requirements[0]
    assert req.key == "KAN-4"
    assert req.summary == "Homepage loads"
    assert req.acceptance_criteria == ["The logo is visible.", "A search box is visible."]

    # Confirm the JQL sent restricts by project and the default issue types.
    _, kwargs = mock_get.call_args
    assert 'project = "KAN"' in kwargs["params"]["jql"]
    assert "Story" in kwargs["params"]["jql"]
    assert "Task" in kwargs["params"]["jql"]


def test_pull_requirements_handles_issue_with_no_description():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    search_response = {"issues": [_issue("KAN-5", "No description here", None)], "isLast": True}

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        requirements = pull_requirements(client, "KAN")

    assert requirements[0].description_text == ""
    assert requirements[0].acceptance_criteria == []


def test_pull_requirements_with_custom_issue_types():
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")
    search_response = {"issues": [], "isLast": True}

    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, search_response)
        pull_requirements(client, "KAN", issue_types=["Epic"])

    _, kwargs = mock_get.call_args
    assert '"Epic"' in kwargs["params"]["jql"]
    assert "Story" not in kwargs["params"]["jql"]
