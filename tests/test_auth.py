import hmac
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.auth import require_webhook_token


def test_webhook_token_uses_constant_time_comparison(monkeypatch):
    monkeypatch.setenv("JIRA_WEBHOOK_SECRET", "webhook-secret")
    with patch("backend.auth.hmac.compare_digest", wraps=hmac.compare_digest) as mock_compare:
        require_webhook_token(token="webhook-secret")
    mock_compare.assert_called_once_with("webhook-secret", "webhook-secret")


def test_webhook_token_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("JIRA_WEBHOOK_SECRET", "webhook-secret")
    require_webhook_token(token="webhook-secret")


def test_webhook_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("JIRA_WEBHOOK_SECRET", "webhook-secret")
    with pytest.raises(HTTPException) as exc_info:
        require_webhook_token(token="wrong-token")
    assert exc_info.value.status_code == 401


def test_webhook_token_fails_closed_when_unconfigured(monkeypatch):
    monkeypatch.delenv("JIRA_WEBHOOK_SECRET", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        require_webhook_token(token="anything")
    assert exc_info.value.status_code == 500
