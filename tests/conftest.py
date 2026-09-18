from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base, get_db
from backend.main import app


@pytest.fixture()
def client(tmp_path):
    """A TestClient backed by an isolated, per-test SQLite database.

    Shared across all backend tests so each test gets a clean DB instead of
    sharing state through backend/traceability.db. Also patches
    backend.main.SessionLocal to the same per-test engine: TestClient's
    context manager runs the app's lifespan (which tries to auto-connect
    Jira from JIRA_SITE_URL/JIRA_EMAIL/JIRA_API_TOKEN env vars - see
    _bootstrap_jira_connection_from_env), and that code opens its own
    session directly rather than through the get_db dependency, so it
    would otherwise write into the real backend/traceability.db instead
    of this test's isolated one if those env vars happened to be set in
    a developer's shell (e.g. for tests/integration/).
    """
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
    with patch("backend.main.SessionLocal", testing_session):
        with TestClient(app) as test_client:
            yield test_client
    app.dependency_overrides.clear()
