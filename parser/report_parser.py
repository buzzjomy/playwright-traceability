"""Parses Playwright's built-in JSON reporter output into flat TestRecord objects.

Usage:
    npx playwright test --reporter=json > report.json
    python -m parser.report_parser report.json

Why parse the JSON reporter instead of source .spec.ts files:
    The JSON report always contains REAL, RESOLVED test titles and outcomes,
    regardless of whether tests were hand-written, generated in a loop, or
    authored via a BDD layer. Static source parsing is added later as an
    enrichment layer (for annotations/tags not visible in the run report),
    not as the primary source of truth.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from parser.models import TestRecord

# Matches Jira-style issue keys: PROJ-123, ABC-42, etc.
# Also strips an optional "Jira:" prefix (CTM-style annotation syntax) and a
# leading "@" (tag-style syntax), so "@PROJ-13" and "Jira:PROJ-13" both match.
JIRA_KEY_PATTERN = re.compile(r"(?:Jira:)?@?([A-Z][A-Z0-9]+-\d+)")


def extract_jira_keys(*texts: str) -> list[str]:
    """Pull unique Jira issue keys out of any number of strings (tags, annotations, titles)."""
    keys: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in JIRA_KEY_PATTERN.finditer(text):
            key = match.group(1)
            if key not in keys:
                keys.append(key)
    return keys


def _walk_suite(suite: dict, ancestor_titles: list[str]) -> list[TestRecord]:
    """Recursively walk a suite (which may itself contain nested suites)."""
    records: list[TestRecord] = []
    suite_title = suite.get("title", "")
    current_path = ancestor_titles + ([suite_title] if suite_title else [])

    for spec in suite.get("specs", []):
        records.extend(_parse_spec(spec, current_path))

    for nested_suite in suite.get("suites", []):
        records.extend(_walk_suite(nested_suite, current_path))

    return records


def _parse_spec(spec: dict, ancestor_titles: list[str]) -> list[TestRecord]:
    """A spec can have one `test` entry per project (chromium/firefox/etc)."""
    records: list[TestRecord] = []
    title = spec.get("title", "")
    full_title = " > ".join(ancestor_titles + [title]) if ancestor_titles else title
    tags = spec.get("tags", []) or []

    for test in spec.get("tests", []):
        project = test.get("projectName") or test.get("projectId") or "default"
        annotations = test.get("annotations", []) or []
        annotation_texts = [a.get("description", "") for a in annotations]

        jira_keys = extract_jira_keys(*tags, *annotation_texts, title)

        results = test.get("results", []) or []
        final_status, duration_ms, error_message = _resolve_outcome(results)
        is_flaky = test.get("status") == "flaky"

        records.append(
            TestRecord(
                spec_id=spec.get("id", ""),
                title=title,
                full_title=full_title,
                file=spec.get("file", ""),
                line=spec.get("line", 0),
                column=spec.get("column", 0),
                project=project,
                tags=tags,
                jira_keys=jira_keys,
                status=final_status,
                duration_ms=duration_ms,
                retry_count=max(len(results) - 1, 0),
                is_flaky=is_flaky,
                error_message=error_message,
            )
        )

    return records


def _resolve_outcome(results: list[dict]) -> tuple[str, int, str | None]:
    """Reduce a list of retry attempts down to one final outcome.

    Playwright retries a failing test up to N times; `results` holds one
    entry per attempt in order. The last attempt is the deciding one.
    """
    if not results:
        return "unknown", 0, None

    last = results[-1]
    final_status = last.get("status", "unknown")
    duration_ms = last.get("duration", 0)

    errors = last.get("errors", []) or []
    error_message = errors[0].get("message") if errors else None

    return final_status, duration_ms, error_message


def parse_report(report: dict) -> list[TestRecord]:
    """Entry point: parse a full Playwright JSON report dict into TestRecords."""
    records: list[TestRecord] = []
    for suite in report.get("suites", []):
        records.extend(_walk_suite(suite, ancestor_titles=[]))
    return records


def parse_report_file(path: str | Path) -> list[TestRecord]:
    """Load a JSON report from disk and parse it into TestRecords."""
    with open(path, "r", encoding="utf-8") as f:
        report = json.load(f)
    return parse_report(report)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m parser.report_parser <path-to-report.json>")
        sys.exit(1)

    parsed = parse_report_file(sys.argv[1])
    print(json.dumps([r.to_dict() for r in parsed], indent=2))
    print(f"\n--- Parsed {len(parsed)} test records ---", file=sys.stderr)
