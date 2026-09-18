"""Requirement<->test link state (Milestone 4, issues #16/#18/#20).

Ties together the reconciled test inventory (issue #12) and live Jira
requirement data (issue #7) into persisted RequirementLink rows, so a
link's suspect-ness survives across requests instead of being recomputed
from scratch - drift detection (issue #17) needs somewhere to durably
flip a flag, and a human's "reviewed" action (issue #20) needs something
to clear.

Two states are stored on the row ("covered" / "suspect" - see
RequirementLink's docstring for why); "stale" and "orphaned" are resolved
here at read time by cross-referencing current inventory/requirement data,
since neither needs event-driven detection the way a Jira content change
does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.jira_requirements import JiraRequirement
from backend.models import RequirementLink
from backend.requirement_hash import hash_requirement_content
from backend.test_inventory import InventoryEntry

COVERED = "covered"
SUSPECT = "suspect"
STALE = "stale"
ORPHANED = "orphaned"


@dataclass
class RequirementLinkView:
    """One requirement<->test link with its effective (read-time-resolved) state."""

    id: int
    jira_key: str
    test_file: str
    test_title: str
    state: str
    change_summary: str | None
    linked_at: datetime
    last_reviewed_at: datetime | None

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of this view."""
        return {
            "id": self.id,
            "jira_key": self.jira_key,
            "test_file": self.test_file,
            "test_title": self.test_title,
            "state": self.state,
            "change_summary": self.change_summary,
            "linked_at": self.linked_at.isoformat(),
            "last_reviewed_at": self.last_reviewed_at.isoformat() if self.last_reviewed_at else None,
        }


def sync_requirement_links(
    db: Session, requirements: list[JiraRequirement], inventory_entries: list[InventoryEntry]
) -> None:
    """Create a RequirementLink (state=covered, hashed now) for every
    (jira_key, test) pair newly observed in the inventory - issue #16's
    "hash at link time". Does not modify existing links; drift detection
    (issue #17) and the reviewed action (issue #20) are what change an
    existing link's state afterward. Does not commit - callers share a
    transaction with whatever else they're doing (e.g. the endpoint that
    triggers this).
    """
    requirement_by_key = {r.key: r for r in requirements}
    existing = {(l.jira_key, l.test_file, l.test_title) for l in db.query(RequirementLink).all()}

    seen_this_call: set[tuple[str, str, str]] = set()
    for entry in inventory_entries:
        for jira_key in entry.jira_keys:
            dedup_key = (jira_key, entry.file, entry.title)
            if dedup_key in existing or dedup_key in seen_this_call:
                continue
            requirement = requirement_by_key.get(jira_key)
            if requirement is None:
                # Can't hash content we don't have (wrong key, different
                # project, or an issue type outside what was pulled) - the
                # link is created once it's next seen alongside a
                # resolvable requirement.
                continue
            db.add(
                RequirementLink(
                    jira_key=jira_key,
                    test_file=entry.file,
                    test_title=entry.title,
                    state=COVERED,
                    content_hash=hash_requirement_content(requirement),
                    content_snapshot=requirement.to_dict(),
                )
            )
            seen_this_call.add(dedup_key)


def resolve_effective_state(link: RequirementLink, test_exists: bool, requirement_exists: bool) -> str:
    """Resolve a link's displayed state, layering the cheap-to-derive
    "orphaned"/"stale" cases on top of the stored covered/suspect state.
    """
    if not requirement_exists:
        return ORPHANED
    if not test_exists:
        return STALE
    return link.state


def list_requirement_links(
    db: Session, project_key: str, requirements: list[JiraRequirement], inventory_entries: list[InventoryEntry]
) -> list[RequirementLinkView]:
    """Return every RequirementLink for a project, with effective state resolved.

    Scoped by Jira key prefix ("KAN-") rather than by the pulled
    requirements list, so an orphaned link (whose key no longer resolves
    in Jira at all) still shows up instead of silently disappearing.
    """
    requirement_keys = {r.key for r in requirements}
    test_keys = {(e.file, e.title) for e in inventory_entries}

    links = db.query(RequirementLink).filter(RequirementLink.jira_key.like(f"{project_key}-%")).all()

    views = [
        RequirementLinkView(
            id=link.id,
            jira_key=link.jira_key,
            test_file=link.test_file,
            test_title=link.test_title,
            state=resolve_effective_state(
                link,
                test_exists=(link.test_file, link.test_title) in test_keys,
                requirement_exists=link.jira_key in requirement_keys,
            ),
            change_summary=link.change_summary,
            linked_at=link.linked_at,
            last_reviewed_at=link.last_reviewed_at,
        )
        for link in links
    ]
    views.sort(key=lambda v: (v.jira_key, v.test_file, v.test_title))
    return views


def mark_reviewed(link: RequirementLink, requirement: JiraRequirement, reviewed_at: datetime) -> None:
    """Re-snapshot a link's hash/content from a freshly-pulled requirement
    and clear its suspect state (issue #20) - the only way a Suspect link
    is ever cleared, on purpose. Does not commit.
    """
    link.content_hash = hash_requirement_content(requirement)
    link.content_snapshot = requirement.to_dict()
    link.state = COVERED
    link.change_summary = None
    link.last_reviewed_at = reviewed_at
