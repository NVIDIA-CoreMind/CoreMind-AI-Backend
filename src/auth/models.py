"""
CoreMind Backend — Authentication Models and Schemas.

Pydantic schemas for Google OAuth user accounts, credentials, and JWT tokens.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """Internal user representation stored in the database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    avatar_url: str | None = None
    provider: str = "google"
    google_id: str | None = None
    role: str = "user"  # 'user' | 'admin'
    is_active: bool = True
    created_at: str
    updated_at: str
    last_login_at: str | None = None


class GoogleAuthRequest(BaseModel):
    """
    Payload for Google Authentication.
    Accepts either an ID token (from Google One-Tap or Google Sign-In SDK)
    or an OAuth authorization code from Google OAuth redirect.
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
    """Safe user profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    avatar_url: str | None = None
    provider: str = "google"
    role: str
    created_at: str
    last_login_at: str | None = None


class TokenResponse(BaseModel):
    """Authentication token response with user profile."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    """Payload to exchange a refresh token for a new access token."""

    refresh_token: str = Field(..., description="Valid refresh token")


class UpdateProfileRequest(BaseModel):
    """Payload for updating user profile fields."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=500)
