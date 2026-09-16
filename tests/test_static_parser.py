from pathlib import Path

import pytest

from parser.static_parser import parse_spec_directory

SAMPLE_SPECS_DIR = Path(__file__).parent.parent / "samples" / "sample-specs"


@pytest.fixture(scope="module")
def records():
    return parse_spec_directory(SAMPLE_SPECS_DIR)


def test_total_record_count(records):
    # auth.spec.ts: 4 statically-titled tests (2 dynamic-title loop tests excluded)
    # checkout.spec.ts: 2 statically-titled tests
    assert len(records) == 6


def test_nested_describe_titles_are_flattened(records):
    rec = next(r for r in records if r.title == "should login with valid credentials")
    assert rec.full_title == "Login flow > should login with valid credentials"


def test_dynamically_titled_tests_are_excluded(records):
    titles = [r.title for r in records]
    assert not any("dashboard after login" in t for t in titles)


def test_skipped_test_is_still_captured(records):
    rec = next(r for r in records if r.title == "should lock account after 5 failed attempts")
    assert rec.full_title == "Login flow > should lock account after 5 failed attempts"


def test_describe_skip_block_is_still_captured(records):
    rec = next(r for r in records if r.title == "should support the old single-page checkout flow")
    assert rec.full_title == "Legacy checkout (deprecated) > should support the old single-page checkout flow"


def test_trace_comment_extracts_jira_key_not_in_any_playwright_annotation(records):
    rec = next(r for r in records if r.title == "should lock account after 5 failed attempts")
    assert rec.jira_keys == ["PROJ-109"]


def test_tag_option_string_is_captured(records):
    rec = next(r for r in records if r.title == "should login with valid credentials")
    assert rec.tags == ["@smoke"]
    assert rec.jira_keys == ["PROJ-101"]


def test_test_without_tag_or_comment_has_no_tags_or_jira_keys(records):
    rec = next(r for r in records if r.title == "should reject invalid password")
    assert rec.tags == []
    assert rec.jira_keys == []


def test_top_level_test_outside_any_describe_has_empty_full_title_prefix(records):
    rec = next(r for r in records if r.title == "should apply discount code at checkout")
    assert rec.full_title == "should apply discount code at checkout"
