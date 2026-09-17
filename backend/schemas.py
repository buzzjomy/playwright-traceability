"""Pydantic request/response models for the backend API."""

from __future__ import annotations

from pydantic import BaseModel, HttpUrl


class JiraConnectionCreate(BaseModel):
    """Request body for setting up a Jira Cloud connection."""

    site_url: HttpUrl
    email: str
    api_token: str


class JiraConnectionStatus(BaseModel):
    """Response body describing the current Jira connection, if any.

    Never includes the API token - only enough to confirm what's connected.
    """

    connected: bool
    site_url: str | None = None
    email: str | None = None
    account_id: str | None = None
    display_name: str | None = None
