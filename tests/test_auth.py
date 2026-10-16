"""
Tests for CoreMind Google Authentication System.

Covers:
- Google OAuth URL generation & consent flow
- Google ID token verification and user syncing
- JWT token issuing, validation, and refresh
- User profile retrieval and updating
- Bearer token authentication dependencies
- Antigravity Google Auth portal UI
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.app.application import create_app
from src.auth.models import (
    GoogleAuthRequest,
    RefreshTokenRequest,
    UpdateProfileRequest,
)
from src.auth.security import create_access_token, decode_token
from src.auth.service import AuthService
from src.auth.storage import UserStorage
from src.utils.errors import AuthError, ErrorCode


@pytest.fixture
def temp_storage():
    """Create an isolated SQLite storage for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "test_auth.db")
        storage = UserStorage(db_path=db_path)
        yield storage


@pytest.fixture
def auth_service(temp_storage):
    """Create an AuthService wired to isolated storage."""
    return AuthService(storage=temp_storage)


@pytest.fixture
def client(temp_storage):
    """Create a TestClient with overridden storage."""
    app = create_app()
    with patch("src.auth.service.user_storage", temp_storage), \
         patch("src.auth.dependencies.user_storage", temp_storage), \
         patch("src.auth.service.auth_service.storage", temp_storage):
        yield TestClient(app)


# ── JWT Security Tests ───────────────────────────────────────────────

def test_jwt_access_and_refresh_tokens():
    """Test JWT access token creation and decoding."""
    token, expires_in = create_access_token(
        user_id="google-user-123",
        email="developer@gmail.com",
        extra_claims={"role": "user", "name": "Google Dev"},
    )
    assert expires_in > 0
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "google-user-123"
    assert payload["email"] == "developer@gmail.com"
    assert payload["name"] == "Google Dev"
    assert payload["type"] == "access"


def test_jwt_invalid_token_type():
    """Test decoding fails when token type mismatches."""
    token, _ = create_access_token(user_id="user-123", email="dev@gmail.com")
    with pytest.raises(AuthError) as exc_info:
        decode_token(token, expected_type="refresh")
    assert exc_info.value.code == ErrorCode.AUTH_TOKEN_INVALID


# ── Google OAuth Tests ───────────────────────────────────────────────

def test_google_auth_url(auth_service: AuthService):
    """Test generating Google OAuth consent URL."""
    res = auth_service.get_google_auth_url(state="test-state-123")
    assert "https://accounts.google.com/o/oauth2/v2/auth" in res.auth_url
    assert "state=test-state-123" in res.auth_url
    assert "scope=openid+email+profile" in res.auth_url or "openid" in res.auth_url


@pytest.mark.asyncio
async def test_google_auth_with_token(auth_service: AuthService):
    """Test Continue with Google via Google ID token."""
    mock_profile = {
        "google_id": "google-uid-998877",
        "email": "alex.mercer@gmail.com",
        "name": "Alex Mercer",
        "avatar_url": "https://lh3.googleusercontent.com/avatar.jpg",
    }

    with patch.object(
        auth_service, "_verify_google_id_token", new_callable=AsyncMock
    ) as mock_verify:
        mock_verify.return_value = mock_profile

        res = await auth_service.google_auth(
            GoogleAuthRequest(id_token="mock_valid_google_id_token")
        )
        assert res.access_token
        assert res.user.email == "alex.mercer@gmail.com"
        assert res.user.name == "Alex Mercer"
        assert res.user.provider == "google"
        assert res.user.avatar_url == "https://lh3.googleusercontent.com/avatar.jpg"


@pytest.mark.asyncio
async def test_google_auth_refresh_token_and_profile(auth_service: AuthService):
    """Test token refresh and profile update."""
    mock_profile = {
        "google_id": "google-uid-112233",
        "email": "dev.user@gmail.com",
        "name": "Dev User",
        "avatar_url": None,
    }

    with patch.object(
        auth_service, "_verify_google_id_token", new_callable=AsyncMock
    ) as mock_verify:
        mock_verify.return_value = mock_profile
        login_res = await auth_service.google_auth(GoogleAuthRequest(id_token="token"))

    # Refresh token
    refresh_res = await auth_service.refresh_token(
        RefreshTokenRequest(refresh_token=login_res.refresh_token)
    )
    assert refresh_res.access_token
    assert refresh_res.user.email == "dev.user@gmail.com"

    # Update profile
    updated_profile = await auth_service.update_profile(
        user_id=login_res.user.id,
        req=UpdateProfileRequest(name="Dev User Updated", avatar_url="https://avatar.png"),
    )
    assert updated_profile.name == "Dev User Updated"
    assert updated_profile.avatar_url == "https://avatar.png"


# ── API Route Integration Tests ──────────────────────────────────────

def test_api_google_auth_and_me(client: TestClient):
    """Test POST /v1/auth/google, then GET /v1/auth/me with Bearer token."""
    mock_profile = {
        "google_id": "google-uid-api-test",
        "email": "coremind.dev@gmail.com",
        "name": "CoreMind Dev",
        "avatar_url": "https://avatar.jpg",
    }

    with patch(
        "src.auth.service.auth_service._verify_google_id_token", new_callable=AsyncMock
    ) as mock_verify:
        mock_verify.return_value = mock_profile

        # 1. Sign in with Google
        res = client.post("/v1/auth/google", json={"id_token": "valid_token"})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        token = data["access_token"]

        # 2. Access protected /v1/auth/me
        me_res = client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 200
        user_info = me_res.json()
        assert user_info["email"] == "coremind.dev@gmail.com"
        assert user_info["name"] == "CoreMind Dev"
        assert user_info["provider"] == "google"

        # 3. Access without token should return 401
        unauth_res = client.get("/v1/auth/me")
        assert unauth_res.status_code == 401


def test_api_auth_portal_ui(client: TestClient):
    """Test GET /auth serves the interactive Antigravity authentication portal."""
    res = client.get("/auth")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Welcome to Antigravity" in res.text
    assert "Continue with Google" in res.text


def test_api_get_google_auth_url(client: TestClient):
    """Test GET /v1/auth/google/url endpoint with default and custom params."""
    # 1. Default request
    res = client.get("/v1/auth/google/url")
    assert res.status_code == 200
    data = res.json()
    assert "auth_url" in data
    assert "client_id" in data
    assert "state" in data
    assert len(data["state"]) > 10
    assert "http%3A%2F%2F127.0.0.1%3A43110%2Fv1%2Fauth%2Fgoogle%2Fcallback" in data["auth_url"] or "127.0.0.1" in data["auth_url"]
    assert "accounts.google.com" in data["auth_url"]

    # 2. Custom state and redirect URI
    res_custom = client.get(
        "/v1/auth/google/url",
        params={"state": "custom-uuid-state", "redirect_uri": "http://127.0.0.1:43110/custom/callback"},
    )
    assert res_custom.status_code == 200
    data_custom = res_custom.json()
    assert data_custom["state"] == "custom-uuid-state"
    assert "custom-uuid-state" in data_custom["auth_url"]
    assert "custom%2Fcallback" in data_custom["auth_url"] or "custom/callback" in data_custom["auth_url"]


def test_api_google_callback_and_session_polling(client: TestClient):
    """Test Google callback and desktop session polling flow."""
    test_state = "desktop-session-state-7788"

    # 0. The client starts sign-in with a state value; the callback only accepts states issued here
    issued = client.get("/v1/auth/google/url", params={"state": test_state})
    assert issued.status_code == 200

    # 1. Polling before callback should return 404 pending
    pending_res = client.get("/v1/auth/session", params={"state": test_state})
    assert pending_res.status_code == 404
    assert pending_res.json()["status"] == "pending"

    mock_profile = {
        "google_id": "google-desktop-user",
        "email": "desktop.dev@gmail.com",
        "name": "Desktop Dev",
        "avatar_url": "https://lh3.googleusercontent.com/avatar_desktop.png",
    }

    with patch(
        "src.auth.service.auth_service._verify_google_id_token", new_callable=AsyncMock
    ) as mock_verify, patch(
        "src.auth.service.auth_service._exchange_google_code", new_callable=AsyncMock
    ) as mock_exchange:
        mock_verify.return_value = mock_profile
        mock_exchange.return_value = mock_profile

        # 2. Google redirects back to callback after Chrome sign-in
        cb_res = client.get(
            "/v1/auth/google/callback",
            params={"code": "sample_oauth_code", "state": test_state},
        )
        assert cb_res.status_code == 200
        assert "text/html" in cb_res.headers["content-type"]
        assert "Authentication Successful" in cb_res.text
        assert "You can now close this tab and return to CoreMind IDE." in cb_res.text
        assert "#0F172A" in cb_res.text  # Modern dark background styling

        # 3. Desktop IDE polls /v1/auth/session?state=...
        poll_res = client.get("/v1/auth/session", params={"state": test_state})
        assert poll_res.status_code == 200
        tokens = poll_res.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "Bearer"
        assert tokens["expires_in"] > 0
        assert tokens["user"]["email"] == "desktop.dev@gmail.com"
        assert tokens["user"]["name"] == "Desktop Dev"
        assert tokens["user"]["avatar_url"] == "https://lh3.googleusercontent.com/avatar_desktop.png"
        assert tokens["user"]["provider"] == "google"


def test_api_logout_endpoint(client: TestClient):
    """Test POST /v1/auth/logout endpoint."""
    res = client.post("/v1/auth/logout")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["message"] == "Successfully logged out"
