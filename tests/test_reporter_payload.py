"""The Node reporter and the Python backend must agree (issue #44).

`reporter/test/sample-payload.json` is a REAL upload captured from the
reporter running real Playwright (regenerate with `UPDATE_FIXTURE=1 npm test`
in reporter/). Feeding it through the backend proves the two halves - written
in different languages - fit together.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SAMPLE = json.loads((ROOT / "reporter" / "test" / "sample-payload.json").read_text())


@pytest.fixture()
def entries(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "k")
    response = client.post("/api/ingest/playwright", json=SAMPLE, headers={"Authorization": "Bearer k"})
    assert response.status_code == 200, response.text
    return {(e["title"], e["project"]): e for e in client.get("/api/inventory").json()["entries"]}


def test_every_test_from_every_project_arrives(entries):
    titles = {t for t, _ in entries}
    assert titles == {"passes everywhere", "fails always", "is skipped", "flaky until retried", "has a Jira annotation"}
    assert {p for _, p in entries} >= {"alpha", "beta"}


def test_outcomes_map_onto_the_inventory_statuses(entries):
    assert entries[("passes everywhere", "alpha")]["status"] == "passed"
    assert entries[("fails always", "alpha")]["status"] == "failed"
    assert entries[("is skipped", "alpha")]["status"] == "skipped"
    flaky = entries[("flaky until retried", "alpha")]
    assert flaky["is_flaky"] is True and flaky["status"] == "passed"


def test_jira_keys_come_from_comments_and_annotations(entries):
    assert entries[("passes everywhere", "alpha")]["jira_keys"] == ["KAN-4"]  # // KAN-4 above the test
    assert entries[("has a Jira annotation", "alpha")]["jira_keys"] == ["SHOP-7"]  # annotation


def test_a_tag_is_kept(entries):
    assert entries[("fails always", "alpha")]["tags"] == ["@broken"]


def test_the_run_and_the_scan_reconcile_into_single_rows(entries):
    # The reporter's run paths and the scanner's source paths are the same string,
    # so a test is one row that is both "in source" and "has run" - never two.
    row = entries[("passes everywhere", "alpha")]
    assert row["in_source"] is True and row["has_run"] is True


def test_the_scan_adds_assertions_the_run_cannot_know(entries):
    assert any("toBe" in a for a in entries[("passes everywhere", "alpha")]["assertions"])


def test_the_reporters_scanner_script_is_identical_to_the_one_the_python_cli_uses():
    # The package ships its own copy so it is self-contained; this stops them drifting.
    assert (ROOT / "reporter" / "src" / "parse_specs.js").read_text() == (ROOT / "static_parser" / "parse_specs.js").read_text()
