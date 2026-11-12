"""Minimal Jira Cloud REST API client.

Handles just enough to support issue #6 (auth + connection setup) and set
up issue #7 (pulling requirement/story data) on the same client. Authenticates
either with email + API token over HTTP Basic Auth (see README's Jira
Integration section for why OAuth 2.0 (3-legged) was deferred) or, for
Marketplace customers, with a Forge app system token (issue #41).
"""

from __future__ import annotations

import requests

_TIMEOUT_SECONDS = 10


class JiraAuthError(Exception):
    """Raised when Jira rejects the credentials a client was built with."""


class JiraClient:
    """A thin wrapper around one Jira Cloud site's REST API.

    Two authentication modes, chosen by how it's built:

    - Basic (email + API token): local dev, the standalone dashboard, and
      the deployment owner's own tenant. `JiraClient(site_url, email, token)`.
    - Bearer (a Forge app system token): every Marketplace customer - the
      app calls Jira as its own bot user, so no customer credentials are
      ever collected. `JiraClient.with_bearer_token(api_base_url, token)`,
      where api_base_url is the `app.apiBaseUrl` claim of the verified
      Forge Invocation Token (https://api.atlassian.com/ex/jira/<cloudId>).
    """

    def __init__(
        self, site_url: str, email: str | None = None, api_token: str | None = None, *, bearer_token: str | None = None
    ) -> None:
        self.site_url = site_url.rstrip("/")
        self._auth = (email, api_token) if bearer_token is None else None
        self._bearer_token = bearer_token

    @classmethod
    def with_bearer_token(cls, api_base_url: str, token: str) -> "JiraClient":
        """A client that authenticates with a Forge app system token."""
        return cls(api_base_url, bearer_token=token)

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Issue a GET request against this Jira site and return the parsed JSON body."""
        headers = {"Accept": "application/json"}
        if self._bearer_token is not None:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        response = requests.get(
            f"{self.site_url}{path}",
            auth=self._auth,
            headers=headers,
            params=params,
            timeout=_TIMEOUT_SECONDS,
        )
        if response.status_code == 401:
            raise JiraAuthError("Jira rejected the given credentials")
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
