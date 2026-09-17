"""Requirement coverage: which Jira requirements have zero linked tests
(Milestone 3, issue #13).

Combines pull_requirements() (issue #7) with the reconciled test
inventory (issue #12) to answer "for each Jira requirement in a project,
how many tests reference it?" A requirement with zero linked tests is
"uncovered" - the core signal this view exists to surface, per
CLAUDE.md's traceability differentiator: knowing a linked test exists at
all is the prerequisite for the later semantic-gap-detection work (which
checks whether a linked test's *content* still matches the requirement,
not just whether one exists).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from backend.jira_client import JiraClient
from backend.jira_requirements import pull_requirements
from backend.test_inventory import InventoryEntry


@dataclass
class CoverageEntry:
    """One Jira requirement's test coverage."""

    key: str
    summary: str
    linked_test_count: int
    covered: bool

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of this entry."""
        return {
            "key": self.key,
            "summary": self.summary,
            "linked_test_count": self.linked_test_count,
            "covered": self.covered,
        }


def _count_tests_per_jira_key(entries: list[InventoryEntry]) -> Counter:
    """Count distinct (file, title) tests referencing each Jira key.

    Distinct per test, not per inventory row, so a multi-project test
    (one row per project - see backend/test_inventory.py) counts once
    toward a requirement's coverage, not once per project it ran under.
    """
    seen: set[tuple[str, str, str]] = set()
    counts: Counter = Counter()
    for entry in entries:
        for jira_key in entry.jira_keys:
            dedup_key = (entry.file, entry.title, jira_key)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            counts[jira_key] += 1
    return counts


def build_coverage(
    client: JiraClient,
    project_key: str,
    inventory_entries: list[InventoryEntry],
    issue_types: list[str] | None = None,
) -> list[CoverageEntry]:
    """Build per-requirement test coverage for a Jira project."""
    requirements = pull_requirements(client, project_key, issue_types=issue_types)
    counts = _count_tests_per_jira_key(inventory_entries)

    return [
        CoverageEntry(
            key=requirement.key,
            summary=requirement.summary,
            linked_test_count=counts.get(requirement.key, 0),
            covered=counts.get(requirement.key, 0) > 0,
        )
        for requirement in requirements
    ]
