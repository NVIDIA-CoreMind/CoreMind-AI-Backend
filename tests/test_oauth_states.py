"""Google sign-in states are single-use, expire, survive restarts, and keep their redirect."""

import sqlite3
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import src.auth.oauth_states as oauth_states_module
from src.api.routes import auth as auth_routes
from src.app.application import create_app
from src.auth.oauth_states import OAuthStateStore

REDIRECT = "https://coremind-ai-backend.onrender.com/v1/auth/google/callback"


def test_state_returns_its_redirect_once(tmp_path) -> None:
    store = OAuthStateStore(str(tmp_path / "states.db"))
    store.issue("state-once", REDIRECT)
    assert store.consume("state-once") == REDIRECT
    assert store.consume("state-once") is None


def test_unissued_state_is_refused(tmp_path) -> None:
    store = OAuthStateStore(str(tmp_path / "states.db"))
    assert store.consume("never-issued") is None


def test_expired_state_is_refused(tmp_path) -> None:
    store = OAuthStateStore(str(tmp_path / "states.db"), ttl_seconds=-1)
    store.issue("already-expired", REDIRECT)
    assert store.consume("already-expired") is None


def test_state_survives_a_restart(tmp_path) -> None:
    db_path = str(tmp_path / "states.db")
    OAuthStateStore(db_path).issue("issued-before-restart", REDIRECT)
    # A new instance on the same database stands in for a restarted backend process.
    assert OAuthStateStore(db_path).consume("issued-before-restart") == REDIRECT


def test_legacy_state_without_a_redirect_is_refused(tmp_path) -> None:
    db_path = str(tmp_path / "states.db")
    # The table as it was before the redirect was stored.
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE oauth_states (state TEXT PRIMARY KEY, expires_at REAL NOT NULL)")
        conn.execute("INSERT INTO oauth_states VALUES ('legacy', ?)", (9_999_999_999.0,))
    store = OAuthStateStore(db_path)
    assert store.consume("legacy") is None


def test_callback_exchanges_the_code_with_the_issued_redirect(monkeypatch) -> None:
    client = TestClient(create_app())
    issued = client.get("/v1/auth/google/url", params={"state": "restart-flow-state"})
    assert issued.status_code == 200
    issued_redirect = parse_qs(urlparse(issued.json()["auth_url"]).query)["redirect_uri"][0]

    # A restarted backend has a new store on the same database.
    monkeypatch.setattr(
        auth_routes, "oauth_states", OAuthStateStore(auth_routes.oauth_states.db_path)
    )
    profile = {
        "google_id": "google-restart-user",
        "email": "restart.user@gmail.com",
        "name": "Restart User",
        "avatar_url": None,
    }
    with patch(
        "src.auth.service.auth_service._exchange_google_code", new_callable=AsyncMock
    ) as mock_exchange:
        mock_exchange.return_value = profile
        response = client.get(
            "/v1/auth/google/callback",
            params={"code": "sample_oauth_code", "state": "restart-flow-state"},
        )

    assert response.status_code == 200
    assert "Authentication Successful" in response.text
    mock_exchange.assert_awaited_once_with("sample_oauth_code", issued_redirect)


def test_callback_rejects_a_replayed_state() -> None:
    client = TestClient(create_app())
    client.get("/v1/auth/google/url", params={"state": "replayed-state"})
    profile = {
        "google_id": "google-replay-user",
        "email": "replay.user@gmail.com",
        "name": "Replay User",
        "avatar_url": None,
    }
    with patch(
        "src.auth.service.auth_service._exchange_google_code", new_callable=AsyncMock
    ) as mock_exchange:
        mock_exchange.return_value = profile
        callback = "/v1/auth/google/callback"
        first = client.get(callback, params={"code": "c1", "state": "replayed-state"})
        second = client.get(callback, params={"code": "c2", "state": "replayed-state"})

    assert first.status_code == 200
    assert second.status_code == 400
    assert "expired or was not started by CoreMind" in second.text


def test_default_window_is_thirty_minutes(tmp_path) -> None:
    assert OAuthStateStore(str(tmp_path / "states.db")).ttl_seconds == 30 * 60


def test_state_survives_a_slow_consent_screen(tmp_path, monkeypatch) -> None:
    clock = [1_000_000.0]
    monkeypatch.setattr(oauth_states_module.time, "time", lambda: clock[0])
    store = OAuthStateStore(str(tmp_path / "states.db"))
    store.issue("slow-sign-in", REDIRECT)
    clock[0] += 15 * 60
    assert store.consume("slow-sign-in") == REDIRECT


def test_state_is_refused_after_thirty_minutes(tmp_path, monkeypatch) -> None:
    clock = [1_000_000.0]
    monkeypatch.setattr(oauth_states_module.time, "time", lambda: clock[0])
    store = OAuthStateStore(str(tmp_path / "states.db"))
    store.issue("too-slow", REDIRECT)
    clock[0] += 31 * 60
    assert store.consume("too-slow") is None
