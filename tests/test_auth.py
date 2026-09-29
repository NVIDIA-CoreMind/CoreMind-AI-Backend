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
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        storage = UserStorage(db_path=tmp.name)
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
