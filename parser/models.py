"""Data models for parsed Playwright test records.

These are deliberately plain dataclasses (not Pydantic/SQLAlchemy) so this
module has zero dependencies and can be unit tested or reused standalone
before it's wired into the FastAPI service.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TestRecord:
    """One (spec x project) test outcome, flattened from a run's JSON report."""

    spec_id: str
    title: str
    full_title: str          # "Login flow > should login with valid credentials"
    file: str
    line: int
    column: int
    project: str             # e.g. "chromium", "firefox"
    tags: list[str] = field(default_factory=list)
    jira_keys: list[str] = field(default_factory=list)
    status: str = "unknown"  # passed | failed | timedOut | skipped | interrupted
    duration_ms: int = 0     # duration of the final (deciding) attempt
    retry_count: int = 0     # number of retries beyond the first attempt
    is_flaky: bool = False   # failed at least once, but final result passed
    error_message: str | None = None

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of this record."""
        return {
            "spec_id": self.spec_id,
            "title": self.title,
            "full_title": self.full_title,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "project": self.project,
            "tags": self.tags,
            "jira_keys": self.jira_keys,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "is_flaky": self.is_flaky,
            "error_message": self.error_message,
        }


@dataclass
class StaticTestRecord:
    """One `test()` definition found by statically parsing a .spec.ts file.

    Unlike TestRecord, this has no run outcome (status/duration/etc) — it
    exists to catch tests and Jira annotations that a JSON run report would
    never show at all: skipped, grep-filtered out, or simply never executed.
    Tests with a dynamically-built title (e.g. inside a loop) are not
    represented here — see static_parser/parse_specs.js for why.
    """

    title: str
    full_title: str
    file: str
    line: int
    column: int
    tags: list[str] = field(default_factory=list)
    jira_keys: list[str] = field(default_factory=list)
    assertions: list[str] = field(default_factory=list)  # raw `expect(...)` call source text (issue #21)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of this record."""
        return {
            "title": self.title,
            "full_title": self.full_title,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "tags": self.tags,
            "jira_keys": self.jira_keys,
            "assertions": self.assertions,
        }


@dataclass
class FeatureTestRecord:
    """One concrete Gherkin scenario, from a .feature file.

    A Scenario Outline with an Examples table expands into one record per
    example row, with <placeholder> values substituted into the scenario
    name (mirroring how Cucumber substitutes them into step text) — unlike
    a data-driven .spec.ts loop, Examples table values are written directly
    in source, so every row is fully knowable statically.
    """

    title: str
    full_title: str
    file: str
    line: int
    column: int
    tags: list[str] = field(default_factory=list)
    jira_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of this record."""
        return {
            "title": self.title,
            "full_title": self.full_title,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "tags": self.tags,
            "jira_keys": self.jira_keys,
        }
