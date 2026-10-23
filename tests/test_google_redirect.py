"""The Google callback is this backend's own address unless GOOGLE_REDIRECT_URI is set."""

from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from src.app.application import create_app
from src.config import Settings, settings

HOSTED_CALLBACK = "https://coremind-ai-backend.onrender.com/v1/auth/google/callback"
HOSTED_HEADERS = {"Host": "coremind-ai-backend.onrender.com", "X-Forwarded-Proto": "https"}
CONFIGURED_CALLBACK = "http://127.0.0.1:43110/v1/auth/google/callback"
PROFILE = {
    "google_id": "google-redirect-user",
    "email": "redirect.user@gmail.com",
    "name": "Redirect User",
    "avatar_url": None,
}


def _redirect_in(auth_url: str) -> str:
    return parse_qs(urlparse(auth_url).query)["redirect_uri"][0]


@pytest.fixture
def unset_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_redirect_uri", None)


def test_the_setting_is_unset_by_default() -> None:
    assert Settings.model_fields["google_redirect_uri"].default is None


def test_unset_redirect_uses_the_public_address_from_forwarded_headers(unset_redirect) -> None:
    client = TestClient(create_app())
    response = client.get("/v1/auth/google/url", headers=HOSTED_HEADERS)
    assert response.status_code == 200
    assert _redirect_in(response.json()["auth_url"]) == HOSTED_CALLBACK


def test_unset_redirect_uses_the_request_host_when_not_behind_a_proxy(unset_redirect) -> None:
    client = TestClient(create_app())
    response = client.get("/v1/auth/google/url")
    assert _redirect_in(response.json()["auth_url"]) == "http://testserver/v1/auth/google/callback"


def test_configured_redirect_wins_over_the_request_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_redirect_uri", CONFIGURED_CALLBACK)
    client = TestClient(create_app())
    response = client.get("/v1/auth/google/url", headers=HOSTED_HEADERS)
    assert _redirect_in(response.json()["auth_url"]) == CONFIGURED_CALLBACK


def test_a_client_supplied_redirect_wins_over_both(unset_redirect) -> None:
    client = TestClient(create_app())
    response = client.get(
        "/v1/auth/google/url",
        params={"redirect_uri": "http://127.0.0.1:43110/custom/callback"},
        headers=HOSTED_HEADERS,
    )
    assert _redirect_in(response.json()["auth_url"]) == "http://127.0.0.1:43110/custom/callback"


def test_token_exchange_uses_the_redirect_the_state_was_issued_with(
    unset_redirect, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(create_app())
    client.get("/v1/auth/google/url", params={"state": "hosted-state"}, headers=HOSTED_HEADERS)

    # The configured value changes after the state was issued. The exchange uses the issued one.
    monkeypatch.setattr(settings, "google_redirect_uri", CONFIGURED_CALLBACK)
    with patch(
        "src.auth.service.auth_service._exchange_google_code", new_callable=AsyncMock
    ) as mock_exchange:
        mock_exchange.return_value = PROFILE
        response = client.get(
            "/v1/auth/google/callback", params={"code": "hosted-code", "state": "hosted-state"}
        )

    assert response.status_code == 200
    mock_exchange.assert_awaited_once_with("hosted-code", HOSTED_CALLBACK)


def test_desktop_code_exchange_without_a_redirect_uses_the_public_address(unset_redirect) -> None:
    client = TestClient(create_app())
    with patch(
        "src.auth.service.auth_service._exchange_google_code", new_callable=AsyncMock
    ) as mock_exchange:
        mock_exchange.return_value = PROFILE
        response = client.post(
            "/v1/auth/google", json={"code": "desktop-code"}, headers=HOSTED_HEADERS
        )

    assert response.status_code == 200
    mock_exchange.assert_awaited_once_with("desktop-code", HOSTED_CALLBACK)
