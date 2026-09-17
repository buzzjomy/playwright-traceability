import pytest

REALISTIC_PAYLOAD = {
    "timestamp": 1758087600000,
    "webhookEvent": "jira:issue_updated",
    "issue_event_type_name": "issue_generic",
    "issue": {
        "id": "10013",
        "key": "KAN-4",
        "fields": {"summary": "Google homepage displays search box and logo"},
    },
    "changelog": {
        "id": "10050",
        "items": [
            {
                "field": "description",
                "fieldtype": "jira",
                "from": None,
                "fromString": "old description",
                "to": None,
                "toString": "new description",
            }
        ],
    },
}


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    """Configure a fixed JIRA_WEBHOOK_SECRET for every test in this file."""
    monkeypatch.setenv("JIRA_WEBHOOK_SECRET", "test-webhook-secret")
    return "test-webhook-secret"


def test_missing_token_is_rejected(client):
    response = client.post("/api/webhooks/jira", json=REALISTIC_PAYLOAD)
    assert response.status_code == 401


def test_wrong_token_is_rejected(client):
    response = client.post("/api/webhooks/jira?token=wrong", json=REALISTIC_PAYLOAD)
    assert response.status_code == 401


def test_missing_server_secret_fails_closed(client, monkeypatch):
    monkeypatch.delenv("JIRA_WEBHOOK_SECRET", raising=False)
    response = client.post("/api/webhooks/jira?token=anything", json=REALISTIC_PAYLOAD)
    assert response.status_code == 500


def test_valid_webhook_is_recorded(client):
    response = client.post("/api/webhooks/jira?token=test-webhook-secret", json=REALISTIC_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body == {"received": True, "issue_key": "KAN-4", "webhook_event": "jira:issue_updated"}


def test_recorded_event_is_listable(client):
    client.post("/api/webhooks/jira?token=test-webhook-secret", json=REALISTIC_PAYLOAD)

    response = client.get("/api/webhooks/jira/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["issue_key"] == "KAN-4"
    assert events[0]["webhook_event"] == "jira:issue_updated"
    assert events[0]["changelog"]["items"][0]["field"] == "description"


def test_multiple_events_listed_newest_first(client):
    first_payload = {**REALISTIC_PAYLOAD, "issue": {"key": "KAN-4"}}
    second_payload = {**REALISTIC_PAYLOAD, "issue": {"key": "KAN-5"}}

    client.post("/api/webhooks/jira?token=test-webhook-secret", json=first_payload)
    client.post("/api/webhooks/jira?token=test-webhook-secret", json=second_payload)

    events = client.get("/api/webhooks/jira/events").json()
    assert [e["issue_key"] for e in events] == ["KAN-5", "KAN-4"]


def test_malformed_payload_missing_issue_is_handled_gracefully(client):
    response = client.post("/api/webhooks/jira?token=test-webhook-secret", json={"webhookEvent": "jira:issue_updated"})
    assert response.status_code == 200
    assert response.json()["issue_key"] == ""
