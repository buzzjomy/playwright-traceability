"""POST /api/ingest/playwright (issue #44): the Playwright reporter sends the
raw report and raw scan facts, and the backend interprets them with the same
parsers the Python CLI uses."""

import json
from pathlib import Path

import pytest

SAMPLE_REPORT = json.loads((Path(__file__).parent.parent / "samples" / "sample-report.json").read_text())
HEADERS = {"Authorization": "Bearer test-key"}

RAW_FACT = {
    "title": "should load",
    "ancestors": ["Homepage"],
    "file": "tests/homepage.spec.ts",
    "line": 4,
    "column": 3,
    "tag_option": ["@smoke"],
    "leading_comment_text": "// KAN-4",
    "assertions": ["expect(page).toHaveTitle(/Google/)"],
}


@pytest.fixture(autouse=True)
def ingest_key(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")


def test_a_report_becomes_a_run_of_test_records(client):
    response = client.post("/api/ingest/playwright", json={"report": SAMPLE_REPORT}, headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["run_report_count"] > 0 and body["run_id"] is not None
    assert body["static_specs_count"] is None  # not sent -> untouched
    assert len(client.get("/api/inventory").json()["entries"]) == body["run_report_count"]


def test_raw_scan_facts_are_interpreted_with_the_cli_rules(client):
    response = client.post("/api/ingest/playwright", json={"static_facts": [RAW_FACT]}, headers=HEADERS)

    assert response.json()["static_specs_count"] == 1
    assert response.json()["run_report_count"] is None
    entry = client.get("/api/inventory").json()["entries"][0]
    # The Jira key came from the leading comment, the full title from the ancestry.
    assert entry["jira_keys"] == ["KAN-4"]
    assert entry["full_title"] == "Homepage > should load"
    assert entry["tags"] == ["@smoke"] and entry["assertions"] == ["expect(page).toHaveTitle(/Google/)"]


def test_a_report_and_a_scan_together_reconcile_by_file_and_title(client):
    report = {
        "suites": [
            {
                "title": "homepage.spec.ts",
                "specs": [
                    {
                        "id": "s1", "title": "should load", "file": "tests/homepage.spec.ts", "line": 4, "column": 3,
                        "tags": ["@smoke"],
                        "tests": [{"projectName": "chromium", "status": "expected", "annotations": [],
                                   "results": [{"status": "passed", "duration": 12, "errors": []}]}],
                    }
                ],
            }
        ]
    }
    client.post("/api/ingest/playwright", json={"report": report, "static_facts": [RAW_FACT]}, headers=HEADERS)

    entries = client.get("/api/inventory").json()["entries"]
    assert len(entries) == 1  # one reconciled row, not a run-only plus a source-only
    assert entries[0]["in_source"] and entries[0]["has_run"] and entries[0]["status"] == "passed"


def test_a_scan_replaces_the_previous_snapshot_but_not_the_run_history(client):
    client.post("/api/ingest/playwright", json={"report": SAMPLE_REPORT, "static_facts": [RAW_FACT]}, headers=HEADERS)
    client.post("/api/ingest/playwright", json={"static_facts": []}, headers=HEADERS)  # a scan that found nothing
    entries = client.get("/api/inventory").json()["entries"]
    assert entries and not any(e["in_source"] for e in entries)  # snapshot cleared, runs kept


@pytest.mark.parametrize("report", [{}, {"suites": "nope"}, {"config": {}}])
def test_something_that_is_not_a_json_report_is_a_422(client, report):
    response = client.post("/api/ingest/playwright", json={"report": report}, headers=HEADERS)
    assert response.status_code == 422


def test_malformed_scan_facts_are_a_422(client):
    response = client.post("/api/ingest/playwright", json={"static_facts": [{"title": "no file or ancestors"}]}, headers=HEADERS)
    assert response.status_code == 422


def test_it_needs_a_valid_ingest_key(client):
    assert client.post("/api/ingest/playwright", json={"report": SAMPLE_REPORT}).status_code == 401
    assert client.post("/api/ingest/playwright", json={"report": SAMPLE_REPORT}, headers={"Authorization": "Bearer nope"}).status_code == 401
