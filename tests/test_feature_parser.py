from pathlib import Path

import pytest

from parser.feature_parser import parse_feature_directory

SAMPLE_FEATURES_DIR = Path(__file__).parent.parent / "samples" / "sample-features"


@pytest.fixture(scope="module")
def records():
    return parse_feature_directory(SAMPLE_FEATURES_DIR)


def test_total_record_count(records):
    # 2 plain scenarios + 1 outline expanded over 2 Examples rows
    assert len(records) == 4


def test_feature_title_prefixes_full_title(records):
    rec = next(r for r in records if r.title == "Login with valid credentials")
    assert rec.full_title == "Login > Login with valid credentials"


def test_feature_and_scenario_tags_are_combined(records):
    rec = next(r for r in records if r.title == "Login with valid credentials")
    assert rec.tags == ["@auth", "@smoke"]


def test_trace_comment_extracts_jira_key(records):
    rec = next(r for r in records if r.title == "Login with valid credentials")
    assert rec.jira_keys == ["PROJ-101"]


def test_scenario_without_tag_or_comment_has_no_jira_keys(records):
    rec = next(r for r in records if r.title == "Login with an invalid password")
    assert rec.tags == ["@auth"]
    assert rec.jira_keys == []


def test_scenario_outline_expands_one_record_per_examples_row(records):
    matching = [r for r in records if r.title.startswith("Login as different roles")]
    assert len(matching) == 2
    titles = {r.title for r in matching}
    assert titles == {
        "Login as different roles [role=admin]",
        "Login as different roles [role=guest]",
    }


def test_scenario_outline_combines_feature_scenario_and_examples_tags(records):
    rec = next(r for r in records if r.title == "Login as different roles [role=admin]")
    assert rec.tags == ["@auth", "@regression", "@PROJ-108"]


def test_scenario_outline_jira_key_comes_from_examples_tag(records):
    rec = next(r for r in records if r.title == "Login as different roles [role=admin]")
    assert rec.jira_keys == ["PROJ-108"]


def test_scenario_outline_rows_have_distinct_lines(records):
    matching = [r for r in records if r.title.startswith("Login as different roles")]
    lines = {r.line for r in matching}
    assert len(lines) == 2
