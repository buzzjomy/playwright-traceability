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

    def _get(self, path: str) -> dict:
        """Issue a GET request against this Jira site and return the parsed JSON body."""
        response = requests.get(
            f"{self.site_url}{path}",
            auth=self._auth,
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT_SECONDS,
        )
        if response.status_code == 401:
            raise JiraAuthError("Jira rejected the given email/API token combination")
        response.raise_for_status()
        return response.json()

    def get_current_user(self) -> dict:
        """Call /myself to both validate credentials and identify the connected account."""
        return self._get("/rest/api/3/myself")
