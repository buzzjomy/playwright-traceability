import pytest

RUN_RECORD = {
    "spec_id": "spec-1",
    "title": "should login",
    "full_title": "Login > should login",
    "file": "auth.spec.ts",
    "line": 5,
    "column": 3,
    "project": "chromium",
    "tags": ["@smoke"],
    "jira_keys": ["PROJ-101"],
    "status": "passed",
    "duration_ms": 842,
    "retry_count": 0,
    "is_flaky": False,
    "error_message": None,
}

SOURCE_RECORD = {
    "title": "should login",
    "full_title": "Login > should login",
    "file": "auth.spec.ts",
    "line": 5,
    "column": 3,
    "tags": ["@smoke"],
    "jira_keys": ["PROJ-101"],
}


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    """Configure a fixed INGEST_API_KEY for every test in this file."""
    monkeypatch.setenv("INGEST_API_KEY", "test-secret-key")
    return "test-secret-key"


def _auth_headers(key: str = "test-secret-key") -> dict:
    return {"Authorization": f"Bearer {key}"}


def test_missing_authorization_header_is_rejected(client):
    response = client.post("/api/ingest/run", json={"run_report": []})
    assert response.status_code == 401


def test_wrong_api_key_is_rejected(client):
    response = client.post("/api/ingest/run", json={"run_report": []}, headers=_auth_headers("wrong-key"))
    assert response.status_code == 401


def test_missing_server_api_key_fails_closed(client, monkeypatch):
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    response = client.post("/api/ingest/run", json={"run_report": []}, headers=_auth_headers())
    assert response.status_code == 500


def test_push_run_report_creates_a_run(client):
    response = client.post("/api/ingest/run", json={"run_report": [RUN_RECORD]}, headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["run_report_count"] == 1
    assert body["run_id"] is not None
    assert body["static_specs_count"] is None
    assert body["features_count"] is None


def test_two_pushes_create_two_separate_runs(client):
    first = client.post("/api/ingest/run", json={"run_report": [RUN_RECORD]}, headers=_auth_headers())
    second = client.post("/api/ingest/run", json={"run_report": [RUN_RECORD]}, headers=_auth_headers())
    assert first.json()["run_id"] != second.json()["run_id"]


def test_omitted_field_leaves_previous_data_untouched(client):
    client.post(
        "/api/ingest/run",
        json={"static_specs": [SOURCE_RECORD]},
        headers=_auth_headers(),
    )
    # This push doesn't mention static_specs at all - it should be left alone.
    response = client.post("/api/ingest/run", json={"run_report": [RUN_RECORD]}, headers=_auth_headers())
    assert response.json()["static_specs_count"] is None


def test_explicit_empty_list_replaces_with_zero(client):
    client.post("/api/ingest/run", json={"static_specs": [SOURCE_RECORD]}, headers=_auth_headers())
    response = client.post("/api/ingest/run", json={"static_specs": []}, headers=_auth_headers())
    assert response.json()["static_specs_count"] == 0


def test_static_and_feature_records_are_independent(client):
    client.post("/api/ingest/run", json={"static_specs": [SOURCE_RECORD]}, headers=_auth_headers())
    response = client.post(
        "/api/ingest/run",
        json={"features": [SOURCE_RECORD, SOURCE_RECORD]},
        headers=_auth_headers(),
    )
    body = response.json()
    assert body["features_count"] == 2
    assert body["static_specs_count"] is None  # untouched by this push


def test_pushing_static_specs_again_replaces_the_previous_set(client):
    two_records = {"static_specs": [SOURCE_RECORD, SOURCE_RECORD]}
    one_record = {"static_specs": [SOURCE_RECORD]}
    client.post("/api/ingest/run", json=two_records, headers=_auth_headers())
    response = client.post("/api/ingest/run", json=one_record, headers=_auth_headers())
    assert response.json()["static_specs_count"] == 1
