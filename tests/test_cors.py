"""CORS allowlist: browser origins come from FRONTEND_ORIGIN, not from a wildcard."""

import pytest
from fastapi.testclient import TestClient

from src.app.application import create_app
from src.config import settings

HOSTED_WEB_ORIGIN = "https://coremind-application.onrender.com"


def _allow_origin_header(origin: str) -> str | None:
    # create_app() reads settings.frontend_origin, so callers must set it before this runs.
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": origin})
    assert response.status_code == 200
    return response.headers.get("access-control-allow-origin")


def test_configured_hosted_origin_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_origin", f"http://localhost:5173,{HOSTED_WEB_ORIGIN}")
    assert _allow_origin_header(HOSTED_WEB_ORIGIN) == HOSTED_WEB_ORIGIN


def test_hosted_origin_is_blocked_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_origin", "http://localhost:5173")
    assert _allow_origin_header(HOSTED_WEB_ORIGIN) is None


def test_unlisted_origin_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_origin", f"http://localhost:5173,{HOSTED_WEB_ORIGIN}")
    assert _allow_origin_header("https://evil.example") is None
