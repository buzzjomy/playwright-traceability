"""Hash a Jira requirement's substantive fields (Milestone 4, issue #16).

The hash is what makes a link "suspect-able": snapshotted at link time and
recomputed on drift detection (issue #17), a mismatch means the
requirement's actual content has changed since a test was linked to it -
not just that *some* field on the Jira issue changed (status transitions,
assignee, sprint, etc. are all irrelevant to whether a test still covers
the requirement).
"""

from __future__ import annotations

import hashlib

from backend.jira_requirements import JiraRequirement

_FIELD_SEPARATOR = "␟"  # unlikely to appear in real text; keeps fields from colliding when concatenated


def hash_requirement_content(requirement: JiraRequirement) -> str:
    """Hash a requirement's summary, description, and acceptance criteria.

    Any change to any of these three fields changes the hash; anything
    else about the Jira issue is ignored.
    """
    payload = _FIELD_SEPARATOR.join(
        [requirement.summary, requirement.description_text, *requirement.acceptance_criteria]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
