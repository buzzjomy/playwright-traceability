"""CLI to push Playwright test inventory data to the backend service.

Runs whichever of the three Milestone 1 parsers are asked for (JSON run
report, static .spec.ts AST scan, .feature Gherkin scan) and POSTs the
combined result to POST /api/ingest/run. Meant for a CI step (e.g. a
GitHub Action) right after `npx playwright test --reporter=json`, but
works the same run locally.

Usage:
    python -m scripts.push_test_inventory \
        --backend-url https://your-backend.example.com \
        --report report.json \
        --specs-dir tests/ \
        --features-dir features/ \
        --mapping-file jira-mapping.json

The API key can be passed via --api-key or (preferred, so it never shows
up in shell history or CI logs) the INGEST_API_KEY environment variable.

Any of --report/--specs-dir/--features-dir may be omitted - only the
requested parsers run, and only their corresponding backend data is
touched (an omitted one is left as-is, not wiped - see
backend/schemas.py's IngestRunRequest for why).

--mapping-file (issue #9) merges Jira keys from a JSON mapping file into
whichever record types were actually requested - see
parser/mapping_parser.py for the file format and (file, title) matching
rules. This is additive to whatever jira_keys the parsers already found
from tags/annotations/Trace(...) comments, not a replacement.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

from parser.feature_parser import parse_feature_directory
from parser.mapping_parser import apply_mapping, load_mapping_file
from parser.report_parser import parse_report_file
from parser.static_parser import parse_spec_directory


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    arg_parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    arg_parser.add_argument("--backend-url", required=True, help="Base URL of the backend service, e.g. https://host")
    arg_parser.add_argument("--api-key", default=None, help="Falls back to the INGEST_API_KEY env var if omitted")
    arg_parser.add_argument("--report", default=None, help="Path to a Playwright JSON reporter output file")
    arg_parser.add_argument("--specs-dir", default=None, help="Directory to scan for .spec.ts files")
    arg_parser.add_argument("--features-dir", default=None, help="Directory to scan for .feature files")
    arg_parser.add_argument(
        "--mapping-file", default=None, help="JSON file linking (file, title) pairs to Jira keys - see parser/mapping_parser.py"
    )

    args = arg_parser.parse_args(argv)

    if not any([args.report, args.specs_dir, args.features_dir]):
        arg_parser.error("at least one of --report, --specs-dir, --features-dir is required")

    args.api_key = args.api_key or os.environ.get("INGEST_API_KEY")
    if not args.api_key:
        arg_parser.error("--api-key or the INGEST_API_KEY environment variable is required")

    return args


def build_payload(
    report: str | None,
    specs_dir: str | None,
    features_dir: str | None,
    mapping_file: str | None = None,
) -> tuple[dict, set]:
    """Run the requested parsers and build the /api/ingest/run request body.

    A key is only present in the returned dict if the corresponding
    argument was given - matches IngestRunRequest's None-vs-[] semantics
    on the backend (omitted means "don't touch that data").

    If mapping_file is given, its Jira keys are merged into every produced
    record's jira_keys (additive - see parser/mapping_parser.py). Returns
    (payload, unmatched_mapping_keys) so callers can warn about mapping
    entries that never matched any parsed test (a likely typo or a
    renamed/removed test).
    """
    record_lists: dict[str, list] = {}

    if report is not None:
        record_lists["run_report"] = parse_report_file(report)

    if specs_dir is not None:
        record_lists["static_specs"] = parse_spec_directory(specs_dir)

    if features_dir is not None:
        record_lists["features"] = parse_feature_directory(features_dir)

    unmatched: set = set()
    if mapping_file is not None:
        mapping = load_mapping_file(mapping_file)
        matched: set = set()
        for records in record_lists.values():
            matched |= apply_mapping(records, mapping)
        unmatched = set(mapping) - matched

    payload = {key: [r.to_dict() for r in records] for key, records in record_lists.items()}
    return payload, unmatched


def push(backend_url: str, api_key: str, payload: dict) -> requests.Response:
    """POST the payload to the backend's ingest endpoint."""
    return requests.post(
        f"{backend_url.rstrip('/')}/api/ingest/run",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args, run the requested parsers, push, report the result."""
    args = _parse_args(argv)
    payload, unmatched_mapping_keys = build_payload(
        args.report, args.specs_dir, args.features_dir, args.mapping_file
    )

    if unmatched_mapping_keys:
        for file, title in sorted(unmatched_mapping_keys):
            print(f"Warning: mapping entry for {file!r} / {title!r} matched no test", file=sys.stderr)

    counts = ", ".join(f"{key}={len(records)}" for key, records in payload.items())
    print(f"Pushing to {args.backend_url}: {counts}")

    response = push(args.backend_url, args.api_key, payload)
    if response.status_code != 200:
        print(f"Push failed: {response.status_code} {response.text}", file=sys.stderr)
        return 1

    print(f"Push succeeded: {response.json()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
