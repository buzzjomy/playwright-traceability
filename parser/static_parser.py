"""Static AST parser for Playwright .spec.ts source files.

Complements report_parser.py: a JSON run report only knows about tests that
actually executed in that run. This module statically walks .spec.ts files
(via a small Node/TypeScript-compiler-API script, static_parser/parse_specs.js)
to also catch:
  - tests that never ran (skipped, filtered out by grep, or just not part
    of the run that produced the JSON report)
  - Trace(Jira:PROJ-13)-style comment annotations, which aren't registered
    via test.info().annotations() and so never appear in a JSON report

The Node script only extracts raw AST facts (title, location, tag option,
leading comment text); Jira-key extraction reuses report_parser's regex so
that logic isn't duplicated across two languages.

Usage:
    python -m parser.static_parser tests/
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from parser.models import StaticTestRecord
from parser.report_parser import extract_jira_keys

_STATIC_PARSER_DIR = Path(__file__).parent.parent / "static_parser"
_NODE_SCRIPT = _STATIC_PARSER_DIR / "parse_specs.js"


def find_spec_files(root: str | Path) -> list[Path]:
    """Recursively find every *.spec.ts file under root, sorted for stable output."""
    return sorted(Path(root).rglob("*.spec.ts"))


def _run_node_parser(files: list[Path]) -> list[dict]:
    """Invoke parse_specs.js on the given files and return its raw JSON records.

    Each file is passed as a (resolved absolute path, original path) pair so
    the Node script can read from disk while still emitting the caller's
    original (typically repo-relative) path in the "file" field.
    """
    if not files:
        return []
    path_pairs: list[str] = []
    for f in files:
        path_pairs.extend([str(f.resolve()), str(f)])
    result = subprocess.run(
        ["node", str(_NODE_SCRIPT), *path_pairs],
        cwd=_STATIC_PARSER_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def parse_spec_files(files: list[str | Path]) -> list[StaticTestRecord]:
    """Statically parse the given .spec.ts files into StaticTestRecords."""
    raw_records = _run_node_parser([Path(f) for f in files])

    records: list[StaticTestRecord] = []
    for raw in raw_records:
        title = raw["title"]
        ancestors = raw["ancestors"]
        full_title = " > ".join(ancestors + [title]) if ancestors else title

        tag_option = raw.get("tag_option") or []
        leading_comment = raw.get("leading_comment_text") or ""
        jira_keys = extract_jira_keys(*tag_option, leading_comment, title)

        records.append(
            StaticTestRecord(
                title=title,
                full_title=full_title,
                file=raw["file"],
                line=raw["line"],
                column=raw["column"],
                tags=tag_option,
                jira_keys=jira_keys,
                assertions=raw.get("assertions") or [],
            )
        )
    return records


def parse_spec_directory(root: str | Path) -> list[StaticTestRecord]:
    """Find every .spec.ts file under root and statically parse all of them."""
    return parse_spec_files(find_spec_files(root))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m parser.static_parser <path-to-tests-dir>")
        sys.exit(1)

    parsed = parse_spec_directory(sys.argv[1])
    print(json.dumps([r.to_dict() for r in parsed], indent=2))
    print(f"\n--- Statically parsed {len(parsed)} test records ---", file=sys.stderr)
