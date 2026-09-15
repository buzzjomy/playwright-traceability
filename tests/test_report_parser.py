from pathlib import Path

import pytest

from parser.report_parser import extract_jira_keys, parse_report_file

SAMPLE_REPORT = Path(__file__).parent.parent / "samples" / "sample-report.json"


@pytest.fixture(scope="module")
def records():
    return parse_report_file(SAMPLE_REPORT)


def test_total_record_count(records):
    # spec-1: 1 project, spec-2: 1 project, spec-3: 2 projects, spec-4: 1 project
    assert len(records) == 5


def test_nested_describe_titles_are_flattened(records):
    rec = next(r for r in records if r.spec_id == "spec-1")
    assert rec.full_title == "auth.spec.ts > Login flow > should login with valid credentials"


def test_simple_pass(records):
    rec = next(r for r in records if r.spec_id == "spec-1")
    assert rec.status == "passed"
    assert rec.retry_count == 0
    assert rec.is_flaky is False
    assert rec.jira_keys == ["PROJ-101"]


def test_flaky_test_detected(records):
    rec = next(r for r in records if r.spec_id == "spec-2")
    assert rec.status == "passed"       # final attempt passed
    assert rec.retry_count == 1
    assert rec.is_flaky is True         # but it failed before passing


def test_multi_project_spec_produces_separate_records(records):
    matching = [r for r in records if r.spec_id == "spec-3"]
    assert len(matching) == 2
    projects = {r.project for r in matching}
    assert projects == {"chromium", "firefox"}

    chromium_rec = next(r for r in matching if r.project == "chromium")
    firefox_rec = next(r for r in matching if r.project == "firefox")
    assert chromium_rec.status == "failed"
    assert chromium_rec.retry_count == 1
    assert firefox_rec.status == "passed"


def test_untagged_test_has_no_jira_keys(records):
    rec = next(r for r in records if r.spec_id == "spec-4")
    assert rec.jira_keys == []
    assert rec.tags == []


def test_tags_are_preserved(records):
    rec = next(r for r in records if r.spec_id == "spec-1")
    assert rec.tags == ["@smoke"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("@PROJ-13", ["PROJ-13"]),
        ("Jira:PROJ-13", ["PROJ-13"]),
        ("PROJ-13", ["PROJ-13"]),
        ("covers PROJ-13 and PROJ-14", ["PROJ-13", "PROJ-14"]),
        ("no key here", []),
        ("", []),
    ],
)
def test_extract_jira_keys(text, expected):
    assert extract_jira_keys(text) == expected


def test_extract_jira_keys_dedupes_across_multiple_texts():
    assert extract_jira_keys("PROJ-13", "@PROJ-13", "Jira:PROJ-13") == ["PROJ-13"]
