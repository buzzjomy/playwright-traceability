from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.main import _bootstrap_jira_connection_from_env
from backend.models import JiraConnection


def _session_factory():
    """Build a fresh isolated in-memory sessionmaker for one test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _fake_response(status_code: int, json_body: dict):
    class _Response:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return json_body

        def raise_for_status(self):
            if status_code >= 400:
                import requests

                raise requests.exceptions.HTTPError(response=self)

    return _Response()


def test_does_nothing_without_all_three_env_vars(monkeypatch):
    monkeypatch.delenv("JIRA_SITE_URL", raising=False)
    monkeypatch.setenv("JIRA_EMAIL", "me@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")

    with patch("backend.main.SessionLocal") as mock_session_local:
        _bootstrap_jira_connection_from_env()

    mock_session_local.assert_not_called()


def test_creates_connection_when_none_exists(monkeypatch):
    monkeypatch.setenv("JIRA_SITE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "me@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")

    session_factory = _session_factory()
    with patch("backend.main.SessionLocal", session_factory):
        with patch("backend.jira_client.requests.get") as mock_get:
            mock_get.return_value = _fake_response(200, {"accountId": "abc123", "displayName": "Jane Doe"})
            _bootstrap_jira_connection_from_env()

    db = session_factory()
    connection = db.query(JiraConnection).first()
    assert connection is not None
    assert connection.email == "me@example.com"
    assert connection.api_token == "token"
    assert connection.site_url == "https://example.atlassian.net/"


def test_does_not_overwrite_an_existing_connection(monkeypatch):
    monkeypatch.setenv("JIRA_SITE_URL", "https://from-env.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "env@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "env-token")

    session_factory = _session_factory()
    db = session_factory()
    db.add(
        JiraConnection(
            site_url="https://already-connected.atlassian.net/",
            email="existing@example.com",
            api_token="existing-token",
        )
    )
    db.commit()
    db.close()

    with patch("backend.main.SessionLocal", session_factory):
        with patch("backend.jira_client.requests.get") as mock_get:
            _bootstrap_jira_connection_from_env()

    mock_get.assert_not_called()
    db = session_factory()
    connection = db.query(JiraConnection).first()
    assert connection.email == "existing@example.com"


def test_credentials_rejected_by_jira_do_not_raise_or_persist(monkeypatch):
    monkeypatch.setenv("JIRA_SITE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "me@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "bad-token")

    session_factory = _session_factory()
    with patch("backend.main.SessionLocal", session_factory):
        with patch("backend.jira_client.requests.get") as mock_get:
            mock_get.return_value = _fake_response(401, {})
            _bootstrap_jira_connection_from_env()  # must not raise

    db = session_factory()
    assert db.query(JiraConnection).first() is None


def test_malformed_url_does_not_raise_or_persist(monkeypatch):
    monkeypatch.setenv("JIRA_SITE_URL", "not-a-url")
    monkeypatch.setenv("JIRA_EMAIL", "me@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")

    session_factory = _session_factory()
    with patch("backend.main.SessionLocal", session_factory):
        with patch("backend.jira_client.requests.get") as mock_get:
            _bootstrap_jira_connection_from_env()  # must not raise

    mock_get.assert_not_called()
    db = session_factory()
    assert db.query(JiraConnection).first() is None


def test_end_to_end_via_lifespan(client):
    """The client fixture's TestClient already triggered the app's
    lifespan with no JIRA_* env vars set, so no auto-connect should have
    happened - confirms the wiring doesn't misfire when unconfigured."""
    response = client.get("/api/jira/connection")
    assert response.status_code == 200
    assert response.json()["connected"] is False
