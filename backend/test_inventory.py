"""Reconcile run-based and source-based test records into one inventory
view (Milestone 3, issue #12).

TestRunRecord (from a pushed run) and SourceTestRecord (from a static
.spec.ts/.feature scan) have been independent, unreconciled streams since
Milestone 1 - this is where they finally get combined, using the simple
(file, title) match flagged as sufficient back then rather than a more
elaborate reconciliation system.

Multi-project runs are deliberately NOT collapsed (same principle as
Milestone 1's TestRecord): a test that ran under both chromium and
firefox produces one inventory row per project, since they can have
independently different outcomes. A test found only in source (never
run - skipped, filtered out, or just not part of the pushed run) or only
in a run (no matching source - e.g. a dynamically-generated title a
static scan can never resolve, or a test since deleted from source) is
still included as its own row, with in_source/has_run reflecting which
side(s) actually matched.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from backend.models import SourceTestRecord, TestRunRecord


@dataclass
class InventoryEntry:
    """One reconciled row: a test, as run under one project (or never run)."""

    file: str
    title: str
    full_title: str
    project: str | None  # None if this test has never been run
    status: str | None  # None if this test has never been run
    tags: list[str] = field(default_factory=list)
    jira_keys: list[str] = field(default_factory=list)
    in_source: bool = False
    has_run: bool = False

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of this entry."""
        return {
            "file": self.file,
            "title": self.title,
            "full_title": self.full_title,
            "project": self.project,
            "status": self.status,
            "tags": self.tags,
            "jira_keys": self.jira_keys,
            "in_source": self.in_source,
            "has_run": self.has_run,
        }


def build_inventory(db: Session) -> list[InventoryEntry]:
    """Build the reconciled test inventory from the current DB contents."""
    source_by_key: dict[tuple[str, str], SourceTestRecord] = {}
    for record in db.query(SourceTestRecord).all():
        source_by_key[(record.file, record.title)] = record

    # Keep only the latest TestRunRecord per (file, title, project) -
    # TestRunRecord is append-only across every push, but the inventory
    # shows current status, not full history (that's issue #14's job).
    latest_run_by_key: dict[tuple[str, str, str], TestRunRecord] = {}
    for record in db.query(TestRunRecord).order_by(TestRunRecord.run_id.asc()).all():
        latest_run_by_key[(record.file, record.title, record.project)] = record

    runs_by_test: dict[tuple[str, str], list[TestRunRecord]] = defaultdict(list)
    for record in latest_run_by_key.values():
        runs_by_test[(record.file, record.title)].append(record)

    entries: list[InventoryEntry] = []
    for key in set(source_by_key) | set(runs_by_test):
        file, title = key
        source = source_by_key.get(key)
        runs = runs_by_test.get(key, [])

        tags = set(source.tags if source else [])
        jira_keys = set(source.jira_keys if source else [])
        for run in runs:
            tags |= set(run.tags)
            jira_keys |= set(run.jira_keys)

        full_title = (runs[0].full_title if runs else None) or (source.full_title if source else title)

        if not runs:
            entries.append(
                InventoryEntry(
                    file=file,
                    title=title,
                    full_title=full_title,
                    project=None,
                    status=None,
                    tags=sorted(tags),
                    jira_keys=sorted(jira_keys),
                    in_source=True,
                    has_run=False,
                )
            )
        else:
            for run in sorted(runs, key=lambda r: r.project):
                entries.append(
                    InventoryEntry(
                        file=file,
                        title=title,
                        full_title=full_title,
                        project=run.project,
                        status=run.status,
                        tags=sorted(tags),
                        jira_keys=sorted(jira_keys),
                        in_source=source is not None,
                        has_run=True,
                    )
                )

    entries.sort(key=lambda e: (e.file, e.title, e.project or ""))
    return entries
