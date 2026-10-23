"""Google sign-in states are single-use, expire, and survive a backend restart."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import src.auth.oauth_states as oauth_states_module
from src.api.routes import auth as auth_routes
from src.app.application import create_app
from src.auth.oauth_states import OAuthStateStore


def test_state_can_be_consumed_once(tmp_path) -> None:
    store = OAuthStateStore(str(tmp_path / "states.db"))
    store.issue("state-once")
    assert store.consume("state-once") is True
    assert store.consume("state-once") is False


def test_unissued_state_is_refused(tmp_path) -> None:
    store = OAuthStateStore(str(tmp_path / "states.db"))
    assert store.consume("never-issued") is False


def test_expired_state_is_refused(tmp_path) -> None:
    store = OAuthStateStore(str(tmp_path / "states.db"), ttl_seconds=-1)
    store.issue("already-expired")
    assert store.consume("already-expired") is False


def test_state_survives_a_restart(tmp_path) -> None:
    db_path = str(tmp_path / "states.db")
    OAuthStateStore(db_path).issue("issued-before-restart")
    # A new instance on the same database stands in for a restarted backend process.
    assert OAuthStateStore(db_path).consume("issued-before-restart") is True


def test_callback_accepts_state_issued_before_a_restart(monkeypatch) -> None:
    client = TestClient(create_app())
    issued = client.get("/v1/auth/google/url", params={"state": "restart-flow-state"})
    assert issued.status_code == 200

    restarted = OAuthStateStore(auth_routes.oauth_states.db_path)
    monkeypatch.setattr(auth_routes, "oauth_states", restarted)

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
    assert "expired" not in response.text


def test_callback_rejects_a_replayed_state(monkeypatch) -> None:
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
    store.issue("slow-sign-in")
    clock[0] += 15 * 60
    assert store.consume("slow-sign-in") is True


def test_state_is_refused_after_thirty_minutes(tmp_path, monkeypatch) -> None:
    clock = [1_000_000.0]
    monkeypatch.setattr(oauth_states_module.time, "time", lambda: clock[0])
    store = OAuthStateStore(str(tmp_path / "states.db"))
    store.issue("too-slow")
    clock[0] += 31 * 60
    assert store.consume("too-slow") is False
