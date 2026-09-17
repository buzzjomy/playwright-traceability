"""Polling fallback for Jira instances without webhook access (issue #11).

Complements issue #10's webhook receiver: some Jira instances/networks
can't deliver webhooks at all (no admin access to configure one, a
firewall blocking inbound requests to a self-hosted backend, etc). This
polls Jira's search API instead, on whatever interval an external
scheduler (cron, a scheduled GitHub Action, etc.) triggers
POST /api/jira/poll - there's no in-process background scheduler here,
matching how scripts/push_test_inventory.py is also externally triggered
rather than self-scheduling.

Lower fidelity than webhooks by design: a JQL search only returns each
issue's CURRENT state, not a field-level diff, so polled events carry no
changelog (unlike a real webhook delivery) - just "this issue changed as
of this poll." Getting a real diff would mean an extra changelog fetch
per changed issue; deferred as unnecessary complexity for a fallback path
until proven needed.
"""

from __future__ import annotations

import math
from datetime import datetime

from backend.jira_client import JiraClient

POLLED_EVENT_TYPE = "jira:issue_polled"


def format_jql_relative_window(since: datetime, now: datetime) -> str:
    """Build a Jira JQL relative-time literal covering the window from
    since to now, e.g. "-45m".

    Jira Cloud's absolute JQL date/time literals are unreliable for
    anything but midnight - confirmed against a real site: every
    non-midnight absolute time-of-day literal tried (with or without
    seconds, at several different hours) silently matched zero issues,
    while a relative literal (e.g. "-5m") worked correctly down to
    minute precision. So the polling window is expressed in Jira's own
    relative-time syntax instead of an absolute timestamp - this
    sidesteps that bug entirely, and any timezone-conversion ambiguity
    along with it, since a relative literal needs no timezone context.

    Rounds UP so a partial minute is never silently dropped, with a
    floor of 1 minute - polls closer together than that just slightly
    overlap (a duplicate event, harmless) rather than risk the window
    rounding down to "0m" and missing something.
    """
    elapsed_seconds = (now - since).total_seconds()
    minutes = max(1, math.ceil(elapsed_seconds / 60))
    return f"-{minutes}m"


def poll_for_changes(client: JiraClient, project_key: str, since: datetime | None, now: datetime) -> list[dict]:
    """Return every issue in project_key updated between since and now.

    Returns [] if since is None, treating a first poll as establishing a
    baseline rather than fetching the entire project's history as if it
    all "just changed" (which would flood downstream consumers with
    noise on day one).
    """
    if since is None:
        return []

    jql = f'project = "{project_key}" AND updated >= "{format_jql_relative_window(since, now)}"'
    return client.search_issues(jql, fields=["summary", "updated"])
