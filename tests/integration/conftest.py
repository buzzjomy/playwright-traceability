"""Shared fixtures for the real-Jira integration suite (tests/integration/).

Every test here talks to a real, live Jira Cloud site - see
tests/integration/README.md for why this suite exists, what it's allowed
to do, and how to run it. Auto-skips the whole directory unless the
required environment variables are set, so `pytest tests/` (the default,
mocked suite) is unaffected whether or not real credentials are available.
"""

from __future__ import annotations

import os

import pytest

from backend.jira_client import JiraClient

JIRA_SITE_URL = os.environ.get("JIRA_SITE_URL")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_TEST_PROJECT_KEY = os.environ.get("JIRA_TEST_PROJECT_KEY", "KAN")
JIRA_TEST_ISSUE_KEY = os.environ.get("JIRA_TEST_ISSUE_KEY")

_REQUIRED_VARS = {
    "JIRA_SITE_URL": JIRA_SITE_URL,
    "JIRA_EMAIL": JIRA_EMAIL,
    "JIRA_API_TOKEN": JIRA_API_TOKEN,
    "JIRA_TEST_ISSUE_KEY": JIRA_TEST_ISSUE_KEY,
}


@pytest.fixture(autouse=True)
def _require_real_jira_credentials() -> None:
    """Skip every test in this directory unless real credentials are set.

    A module-level `pytestmark` doesn't apply across files from a
    conftest.py - an autouse fixture is the reliable way to gate an
    entire directory.
    """
    missing = [name for name, value in _REQUIRED_VARS.items() if not value]
    if missing:
        pytest.skip(f"Real Jira credentials not configured - missing: {', '.join(missing)}")


@pytest.fixture()
def jira_client() -> JiraClient:
    """A JiraClient authenticated against the real site under test."""
    return JiraClient(JIRA_SITE_URL, JIRA_EMAIL, JIRA_API_TOKEN)
