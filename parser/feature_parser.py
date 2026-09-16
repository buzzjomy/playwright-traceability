"""Static parser for Gherkin .feature files (BDD/Cucumber teams, e.g. playwright-bdd).

Complements report_parser.py and static_parser.py: BDD teams keep the
human-readable test intent in .feature files, with the actual Playwright
code living in separate step definitions that neither report_parser's JSON
run report nor static_parser's .spec.ts AST walk ever see. This module
reads .feature files directly using gherkin-official (Cucumber's own
Gherkin parser, implemented in pure Python — no subprocess needed here,
unlike static_parser.py) to extract scenario titles, tags, and
Trace(Jira:PROJ-13)-style comments.

A Scenario Outline + Examples table is expanded into one record per example
row, with <placeholder> values substituted into the scenario name — unlike
a .spec.ts loop, Examples table values are written directly in source, so
(unlike report_parser's take on data-driven tests) every row is fully
knowable statically.

Rule blocks are not yet supported (a Gherkin 6+ feature, rare in practice);
their scenarios are simply skipped. Jira-key extraction reuses
report_parser's regex so that logic isn't duplicated per parser.

Usage:
    python -m parser.feature_parser features/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from gherkin.parser import Parser as GherkinParser

from parser.models import FeatureTestRecord
from parser.report_parser import extract_jira_keys


def find_feature_files(root: str | Path) -> list[Path]:
    """Recursively find every *.feature file under root, sorted for stable output."""
    return sorted(Path(root).rglob("*.feature"))


def _resolve_outline_title(name: str, values: dict[str, str]) -> str:
    """Build a unique, fully-static title for one Examples row.

    Substitutes every <key> in the scenario name with its row value,
    mirroring how Cucumber substitutes Examples values into step text. Many
    outlines only reference placeholders in their steps, not the scenario
    name itself, so the row's values are also appended — otherwise every
    row of an Examples table would share one identical, ambiguous title.
    """
    substituted = name
    for key, value in values.items():
        substituted = substituted.replace(f"<{key}>", value)
    row_suffix = ", ".join(f"{key}={value}" for key, value in values.items())
    return f"{substituted} [{row_suffix}]" if row_suffix else substituted


def _leading_comment_text(top_line: int, comments_by_line: dict[int, str]) -> str:
    """Concatenate the contiguous block of comment lines directly above top_line."""
    lines: list[str] = []
    line = top_line - 1
    while line in comments_by_line:
        lines.append(comments_by_line[line])
        line -= 1
    return "\n".join(reversed(lines))


def _dedupe(items: list[str]) -> list[str]:
    """Remove duplicates from items while preserving first-seen order."""
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _handle_scenario(
    scenario: dict,
    feature_name: str,
    feature_tags: list[str],
    comments_by_line: dict[int, str],
    file_path: str,
) -> list[FeatureTestRecord]:
    """Turn one Scenario (or Scenario Outline) AST node into its record(s).

    A plain Scenario produces exactly one record. A Scenario Outline
    produces one record per row of each of its Examples tables, with tags
    combined from the feature, the scenario, and that Examples block.
    """
    name = scenario.get("name", "")
    scenario_tags = [t["name"] for t in scenario.get("tags", [])]
    keyword_line = scenario["location"]["line"]
    tag_lines = [t["location"]["line"] for t in scenario.get("tags", [])]
    top_line = min(tag_lines + [keyword_line]) if tag_lines else keyword_line
    leading_comment = _leading_comment_text(top_line, comments_by_line)

    examples_list = scenario.get("examples") or []
    if not examples_list:
        full_title = f"{feature_name} > {name}" if feature_name else name
        tags = _dedupe(feature_tags + scenario_tags)
        jira_keys = extract_jira_keys(*tags, leading_comment, name)
        return [
            FeatureTestRecord(
                title=name,
                full_title=full_title,
                file=file_path,
                line=keyword_line,
                column=scenario["location"]["column"],
                tags=tags,
                jira_keys=jira_keys,
            )
        ]

    records: list[FeatureTestRecord] = []
    for examples in examples_list:
        examples_tags = [t["name"] for t in examples.get("tags", [])]
        header_cells = [c["value"] for c in examples.get("tableHeader", {}).get("cells", [])]
        for row in examples.get("tableBody", []):
            row_values = [c["value"] for c in row.get("cells", [])]
            row_map = dict(zip(header_cells, row_values))
            resolved_name = _resolve_outline_title(name, row_map)
            full_title = f"{feature_name} > {resolved_name}" if feature_name else resolved_name
            tags = _dedupe(feature_tags + scenario_tags + examples_tags)
            jira_keys = extract_jira_keys(*tags, leading_comment, resolved_name)
            records.append(
                FeatureTestRecord(
                    title=resolved_name,
                    full_title=full_title,
                    file=file_path,
                    line=row["location"]["line"],
                    column=row["location"]["column"],
                    tags=tags,
                    jira_keys=jira_keys,
                )
            )
    return records


def parse_feature_text(text: str, file_path: str) -> list[FeatureTestRecord]:
    """Parse the text of one .feature file into FeatureTestRecords."""
    document = GherkinParser().parse(text)
    feature = document.get("feature")
    if not feature:
        return []

    comments_by_line = {c["location"]["line"]: c["text"].strip() for c in document.get("comments", [])}
    feature_name = feature.get("name", "")
    feature_tags = [t["name"] for t in feature.get("tags", [])]

    records: list[FeatureTestRecord] = []
    for child in feature.get("children", []):
        if "scenario" in child:
            records.extend(
                _handle_scenario(child["scenario"], feature_name, feature_tags, comments_by_line, file_path)
            )
        # Background steps don't produce their own record; Rule blocks
        # aren't supported yet (see module docstring).
    return records


def parse_feature_file(path: str | Path) -> list[FeatureTestRecord]:
    """Read and parse one .feature file from disk into FeatureTestRecords."""
    path = Path(path)
    return parse_feature_text(path.read_text(encoding="utf-8"), str(path))


def parse_feature_files(files: list[str | Path]) -> list[FeatureTestRecord]:
    """Parse the given .feature files into FeatureTestRecords."""
    records: list[FeatureTestRecord] = []
    for f in files:
        records.extend(parse_feature_file(f))
    return records


def parse_feature_directory(root: str | Path) -> list[FeatureTestRecord]:
    """Find every .feature file under root and parse all of them."""
    return parse_feature_files(find_feature_files(root))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m parser.feature_parser <path-to-features-dir>")
        sys.exit(1)

    parsed = parse_feature_directory(sys.argv[1])
    print(json.dumps([r.to_dict() for r in parsed], indent=2))
    print(f"\n--- Parsed {len(parsed)} feature test records ---", file=sys.stderr)
