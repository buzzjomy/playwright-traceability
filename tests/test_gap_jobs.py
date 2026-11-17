"""Gap analysis as a background job (issue #50): start returns at once, the
result is polled, it is kept per tenant, and nothing hangs or leaks."""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.models import utcnow

HEADERS = {"Authorization": "Bearer test-key"}
PARAMS = {"project_key": "KAN", "jira_key": "KAN-5"}


def _response(status_code, body=None):
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(body or {}).encode()
    return response


def _issue(key, criteria):
    description = {
        "type": "doc",
        "content": [
            {"type": "heading", "content": [{"type": "text", "text": "Acceptance Criteria"}]},
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": c}]}]} for c in criteria]},
        ],
    }
    return {"key": key, "fields": {"summary": "S", "description": description}}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")


@pytest.fixture()
def connected(client):
    with patch("backend.jira_client.requests.get", return_value=_response(200, {"accountId": "a"})):
        client.post("/api/jira/connection", json={"site_url": "https://x.atlassian.net", "email": "e@x.y", "api_token": "t"})


def _push_test(client, keys=("KAN-5",)):
    client.post("/api/ingest/run", json={"static_specs": [{
        "title": "shows results", "full_title": "shows results", "file": "s.spec.ts", "line": 1, "column": 1,
        "tags": [], "jira_keys": list(keys), "assertions": ["expect(results).toBeVisible()"]}]}, headers=HEADERS)


def _llm(results):
    mock = MagicMock()
    mock.messages.create.return_value = MagicMock(content=[MagicMock(type="text", text=json.dumps(results))])
    return mock


def _start(client, **overrides):
    return client.post("/api/coverage/gap-analysis/start", params={**PARAMS, **overrides})


def _result(client, jira_key="KAN-5"):
    return client.get("/api/coverage/gap-analysis/result", params={"jira_key": jira_key}).json()


def test_nothing_has_run_yet(client):
    assert _result(client) == {
        "jira_key": "KAN-5", "status": "none", "criteria": None, "uncovered_count": None,
        "error": None, "started_at": None, "finished_at": None,
    }


def test_start_answers_202_pending_and_the_result_arrives_done(client, connected):
    _push_test(client)
    with patch("backend.jira_client.requests.get", return_value=_response(200, _issue("KAN-5", ["Shows results", "Filters"]))), patch(
        "backend.semantic_gap.anthropic.Anthropic",
        return_value=_llm([{"covered": True, "reasoning": "asserted"}, {"covered": False, "reasoning": "no evidence"}]),
    ):
        started = _start(client)
        result = _result(client)

    assert started.status_code == 202 and started.json()["status"] == "pending"
    assert result["status"] == "done"
    assert [c["covered"] for c in result["criteria"]] == [True, False]
    assert result["uncovered_count"] == 1 and result["finished_at"] is not None


def test_no_linked_tests_needs_no_llm(client, connected):
    with patch("backend.jira_client.requests.get", return_value=_response(200, _issue("KAN-5", ["A criterion"]))), patch(
        "backend.semantic_gap.anthropic.Anthropic"
    ) as llm:
        _start(client)
        result = _result(client)
    llm.assert_not_called()
    assert result["status"] == "done" and result["uncovered_count"] == 1


@pytest.mark.parametrize(
    "setup, expected",
    [
        ("llm_down", "Claude API call failed"),
        ("no_key", "ANTHROPIC_API_KEY is not configured"),
        ("missing_issue", "does not resolve in Jira"),
    ],
)
def test_failures_become_a_failed_result_with_a_readable_message(client, connected, monkeypatch, setup, expected):
    _push_test(client)
    issue_status = 404 if setup == "missing_issue" else 200
    if setup == "no_key":
        monkeypatch.delenv("ANTHROPIC_API_KEY")
    llm = MagicMock()
    if setup == "llm_down":
        import anthropic

        llm.messages.create.side_effect = anthropic.APIError("boom", request=MagicMock(), body=None)

    with patch("backend.jira_client.requests.get", return_value=_response(issue_status, _issue("KAN-5", ["A"]))), patch(
        "backend.semantic_gap.anthropic.Anthropic", return_value=llm
    ):
        started = _start(client)
        result = _result(client)

    assert started.status_code == 202  # accepted regardless; the outcome is in the result
    assert result["status"] == "failed" and expected in result["error"]
    assert result["criteria"] is None


def test_an_unexpected_error_is_failed_not_a_crash_and_not_a_leak(client, connected):
    _push_test(client)
    with patch("backend.jira_client.requests.get", side_effect=RuntimeError("secret internal detail")):
        _start(client)
        result = _result(client)
    assert result["status"] == "failed"
    assert "RuntimeError" in result["error"] and "secret internal detail" not in result["error"]


def test_a_second_start_while_pending_does_not_call_the_llm_twice(client, connected):
    from backend.db import get_db
    from backend.main import app
    from backend.models import GapAnalysis
    from backend.tenancy import get_local_tenant

    # Simulate a run in flight: a fresh pending row.
    db = next(app.dependency_overrides[get_db]())
    tenant = get_local_tenant(db)
    db.add(GapAnalysis(tenant_id=tenant.id, project_key="KAN", jira_key="KAN-5", status="pending", started_at=utcnow()))
    db.commit()
    db.close()

    with patch("backend.jira_client.requests.get") as jira, patch("backend.semantic_gap.anthropic.Anthropic") as llm:
        again = _start(client)
    assert again.status_code == 202 and again.json()["status"] == "pending"
    jira.assert_not_called()
    llm.assert_not_called()


def test_a_pending_run_that_never_finished_is_reported_failed(client, connected):
    from backend.db import get_db
    from backend.main import app
    from backend.models import GapAnalysis
    from backend.tenancy import get_local_tenant

    db = next(app.dependency_overrides[get_db]())
    tenant = get_local_tenant(db)
    db.add(GapAnalysis(tenant_id=tenant.id, project_key="KAN", jira_key="KAN-5", status="pending", started_at=utcnow() - timedelta(minutes=10)))
    db.commit()
    db.close()

    result = _result(client)
    assert result["status"] == "failed" and "interrupted" in result["error"]
    assert _result(client)["status"] == "failed"  # and it stays recorded


def test_a_key_from_another_project_is_a_400(client, connected):
    assert _start(client, jira_key="OTHER-1").status_code == 400


def test_without_jira_access_start_is_a_400_and_queues_nothing(client):
    assert _start(client).status_code == 400
    assert _result(client)["status"] == "none"


def test_running_again_replaces_the_previous_result(client, connected):
    _push_test(client)
    with patch("backend.jira_client.requests.get", return_value=_response(200, _issue("KAN-5", ["One"]))), patch(
        "backend.semantic_gap.anthropic.Anthropic", return_value=_llm([{"covered": True, "reasoning": "first"}])
    ):
        _start(client)
    with patch("backend.jira_client.requests.get", return_value=_response(200, _issue("KAN-5", ["One"]))), patch(
        "backend.semantic_gap.anthropic.Anthropic", return_value=_llm([{"covered": False, "reasoning": "second"}])
    ):
        _start(client)
    result = _result(client)
    assert result["criteria"][0]["reasoning"] == "second"


# -- tenant isolation ------------------------------------------------------------


@pytest.fixture()
def forge(monkeypatch):
    monkeypatch.setenv("REQUIRE_FORGE_AUTH", "true")
    monkeypatch.setenv("FORGE_APP_ID", "the-app")
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_TENANT_INSTALLATION_ID", raising=False)

    def verify(authorization):
        token = (authorization or "").removeprefix("Bearer ")
        return {"app": {"id": "the-app", "installationId": token.removeprefix("fit-"),
                        "apiBaseUrl": "https://api.atlassian.com/ex/jira/c"}}

    with patch("backend.tenancy.verify_forge_invocation_token", side_effect=verify):
        yield


def _as(installation):
    return {"Authorization": f"Bearer fit-{installation}", "x-forge-oauth-system": "tok"}


def test_one_tenants_result_is_invisible_to_another(client, forge):
    with patch("backend.jira_client.requests.get", return_value=_response(200, _issue("KAN-5", ["A"]))):
        client.post("/api/coverage/gap-analysis/start", params=PARAMS, headers=_as("A"))
    mine = client.get("/api/coverage/gap-analysis/result", params={"jira_key": "KAN-5"}, headers=_as("A")).json()
    theirs = client.get("/api/coverage/gap-analysis/result", params={"jira_key": "KAN-5"}, headers=_as("B")).json()
    assert mine["status"] == "done" and theirs["status"] == "none"


def test_the_forge_system_token_is_what_the_background_job_uses(client, forge):
    with patch("backend.jira_client.requests.get", return_value=_response(200, _issue("KAN-5", ["A"]))) as jira:
        client.post("/api/coverage/gap-analysis/start", params=PARAMS, headers=_as("A"))
    assert jira.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"
