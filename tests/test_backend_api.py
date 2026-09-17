import json
from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base, get_db
from backend.main import app


def _fake_response(status_code: int, json_body: dict | None = None) -> requests.Response:
    """Build a minimal requests.Response for mocking Jira API calls."""
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(json_body or {}).encode("utf-8")
    return response


@pytest.fixture()
def client(tmp_path):
    """A TestClient backed by an isolated, per-test SQLite database."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_connection_when_none_configured(client):
    response = client.get("/api/jira/connection")
    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "site_url": None,
        "email": None,
        "account_id": None,
        "display_name": None,
    }


def test_create_connection_with_valid_credentials(client):
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"accountId": "abc123", "displayName": "Jane Doe"})
        response = client.post(
            "/api/jira/connection",
            json={"site_url": "https://example.atlassian.net", "email": "me@example.com", "api_token": "token123"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["email"] == "me@example.com"
    assert body["account_id"] == "abc123"
    assert body["display_name"] == "Jane Doe"


def test_create_connection_with_invalid_credentials_returns_401(client):
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(401)
        response = client.post(
            "/api/jira/connection",
            json={"site_url": "https://example.atlassian.net", "email": "me@example.com", "api_token": "wrong"},
        )

    assert response.status_code == 401


def test_create_connection_never_returns_api_token(client):
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"accountId": "abc123", "displayName": "Jane Doe"})
        response = client.post(
            "/api/jira/connection",
            json={"site_url": "https://example.atlassian.net", "email": "me@example.com", "api_token": "super-secret"},
        )

    assert "super-secret" not in response.text


def test_get_connection_after_create_reflects_stored_connection(client):
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"accountId": "abc123", "displayName": "Jane Doe"})
        client.post(
            "/api/jira/connection",
            json={"site_url": "https://example.atlassian.net", "email": "me@example.com", "api_token": "token123"},
        )

        response = client.get("/api/jira/connection")

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["site_url"] == "https://example.atlassian.net/"
    assert body["email"] == "me@example.com"


def test_creating_a_second_connection_replaces_the_first(client):
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"accountId": "abc123", "displayName": "Jane Doe"})
        client.post(
            "/api/jira/connection",
            json={"site_url": "https://one.atlassian.net", "email": "one@example.com", "api_token": "token1"},
        )
        client.post(
            "/api/jira/connection",
            json={"site_url": "https://two.atlassian.net", "email": "two@example.com", "api_token": "token2"},
        )

        response = client.get("/api/jira/connection")

    assert response.json()["email"] == "two@example.com"


def test_delete_connection_clears_it(client):
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"accountId": "abc123", "displayName": "Jane Doe"})
        client.post(
            "/api/jira/connection",
            json={"site_url": "https://example.atlassian.net", "email": "me@example.com", "api_token": "token123"},
        )

    delete_response = client.delete("/api/jira/connection")
    assert delete_response.status_code == 204

    get_response = client.get("/api/jira/connection")
    assert get_response.json()["connected"] is False


def test_get_connection_reflects_credentials_revoked_after_setup(client):
    with patch("backend.jira_client.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, {"accountId": "abc123", "displayName": "Jane Doe"})
        client.post(
            "/api/jira/connection",
            json={"site_url": "https://example.atlassian.net", "email": "me@example.com", "api_token": "token123"},
        )

        mock_get.return_value = _fake_response(401)
        response = client.get("/api/jira/connection")

    assert response.json()["connected"] is False
