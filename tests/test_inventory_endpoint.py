def test_inventory_is_empty_with_no_data(client):
    response = client.get("/api/inventory")
    assert response.status_code == 200
    assert response.json() == {"entries": []}


def test_inventory_reflects_ingested_data(client, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")

    client.post(
        "/api/ingest/run",
        json={
            "run_report": [
                {
                    "spec_id": "spec-1",
                    "title": "should login",
                    "full_title": "Auth > should login",
                    "file": "auth.spec.ts",
                    "line": 1,
                    "column": 1,
                    "project": "chromium",
                    "tags": [],
                    "jira_keys": [],
                    "status": "passed",
                    "duration_ms": 100,
                    "retry_count": 0,
                    "is_flaky": False,
                    "error_message": None,
                }
            ],
            "static_specs": [
                {
                    "title": "should login",
                    "full_title": "Auth > should login",
                    "file": "auth.spec.ts",
                    "line": 1,
                    "column": 1,
                    "tags": ["@smoke"],
                    "jira_keys": ["PROJ-101"],
                }
            ],
        },
        headers={"Authorization": "Bearer test-key"},
    )

    response = client.get("/api/inventory")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["status"] == "passed"
    assert entries[0]["jira_keys"] == ["PROJ-101"]
    assert entries[0]["in_source"] is True
    assert entries[0]["has_run"] is True
