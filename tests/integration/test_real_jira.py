"""Regression tests against a real, live Jira Cloud site.

Exists because of a real bug this suite would have caught: issue #11's
first polling implementation built an absolute JQL date literal, which
silently matched zero issues against the real API (no error - it just
never found anything). Nothing in the mocked unit test suite could catch
that, since the mocks encode our own assumptions about Jira's behavior,
not Jira's actual behavior. See tests/integration/README.md for how to
run this locally, and .github/workflows/real-jira-integration.yml for the
scheduled CI job that runs it automatically.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

import requests

from backend.jira_client import JiraClient
from backend.jira_polling import poll_for_changes
from backend.jira_requirements import pull_requirements

# Read directly rather than importing from conftest.py - a relative
# import here needs tests/integration to be a proper package, which
# pytest's rootdir-based test discovery doesn't assume by default.
JIRA_SITE_URL = os.environ.get("JIRA_SITE_URL")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_TEST_PROJECT_KEY = os.environ.get("JIRA_TEST_PROJECT_KEY", "KAN")
JIRA_TEST_ISSUE_KEY = os.environ.get("JIRA_TEST_ISSUE_KEY")


def _touch_scratch_issue(new_summary: str) -> None:
    """Update the dedicated scratch issue's summary, to produce a real
    `updated` timestamp change for the polling test to detect.

    Uses requests directly rather than adding a write method to
    JiraClient - editing issues isn't a product feature of this tool
    (it only reads Jira), so this stays test-only scaffolding.
    """
    response = requests.put(
        f"{JIRA_SITE_URL.rstrip('/')}/rest/api/3/issue/{JIRA_TEST_ISSUE_KEY}",
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        json={"fields": {"summary": new_summary}},
        timeout=10,
    )
    response.raise_for_status()


def test_can_authenticate_against_real_jira(jira_client: JiraClient) -> None:
    me = jira_client.get_current_user()
    assert "accountId" in me


def test_pull_requirements_returns_real_project_data(jira_client: JiraClient) -> None:
    requirements = pull_requirements(jira_client, JIRA_TEST_PROJECT_KEY)

    assert len(requirements) > 0
    for requirement in requirements:
        assert requirement.key.startswith(f"{JIRA_TEST_PROJECT_KEY}-")
        assert requirement.summary


def test_search_issues_uses_the_still_working_endpoint(jira_client: JiraClient) -> None:
    # Regression check for the /rest/api/3/search removal found in issue
    # #7 - confirms /rest/api/3/search/jql (what search_issues actually
    # calls) still works, so a future Atlassian API change gets noticed.
    issues = jira_client.search_issues(f'project = "{JIRA_TEST_PROJECT_KEY}"', fields=["summary"])
    assert len(issues) > 0


def test_polling_detects_a_real_change(jira_client: JiraClient) -> None:
    """The money test: re-creates the exact scenario the issue #11 bug
    broke. A poll must detect a change that happens after `since` -
    if this regresses to using an absolute JQL literal again, Jira's
    real API will silently return zero results here, same as it did the
    first time this was built.
    """
    since = datetime.now(timezone.utc).replace(tzinfo=None)

    nonce = uuid.uuid4().hex[:8]
    _touch_scratch_issue(f"[Integration Test Scratch Issue - DO NOT EDIT MANUALLY] {nonce}")
    time.sleep(2)  # Jira's search index needs a moment to catch up

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    changed = poll_for_changes(jira_client, JIRA_TEST_PROJECT_KEY, since=since, now=now)

    assert JIRA_TEST_ISSUE_KEY in [issue["key"] for issue in changed]


def test_dynamic_webhook_registration_still_requires_oauth() -> None:
    # Regression check for the issue #10 finding: if Atlassian ever
    # allows Basic Auth here, the manual "classic webhook" setup this
    # repo relies on could potentially be replaced with self-registration.
    response = requests.post(
        f"{JIRA_SITE_URL.rstrip('/')}/rest/api/3/webhook",
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        json={"url": "https://example.com/webhook", "webhooks": [{"events": ["jira:issue_updated"]}]},
        timeout=10,
    )
    assert response.status_code == 403
