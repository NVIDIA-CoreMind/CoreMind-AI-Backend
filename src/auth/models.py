"""
CoreMind Backend — Authentication Models and Schemas.

Pydantic schemas for user accounts, credentials, tokens, and OAuth.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class User(BaseModel):
    """Internal user representation stored in the database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    avatar_url: str | None = None
    hashed_password: str | None = None
    provider: str = "local"  # 'local' | 'google'
    google_id: str | None = None
    role: str = "user"  # 'user' | 'admin'
    is_active: bool = True
    created_at: str
    updated_at: str
    last_login_at: str | None = None


class UserRegisterRequest(BaseModel):
    """Payload for creating a new local account."""

    email: str = Field(..., pattern=EMAIL_REGEX, description="User's valid email address")
    password: str = Field(
        ..., min_length=6, max_length=128, description="Account password (min 6 chars)"
    )
    name: str = Field(..., min_length=1, max_length=100, description="User's display or full name")


class UserLoginRequest(BaseModel):
    """Payload for logging into an existing account."""

    email: str = Field(..., pattern=EMAIL_REGEX, description="Registered email address")
    password: str = Field(..., min_length=1, description="Account password")


class GoogleAuthRequest(BaseModel):
    """
    Payload for Google Authentication.
    Accepts either an ID token (from Google One-Tap or Google Sign-In SDK)
    or an OAuth authorization code.
    """

    id_token: str | None = Field(
        default=None,
        description="Google JWT ID token obtained on frontend or IDE webview",
    )
    code: str | None = Field(
        default=None,
        description="OAuth2 authorization code from Google OAuth redirect",
    )
    redirect_uri: str | None = Field(
        default=None,
        description="Redirect URI used when requesting authorization code",
    )


class GoogleAuthUrlResponse(BaseModel):
    """Google OAuth2 consent URL information."""

    auth_url: str
    client_id: str
    state: str


class UserResponse(BaseModel):
    """Safe user profile response without secrets."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    avatar_url: str | None = None
    provider: str
    role: str
    created_at: str
    last_login_at: str | None = None


class TokenResponse(BaseModel):
    """Authentication token response with user profile."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    """Payload to exchange a refresh token for a new access token."""

    refresh_token: str = Field(..., description="Valid refresh token")


class UpdateProfileRequest(BaseModel):
    """Payload for updating user profile fields."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=500)


class ChangePasswordRequest(BaseModel):
    """Payload for changing local account password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)
