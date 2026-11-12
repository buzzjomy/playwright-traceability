"""SPIKE (issue #41) - the probe must report on the token without ever
returning it. Delete with backend/spike.py."""

import time
from unittest.mock import patch

import jwt


def _token(seconds_left=7200):
    return jwt.encode({"exp": int(time.time()) + seconds_left}, "k", algorithm="HS256")


def _claims():
    return {"app": {"id": "a", "installationId": "i", "apiBaseUrl": "https://api.atlassian.com/ex/jira/c"}}


def test_probe_reports_without_leaking_the_token(client):
    token = _token()

    class _Resp:
        ok = True
        status_code = 200

        def json(self):
            return {"values": [{"key": "KAN"}]}

    with patch("backend.spike.verify_forge_invocation_token", return_value=_claims()), patch(
        "backend.spike.requests.get", return_value=_Resp()
    ) as mock_get:
        response = client.get("/api/spike/system-token", headers={"Authorization": "Bearer fit", "x-forge-oauth-system": token})

    body = response.json()
    assert body["token_header_present"] is True
    assert 7100 < body["token_expires_in_seconds"] <= 7200
    assert body["jira_projects"] == ["KAN"]
    assert token not in response.text
    assert mock_get.call_args.args[0] == "https://api.atlassian.com/ex/jira/c/rest/api/3/project/search"


def test_probe_without_a_token_says_so(client):
    with patch("backend.spike.verify_forge_invocation_token", return_value=_claims()):
        body = client.get("/api/spike/system-token", headers={"Authorization": "Bearer fit"}).json()
    assert body["token_header_present"] is False and body["jira_status"] is None
