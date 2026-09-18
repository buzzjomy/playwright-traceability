"""Reconcile run-based and source-based test records into one inventory
view (Milestone 3, issue #12), including each test's pass/fail history
over time (issue #14) and whether its latest run was flaky (issue #15).

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
from datetime import datetime

from sqlalchemy.orm import Session

from backend.models import SourceTestRecord, TestRun, TestRunRecord

# History is capped per (file, title, project) so the inventory payload
# stays bounded as a suite accumulates hundreds of pushed runs over time -
# the dashboard only needs a recent trend, not the entire run archive.
MAX_HISTORY_POINTS = 10


@dataclass
class TrendPoint:
    """One historical run outcome for a single (file, title, project) test."""

    run_id: int
    pushed_at: datetime
    status: str

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of this point."""
        return {
            "run_id": self.run_id,
            "pushed_at": self.pushed_at.isoformat(),
            "status": self.status,
        }


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
    assertions: list[str] = field(default_factory=list)  # static-source only (issue #21) - see SourceTestRecord
    in_source: bool = False
    has_run: bool = False
    history: list[TrendPoint] = field(default_factory=list)  # oldest first, most recent last
    is_flaky: bool = False  # latest run passed on retry after failing at least once

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
            "assertions": self.assertions,
            "in_source": self.in_source,
            "has_run": self.has_run,
            "history": [point.to_dict() for point in self.history],
            "is_flaky": self.is_flaky,
        }


def build_inventory(db: Session) -> list[InventoryEntry]:
    """Build the reconciled test inventory from the current DB contents."""
    source_by_key: dict[tuple[str, str], SourceTestRecord] = {}
    for record in db.query(SourceTestRecord).all():
        source_by_key[(record.file, record.title)] = record

    pushed_at_by_run_id: dict[int, datetime] = {run.id: run.pushed_at for run in db.query(TestRun).all()}

    # TestRunRecord is append-only across every push - every row (not just
    # the latest) is kept here so a per-project trend history can be built,
    # in run order, and the latest one still drives current status/tags.
    all_runs_by_key: dict[tuple[str, str, str], list[TestRunRecord]] = defaultdict(list)
    for record in db.query(TestRunRecord).order_by(TestRunRecord.run_id.asc()).all():
        all_runs_by_key[(record.file, record.title, record.project)].append(record)

    runs_by_test: dict[tuple[str, str], list[TestRunRecord]] = defaultdict(list)
    for records in all_runs_by_key.values():
        runs_by_test[(records[-1].file, records[-1].title)].append(records[-1])

    entries: list[InventoryEntry] = []
    for key in set(source_by_key) | set(runs_by_test):
        file, title = key
        source = source_by_key.get(key)
        latest_runs = runs_by_test.get(key, [])

        tags = set(source.tags if source else [])
        jira_keys = set(source.jira_keys if source else [])
        # Run report data never carries assertions (Playwright's JSON
        # reporter doesn't emit them) - source is the only possible origin.
        assertions = source.assertions if source else []
        for run in latest_runs:
            tags |= set(run.tags)
            jira_keys |= set(run.jira_keys)

        full_title = (latest_runs[0].full_title if latest_runs else None) or (
            source.full_title if source else title
        )

        if not latest_runs:
            entries.append(
                InventoryEntry(
                    file=file,
                    title=title,
                    full_title=full_title,
                    project=None,
                    status=None,
                    tags=sorted(tags),
                    jira_keys=sorted(jira_keys),
                    assertions=assertions,
                    in_source=True,
                    has_run=False,
                )
            )
        else:
            for run in sorted(latest_runs, key=lambda r: r.project):
                history = [
                    TrendPoint(run_id=r.run_id, pushed_at=pushed_at_by_run_id[r.run_id], status=r.status)
                    for r in all_runs_by_key[(run.file, run.title, run.project)][-MAX_HISTORY_POINTS:]
                ]
                entries.append(
                    InventoryEntry(
                        file=file,
                        title=title,
                        full_title=full_title,
                        project=run.project,
                        status=run.status,
                        tags=sorted(tags),
                        jira_keys=sorted(jira_keys),
                        assertions=assertions,
                        in_source=source is not None,
                        has_run=True,
                        history=history,
                        is_flaky=run.is_flaky,
                    )
                )

    entries.sort(key=lambda e: (e.file, e.title, e.project or ""))
    return entries


def entries_for_jira_key(entries: list[InventoryEntry], jira_key: str) -> list[InventoryEntry]:
    """Return the distinct (file, title) tests linked to one Jira key.

    Deduped across projects the same way requirement_coverage's counting
    does - a test that ran under both chromium and firefox is one piece of
    evidence, not two.
    """
    seen: set[tuple[str, str]] = set()
    result: list[InventoryEntry] = []
    for entry in entries:
        if jira_key not in entry.jira_keys:
            continue
        dedup_key = (entry.file, entry.title)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        result.append(entry)
    return result
