from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.push_test_inventory import _parse_args, build_payload, main

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


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
    payload = build_payload(report=None, specs_dir=str(SAMPLES_DIR / "sample-specs"), features_dir=None)
    assert set(payload.keys()) == {"static_specs"}
    assert len(payload["static_specs"]) == 6


def test_build_payload_with_all_three_sources():
    payload = build_payload(
        report=str(SAMPLES_DIR / "sample-report.json"),
        specs_dir=str(SAMPLES_DIR / "sample-specs"),
        features_dir=str(SAMPLES_DIR / "sample-features"),
    )
    assert len(payload["run_report"]) == 5
    assert len(payload["static_specs"]) == 6
    assert len(payload["features"]) == 4


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
