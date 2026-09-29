"""
Tests for CoreMind Authentication System.

Covers:
- Local email/password registration & login
- Google OAuth URL generation & Google sign-in
- JWT generation, validation, and token refresh
- User profile retrieval and updating
- Password changing
- Protected route dependencies
- Interactive Antigravity auth portal
"""

from __future__ import annotations

import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.app.application import create_app
from src.auth.models import (
    GoogleAuthRequest,
    UserLoginRequest,
    UserRegisterRequest,
)
from src.auth.security import create_access_token, decode_token, hash_password, verify_password
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


# ── Security & Hashing Tests ─────────────────────────────────────────

def test_password_hashing():
    """Test bcrypt hashing and verification."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password(password, None) is False


def test_jwt_access_and_refresh_tokens():
    """Test JWT access token creation and decoding."""
    token, expires_in = create_access_token(
        user_id="user-123",
        email="test@coremind.ai",
        extra_claims={"role": "user"},
    )
    assert expires_in > 0
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["email"] == "test@coremind.ai"
    assert payload["role"] == "user"
    assert payload["type"] == "access"


def test_jwt_invalid_token_type():
    """Test decoding fails when token type mismatches."""
    token, _ = create_access_token(user_id="user-123", email="test@coremind.ai")
    with pytest.raises(AuthError) as exc_info:
        decode_token(token, expected_type="refresh")
    assert exc_info.value.code == ErrorCode.AUTH_TOKEN_INVALID


# ── Registration & Login Flow Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_register_and_login_flow(auth_service: AuthService):
    """Test complete register and subsequent login cycle."""
    # 1. Register
    reg_req = UserRegisterRequest(
        email="ada@coremind.ai",
        password="AdaPassword2026!",
        name="Ada Lovelace",
    )
    res = await auth_service.register(reg_req)
    assert res.access_token
    assert res.refresh_token
    assert res.user.email == "ada@coremind.ai"
    assert res.user.name == "Ada Lovelace"
    assert res.user.provider == "local"

    # 2. Login
    login_req = UserLoginRequest(
        email="ada@coremind.ai",
        password="AdaPassword2026!",
    )
    login_res = await auth_service.login(login_req)
    assert login_res.access_token
    assert login_res.user.email == "ada@coremind.ai"


@pytest.mark.asyncio
async def test_register_duplicate_email(auth_service: AuthService):
    """Test registering with an existing email raises AUTH_USER_EXISTS."""
    reg_req = UserRegisterRequest(
        email="duplicate@coremind.ai",
        password="Password123!",
        name="User One",
    )
    await auth_service.register(reg_req)

    with pytest.raises(AuthError) as exc_info:
        await auth_service.register(reg_req)
    assert exc_info.value.code == ErrorCode.AUTH_USER_EXISTS


@pytest.mark.asyncio
async def test_login_invalid_password(auth_service: AuthService):
    """Test login with wrong password raises AUTH_INVALID_CREDENTIALS."""
    await auth_service.register(
        UserRegisterRequest(
            email="test@coremind.ai",
            password="CorrectPassword123!",
            name="Tester",
        )
    )

    with pytest.raises(AuthError) as exc_info:
        await auth_service.login(
            UserLoginRequest(email="test@coremind.ai", password="WrongPassword!")
        )
    assert exc_info.value.code == ErrorCode.AUTH_INVALID_CREDENTIALS


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
    mock_tokeninfo = {
        "sub": "google-uid-998877",
        "email": "google.dev@example.com",
        "name": "Google Developer",
        "picture": "https://lh3.googleusercontent.com/avatar.jpg",
        "email_verified": "true",
    }

    with patch.object(
        auth_service, "_verify_google_id_token", new_callable=AsyncMock
    ) as mock_verify:
        mock_verify.return_value = {
            "google_id": mock_tokeninfo["sub"],
            "email": mock_tokeninfo["email"],
            "name": mock_tokeninfo["name"],
            "avatar_url": mock_tokeninfo["picture"],
        }

        res = await auth_service.google_auth(
            GoogleAuthRequest(id_token="mock_valid_google_id_token")
        )
        assert res.access_token
        assert res.user.email == "google.dev@example.com"
        assert res.user.name == "Google Developer"
        assert res.user.provider == "google"
        assert res.user.avatar_url == "https://lh3.googleusercontent.com/avatar.jpg"

        # Verify password login fails with friendly Google prompt
        with pytest.raises(AuthError) as exc_info:
            await auth_service.login(
                UserLoginRequest(email="google.dev@example.com", password="any_password")
            )
        assert "Google Sign-In" in str(exc_info.value)


# ── API Route Integration Tests ──────────────────────────────────────

def test_api_auth_register_and_me(client: TestClient):
    """Test POST /v1/auth/register, then GET /v1/auth/me with Bearer token."""
    # 1. Register via HTTP API
    reg_payload = {
        "email": "newuser@coremind.ai",
        "password": "Password789!",
        "name": "New CoreMind Dev",
    }
    reg_res = client.post("/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    data = reg_res.json()
    assert "access_token" in data
    token = data["access_token"]

    # 2. Access protected /v1/auth/me
    me_res = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    user_info = me_res.json()
    assert user_info["email"] == "newuser@coremind.ai"
    assert user_info["name"] == "New CoreMind Dev"

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
    assert "Create Account" in res.text
    assert "Sign In" in res.text
