"""Minimal Jira Cloud REST API client.

Handles just enough to support issue #6 (auth + connection setup) and set
up issue #7 (pulling requirement/story data) on the same client. Uses
email + API token via HTTP Basic Auth, per Atlassian's documented Jira
Cloud REST API auth scheme - see README's Jira Integration section for why
OAuth 2.0 (3-legged) was deferred for the MVP.
"""

from __future__ import annotations

import requests

_TIMEOUT_SECONDS = 10


class JiraAuthError(Exception):
    """Raised when Jira rejects the given email/API token combination."""


class JiraClient:
    """A thin wrapper around one Jira Cloud site's REST API.

    Authenticates every request via HTTP Basic Auth (email + API token).
    """

    def __init__(self, site_url: str, email: str, api_token: str) -> None:
        self.site_url = site_url.rstrip("/")
        self._auth = (email, api_token)

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Issue a GET request against this Jira site and return the parsed JSON body."""
        response = requests.get(
            f"{self.site_url}{path}",
            auth=self._auth,
            headers={"Accept": "application/json"},
            params=params,
            timeout=_TIMEOUT_SECONDS,
        )
        if response.status_code == 401:
            raise JiraAuthError("Jira rejected the given email/API token combination")
        response.raise_for_status()
        return response.json()

    def get_current_user(self) -> dict:
        """Call /myself to both validate credentials and identify the connected account."""
        return self._get("/rest/api/3/myself")

    def get_issue(self, key: str, fields: list[str] | None = None) -> dict | None:
        """Fetch one issue by key. Returns None (rather than raising) if the
        issue doesn't exist or isn't visible to this account - drift
        detection (issue #17) treats that the same way either way: the
        link's "orphaned" state is derived from this, not a hard failure.
        """
        fields = fields or ["summary", "description"]
        try:
            return self._get(f"/rest/api/3/issue/{key}", params={"fields": ",".join(fields)})
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    def search_issues(self, jql: str, fields: list[str] | None = None) -> list[dict]:
        """Return every issue matching a JQL query, paging via nextPageToken.

        Uses /rest/api/3/search/jql - Jira Cloud removed the older
        /rest/api/3/search endpoint (confirmed against a real site,
        pwtrace.atlassian.net, on 2026-09-17: it now returns an error
        telling callers to migrate). That endpoint's cursor-based
        pagination (nextPageToken/isLast) replaces the old startAt/total
        offset pagination.
        """
        fields = fields or ["summary", "description", "issuetype"]
        issues: list[dict] = []
        page_token: str | None = None

        while True:
            params = {"jql": jql, "maxResults": 100, "fields": ",".join(fields)}
            if page_token:
                params["nextPageToken"] = page_token

            page = self._get("/rest/api/3/search/jql", params=params)
            issues.extend(page["issues"])

            if page.get("isLast", True):
                break
            page_token = page["nextPageToken"]

        return issues
