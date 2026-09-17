"""JSON mapping-file linking - the alternative to Trace(Jira:...) comment
annotations, for teams that won't touch test code (Milestone 2, issue #9).

Maps (file, title) pairs to Jira keys via a standalone JSON file, since a
team may not want to add inline comments to their test source at all. This
merges into the jira_keys already produced by report_parser/static_parser/
feature_parser (from tags/annotations/title, or leading comments) rather
than replacing them - a test can be linked more than one way at once.

Mapping file format:
    [
      {"file": "auth.spec.ts", "title": "should login", "jira_keys": ["PROJ-101"]},
      ...
    ]

A record is matched by exact (file, title) - file paths must match how the
parser that produced the record reports them (e.g. relative to wherever it
was invoked from). This is a known sharp edge, same class of issue as the
TestRecord/StaticTestRecord reconciliation noted elsewhere in this repo.

Usage:
    python -m parser.mapping_parser mapping.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Protocol


class _HasFileTitleJiraKeys(Protocol):
    file: str
    title: str
    jira_keys: list[str]


def load_mapping_file(path: str | Path) -> dict[tuple[str, str], list[str]]:
    """Load a JSON mapping file into a {(file, title): jira_keys} lookup."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    mapping: dict[tuple[str, str], list[str]] = {}
    for entry in raw:
        mapping[(entry["file"], entry["title"])] = entry.get("jira_keys", [])
    return mapping


def apply_mapping(records: list[_HasFileTitleJiraKeys], mapping: dict[tuple[str, str], list[str]]) -> set:
    """Merge mapping-file jira_keys into a list of records' jira_keys, in place.

    Matches by (record.file, record.title). Existing jira_keys (from tags,
    annotations, or Trace(...) comments) are kept and extended, not
    replaced or deduplicated away, since a test can be linked more than one
    way at once. Returns the set of mapping (file, title) keys that matched
    at least one record, so a caller can warn about unmatched entries
    (likely a typo or a renamed/removed test).
    """
    matched_keys = set()
    for record in records:
        lookup_key = (record.file, record.title)
        mapped_jira_keys = mapping.get(lookup_key)
        if not mapped_jira_keys:
            continue
        matched_keys.add(lookup_key)
        for jira_key in mapped_jira_keys:
            if jira_key not in record.jira_keys:
                record.jira_keys.append(jira_key)
    return matched_keys


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m parser.mapping_parser <mapping.json>")
        sys.exit(1)

    loaded = load_mapping_file(sys.argv[1])
    print(json.dumps({f"{file}::{title}": keys for (file, title), keys in loaded.items()}, indent=2))
    print(f"\n--- Loaded {len(loaded)} mapping entries ---", file=sys.stderr)
