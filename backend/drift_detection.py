"""Drift detection: flip a RequirementLink to Suspect when its Jira
requirement's content has changed (Milestone 4, issue #17).

Triggered from both delivery paths that tell us "this issue changed" -
the webhook receiver (issue #10) and the polling fallback (issue #11) -
so it works the same way regardless of which one a given Jira instance
supports. Always re-pulls the issue's current full content rather than
trying to read it out of the webhook payload/changelog, since a polled
"changed" event carries no changelog at all (see jira_polling.py) and a
webhook's own payload doesn't reliably include description - one code
path for both keeps them consistent.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.change_summary import summarize_change
from backend.jira_client import JiraClient
from backend.jira_requirements import pull_requirement
from backend.models import RequirementLink
from backend.requirement_hash import hash_requirement_content
from backend.requirement_links import COVERED, SUSPECT


def detect_drift_for_issue(db: Session, client: JiraClient, issue_key: str) -> int:
    """Re-check one issue's live content against every non-suspect
    RequirementLink for it, flipping mismatches to Suspect. Returns how
    many links were flipped. Does not commit - the caller shares a
    transaction with whatever recorded the triggering event.

    A requirement that no longer resolves (deleted, wrong key) isn't
    treated as drift here - that's the "orphaned" case, resolved instead
    at read time (see requirement_links.resolve_effective_state), since
    there's no content to compare against or summarize a change from.
    """
    links = db.query(RequirementLink).filter(
        RequirementLink.jira_key == issue_key, RequirementLink.state == COVERED
    ).all()
    if not links:
        return 0

    requirement = pull_requirement(client, issue_key)
    if requirement is None:
        return 0

    new_hash = hash_requirement_content(requirement)
    flipped = 0
    # Multiple links against the same requirement typically share the same
    # content_hash (they were all linked against the same prior snapshot),
    # so summarize_change's input is identical across them - cache by that
    # hash rather than calling Claude once per link.
    summary_by_previous_hash: dict[str, str | None] = {}
    for link in links:
        if link.content_hash == new_hash:
            continue
        if link.content_hash not in summary_by_previous_hash:
            # The LLM summary is enrichment on top of the hash-based flag
            # itself (issue #19) - a failure here (no API key, a transient
            # API error) must not prevent the Suspect flag from being set,
            # which is the actual safety-relevant behavior.
            try:
                summary_by_previous_hash[link.content_hash] = summarize_change(link.content_snapshot, requirement)
            except Exception:
                summary_by_previous_hash[link.content_hash] = None
        link.change_summary = summary_by_previous_hash[link.content_hash]
        link.state = SUSPECT
        flipped += 1
    return flipped
