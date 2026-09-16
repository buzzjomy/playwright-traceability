"""Regression tests for issue #4: every parser must degrade gracefully -
returning an empty list, never raising - when a team has no tests yet.

report_parser is the one exception: it requires an actual report *file* to
exist (a missing run report is a distinct, real usage error, not "zero
tests" - see README's design notes), so its zero-test coverage is at the
report-content level instead of a missing-file level.
"""

from parser.feature_parser import parse_feature_directory
from parser.report_parser import parse_report
from parser.static_parser import parse_spec_directory


def test_report_parser_handles_completely_empty_report():
    assert parse_report({}) == []


def test_report_parser_handles_report_with_no_suites():
    assert parse_report({"suites": [], "errors": [], "stats": {}}) == []


def test_static_parser_handles_empty_directory(tmp_path):
    assert parse_spec_directory(tmp_path) == []


def test_static_parser_handles_nonexistent_directory(tmp_path):
    assert parse_spec_directory(tmp_path / "does-not-exist") == []


def test_feature_parser_handles_empty_directory(tmp_path):
    assert parse_feature_directory(tmp_path) == []


def test_feature_parser_handles_nonexistent_directory(tmp_path):
    assert parse_feature_directory(tmp_path / "does-not-exist") == []


def test_static_parser_ignores_directory_with_only_non_spec_files(tmp_path):
    (tmp_path / "README.md").write_text("not a spec file")
    (tmp_path / "helpers.ts").write_text("export const noop = () => {};")
    assert parse_spec_directory(tmp_path) == []


def test_feature_parser_ignores_directory_with_only_non_feature_files(tmp_path):
    (tmp_path / "README.md").write_text("not a feature file")
    assert parse_feature_directory(tmp_path) == []
