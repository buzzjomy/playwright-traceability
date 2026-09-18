import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.push_test_inventory import _parse_args, build_payload, find_repo_root, main, normalize_file_path

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
DEMO_DIR = Path(__file__).parent.parent / "demo" / "google-search"


def _fake_response(status_code: int, json_body: dict | None = None):
    class _Response:
        def __init__(self):
            self.status_code = status_code
            self.text = "error detail"

        def json(self):
            return json_body or {}

    return _Response()


def test_parse_args_requires_at_least_one_input_source():
    with pytest.raises(SystemExit):
        _parse_args(["--backend-url", "http://localhost:8000", "--api-key", "k"])


def test_parse_args_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        _parse_args(["--backend-url", "http://localhost:8000", "--report", "report.json"])


def test_parse_args_falls_back_to_env_var_api_key(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "env-key")
    args = _parse_args(["--backend-url", "http://localhost:8000", "--report", "report.json"])
    assert args.api_key == "env-key"


def test_build_payload_only_includes_requested_sources():
    payload, unmatched = build_payload(report=None, specs_dir=str(SAMPLES_DIR / "sample-specs"), features_dir=None)
    assert set(payload.keys()) == {"static_specs"}
    assert len(payload["static_specs"]) == 6
    assert unmatched == set()


def test_build_payload_with_all_three_sources():
    payload, unmatched = build_payload(
        report=str(SAMPLES_DIR / "sample-report.json"),
        specs_dir=str(SAMPLES_DIR / "sample-specs"),
        features_dir=str(SAMPLES_DIR / "sample-features"),
    )
    assert len(payload["run_report"]) == 5
    assert len(payload["static_specs"]) == 6
    assert len(payload["features"]) == 4
    assert unmatched == set()


def test_build_payload_applies_mapping_file_additively():
    # A relative specs_dir, matching how sample-mapping.json's "file" paths
    # are written (mapping matches on the exact path string the parser
    # reports back - see parser/mapping_parser.py's docstring).
    payload, unmatched = build_payload(
        report=None,
        specs_dir="samples/sample-specs",
        features_dir=None,
        mapping_file=str(SAMPLES_DIR / "sample-mapping.json"),
    )

    by_title = {r["title"]: r for r in payload["static_specs"]}
    # Previously unlinked test gets the mapping's key.
    assert by_title["should reject invalid password"]["jira_keys"] == ["PROJ-150"]
    # Test already linked via a Trace(...) comment keeps that key AND gets the mapping's.
    assert by_title["should login with valid credentials"]["jira_keys"] == ["PROJ-101", "PROJ-999"]
    # The mapping's third entry doesn't match any real test in this fixture.
    assert unmatched == {("samples/sample-specs/auth.spec.ts", "a test that no longer exists")}


def test_find_repo_root_finds_git_directory_in_ancestor(tmp_path):
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == tmp_path


def test_find_repo_root_returns_none_without_a_git_directory(tmp_path):
    assert find_repo_root(tmp_path) is None


def test_normalize_file_path_makes_an_absolute_path_repo_relative(tmp_path):
    (tmp_path / ".git").mkdir()
    absolute = str(tmp_path / "tests" / "auth.spec.ts")

    assert normalize_file_path(absolute, tmp_path) == "tests/auth.spec.ts"


def test_normalize_file_path_resolves_relative_to_base_dir(tmp_path):
    # The report_parser scenario: "file" is relative to Playwright's own
    # rootDir, not cwd, so a base_dir is needed to resolve it correctly.
    (tmp_path / ".git").mkdir()
    base_dir = tmp_path / "demo" / "tests"

    assert normalize_file_path("auth.spec.ts", tmp_path, base_dir=base_dir) == "demo/tests/auth.spec.ts"


def test_normalize_file_path_falls_back_when_outside_repo_root(tmp_path):
    (tmp_path / ".git").mkdir()
    # Mirrors a synthetic/fake rootDir like "/repo/tests" that shares no
    # ancestry with the real repo root - can't be made relative, so the
    # original string is kept rather than raising or fabricating a path.
    assert normalize_file_path("auth.spec.ts", tmp_path, base_dir=Path("/repo/tests")) == "auth.spec.ts"


def test_normalize_file_path_returns_original_without_a_repo_root():
    assert normalize_file_path("some/path.spec.ts", repo_root=None) == "some/path.spec.ts"


def test_build_payload_normalizes_paths_so_report_and_specs_reconcile(tmp_path):
    # Regression test for a real bug: report.json (Playwright's own
    # output) reports "file" relative to ITS rootDir (e.g.
    # "homepage.spec.ts"), while static_parser invoked with a
    # repo-root-relative --specs-dir reports the fuller
    # "demo/google-search/tests/homepage.spec.ts" - different strings
    # for the same physical file, which silently broke reconciliation in
    # backend/test_inventory.py until paths were normalized here.
    #
    # demo/google-search/report.json's committed rootDir is an absolute
    # path from whichever machine last regenerated it - rewritten here to
    # this machine's real path so the test exercises normalization
    # portably (CI, another contributor's machine) instead of only
    # passing by accident of whose path happens to match the fixture.
    raw_report = json.loads((DEMO_DIR / "report.json").read_text())
    raw_report["config"]["rootDir"] = str(DEMO_DIR / "tests")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(raw_report))

    payload, _ = build_payload(
        report=str(report_path),
        specs_dir=str(DEMO_DIR / "tests"),
        features_dir=None,
    )

    run_files = {r["file"] for r in payload["run_report"]}
    static_files = {r["file"] for r in payload["static_specs"]}

    # Every run-report file now has a matching static-scan file - before
    # normalization, this intersection was empty.
    assert run_files == static_files
    assert len(run_files) > 0


def test_main_returns_zero_and_sends_correct_headers_on_success(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    with patch("scripts.push_test_inventory.requests.post") as mock_post:
        mock_post.return_value = _fake_response(200, {"run_report_count": 5})
        exit_code = main(
            [
                "--backend-url",
                "http://localhost:8000",
                "--report",
                str(SAMPLES_DIR / "sample-report.json"),
            ]
        )

    assert exit_code == 0
    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:8000/api/ingest/run"
    assert kwargs["headers"] == {"Authorization": "Bearer test-key"}
    assert len(kwargs["json"]["run_report"]) == 5


def test_main_returns_one_on_backend_failure(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    with patch("scripts.push_test_inventory.requests.post") as mock_post:
        mock_post.return_value = _fake_response(401)
        exit_code = main(
            [
                "--backend-url",
                "http://localhost:8000",
                "--report",
                str(SAMPLES_DIR / "sample-report.json"),
            ]
        )

    assert exit_code == 1
