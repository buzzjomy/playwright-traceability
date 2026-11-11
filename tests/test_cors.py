from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.main import cors_settings_from_env


def test_cors_is_off_by_default(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOW_ORIGIN_REGEX", raising=False)
    assert cors_settings_from_env() is None


def test_exact_origins_are_parsed_and_trimmed(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", " https://a.example , https://b.example ,")
    monkeypatch.delenv("CORS_ALLOW_ORIGIN_REGEX", raising=False)
    settings = cors_settings_from_env()
    assert settings["allow_origins"] == ["https://a.example", "https://b.example"]
    assert settings["allow_credentials"] is False


def test_regex_alone_enables_cors(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.setenv("CORS_ALLOW_ORIGIN_REGEX", r"https://.*\.atlassian-dev\.net")
    settings = cors_settings_from_env()
    assert settings["allow_origins"] == []
    assert settings["allow_origin_regex"] == r"https://.*\.atlassian-dev\.net"


def test_preflight_from_allowed_origin_succeeds_and_others_do_not(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://forge.example")
    monkeypatch.delenv("CORS_ALLOW_ORIGIN_REGEX", raising=False)

    test_app = FastAPI()
    test_app.add_middleware(CORSMiddleware, **cors_settings_from_env())

    @test_app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(test_app)
    preflight_headers = {
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }

    allowed = client.options("/ping", headers={"Origin": "https://forge.example", **preflight_headers})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://forge.example"

    blocked = client.options("/ping", headers={"Origin": "https://evil.example", **preflight_headers})
    assert "access-control-allow-origin" not in blocked.headers
