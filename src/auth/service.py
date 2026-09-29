"""
CoreMind Backend — Authentication Service.

Handles user registration, credential verification, Google OAuth2/ID token validation,
and token generation.
"""

from __future__ import annotations

import secrets
import urllib.parse
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from src.auth.models import (
    ChangePasswordRequest,
    GoogleAuthRequest,
    GoogleAuthUrlResponse,
    RefreshTokenRequest,
    TokenResponse,
    UpdateProfileRequest,
    User,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from src.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.auth.storage import UserStorage, user_storage
from src.config import settings
from src.utils.errors import AuthError, ErrorCode
from src.utils.logger import logger


class AuthService:
    """Core authentication logic for local accounts and Google OAuth."""

    def __init__(self, storage: UserStorage | None = None) -> None:
        self.storage = storage or user_storage

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def _build_token_response(self, user: User) -> TokenResponse:
        """Create access and refresh tokens and return the standard TokenResponse."""
        access_token, expires_in = create_access_token(
            user_id=user.id,
            email=user.email,
            extra_claims={"role": user.role, "name": user.name},
        )
        refresh_token = create_refresh_token(
            user_id=user.id,
            email=user.email,
        )
        user_resp = UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            avatar_url=user.avatar_url,
            provider=user.provider,
            role=user.role,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user=user_resp,
        )

    async def register(self, req: UserRegisterRequest) -> TokenResponse:
        """Register a new user account with email and password."""
        email_clean = req.email.strip().lower()
        existing = self.storage.get_by_email(email_clean)
        if existing is not None:
            raise AuthError(
                ErrorCode.AUTH_USER_EXISTS,
                f"An account with email '{email_clean}' already exists. Please sign in.",
            )

        now = self._now_iso()
        user = User(
            id=str(uuid4()),
            email=email_clean,
            name=req.name.strip(),
            avatar_url=None,
            hashed_password=hash_password(req.password),
            provider="local",
            google_id=None,
            role="user",
            is_active=True,
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )
        self.storage.create_user(user)
        logger.info("auth.registered", user_id=user.id, email=user.email)
        return self._build_token_response(user)

    async def login(self, req: UserLoginRequest) -> TokenResponse:
        """Authenticate user with email and password."""
        email_clean = req.email.strip().lower()
        user = self.storage.get_by_email(email_clean)
        if user is None:
            raise AuthError(
                ErrorCode.AUTH_INVALID_CREDENTIALS,
                "Invalid email or password.",
            )

        if not user.hashed_password:
            raise AuthError(
                ErrorCode.AUTH_INVALID_CREDENTIALS,
                "This account uses Google Sign-In. Please click 'Continue with Google'.",
            )

        if not verify_password(req.password, user.hashed_password):
            raise AuthError(
                ErrorCode.AUTH_INVALID_CREDENTIALS,
                "Invalid email or password.",
            )

        if not user.is_active:
            raise AuthError(
                ErrorCode.AUTH_FORBIDDEN,
                "Account is disabled. Please contact support.",
            )

        now = self._now_iso()
        self.storage.update_last_login(user.id, now)
        user.last_login_at = now
        logger.info("auth.logged_in", user_id=user.id, email=user.email)
        return self._build_token_response(user)

    def get_google_auth_url(
        self, state: str | None = None, redirect_uri: str | None = None
    ) -> GoogleAuthUrlResponse:
        """Construct the Google OAuth2 consent authorization URL."""
        client_id = settings.google_client_id or "coremind-google-client-id"
        redirect = redirect_uri or settings.google_redirect_uri
        state_str = state or secrets.token_urlsafe(16)

        params = {
            "client_id": client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "select_account",
            "state": state_str,
        }
        query_string = urllib.parse.urlencode(params)
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query_string}"

        return GoogleAuthUrlResponse(
            auth_url=auth_url,
            client_id=client_id,
            state=state_str,
        )

    async def google_auth(self, req: GoogleAuthRequest) -> TokenResponse:
        """
        Authenticate or create user using Google credentials.
        Supports both:
        1. Google ID token (from One-Tap or Google Sign-In SDK).
        2. Google OAuth authorization code (from OAuth redirect).
        """
        if req.id_token:
            google_profile = await self._verify_google_id_token(req.id_token)
        elif req.code:
            google_profile = await self._exchange_google_code(req.code, req.redirect_uri)
        else:
            raise AuthError(
                ErrorCode.AUTH_GOOGLE_FAILED,
                "Neither Google ID token nor authorization code was provided.",
            )

        return await self._sync_google_user(google_profile)

    async def _verify_google_id_token(self, id_token: str) -> dict[str, Any]:
        """Verify Google ID token via Google's tokeninfo API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"id_token": id_token},
                )
                if res.status_code != 200:
                    logger.error(
                        "auth.google.tokeninfo_error",
                        status=res.status_code,
                        body=res.text,
                    )
                    raise AuthError(
                        ErrorCode.AUTH_GOOGLE_FAILED,
                        "Google ID token verification failed. The token may be expired or invalid.",
                    )
                data = res.json()
        except httpx.RequestError as exc:
            raise AuthError(
                ErrorCode.AUTH_GOOGLE_FAILED,
                f"Failed to communicate with Google authentication service: {exc}",
            ) from exc

        # Validate token claims
        email = data.get("email")
        google_id = data.get("sub")
        if not email or not google_id:
            raise AuthError(
                ErrorCode.AUTH_GOOGLE_FAILED,
                "Google token missing required email or subject identification.",
            )

        # Optional client_id check if configured
        if settings.google_client_id and data.get("aud") != settings.google_client_id:
            logger.warn(
                "auth.google.audience_mismatch",
                token_aud=data.get("aud"),
                expected=settings.google_client_id,
            )

        return {
            "google_id": google_id,
            "email": email.strip().lower(),
            "name": data.get("name") or email.split("@")[0],
            "avatar_url": data.get("picture"),
        }

    async def _exchange_google_code(
        self, code: str, redirect_uri: str | None
    ) -> dict[str, Any]:
        """Exchange authorization code with Google for tokens and profile."""
        if not settings.google_client_id or not settings.google_client_secret:
            raise AuthError(
                ErrorCode.AUTH_GOOGLE_FAILED,
                "Google OAuth credentials (GOOGLE_CLIENT_ID / SECRET) are not configured.",
            )

        redirect = redirect_uri or settings.google_redirect_uri
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                token_resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": settings.google_client_id,
                        "client_secret": settings.google_client_secret,
                        "redirect_uri": redirect,
                        "grant_type": "authorization_code",
                    },
                )
                if token_resp.status_code != 200:
                    logger.error("auth.google.exchange_error", body=token_resp.text)
                    raise AuthError(
                        ErrorCode.AUTH_GOOGLE_FAILED,
                        "Failed to exchange Google authorization code.",
                    )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")

                # Fetch user info using Google access token
                userinfo_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if userinfo_resp.status_code != 200:
                    raise AuthError(
                        ErrorCode.AUTH_GOOGLE_FAILED,
                        "Failed to retrieve user profile from Google.",
                    )
                info = userinfo_resp.json()
        except httpx.RequestError as exc:
            raise AuthError(
                ErrorCode.AUTH_GOOGLE_FAILED,
                f"Failed to communicate with Google authentication endpoint: {exc}",
            ) from exc

        return {
            "google_id": info.get("sub"),
            "email": info.get("email", "").strip().lower(),
            "name": info.get("name") or info.get("email", "").split("@")[0],
            "avatar_url": info.get("picture"),
        }

    async def _sync_google_user(self, profile: dict[str, Any]) -> TokenResponse:
        """Find or create a user from Google profile and issue tokens."""
        google_id = profile["google_id"]
        email = profile["email"]
        name = profile["name"]
        avatar_url = profile["avatar_url"]
        now = self._now_iso()

        # 1. Try to find user by google_id
        user = self.storage.get_by_google_id(google_id)

        # 2. Try to find user by email
        if user is None:
            user = self.storage.get_by_email(email)
            if user is not None:
                # Link existing email account to Google ID
                user.google_id = google_id
                if not user.avatar_url and avatar_url:
                    user.avatar_url = avatar_url
                user.updated_at = now
                user.last_login_at = now
                self.storage.update_user(user)
                logger.info("auth.google.linked_account", user_id=user.id, email=email)

        # 3. If still no user, create a new Google user
        if user is None:
            user = User(
                id=str(uuid4()),
                email=email,
                name=name,
                avatar_url=avatar_url,
                hashed_password=None,
                provider="google",
                google_id=google_id,
                role="user",
                is_active=True,
                created_at=now,
                updated_at=now,
                last_login_at=now,
            )
            self.storage.create_user(user)
            logger.info("auth.google.new_user_created", user_id=user.id, email=email)
        else:
            self.storage.update_last_login(user.id, now)
            user.last_login_at = now

        return self._build_token_response(user)

    async def refresh_token(self, req: RefreshTokenRequest) -> TokenResponse:
        """Generate a new access token from a valid refresh token."""
        payload = decode_token(req.refresh_token, expected_type="refresh")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthError(ErrorCode.AUTH_TOKEN_INVALID, "Invalid refresh token payload.")

        user = self.storage.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthError(
                ErrorCode.AUTH_UNAUTHORIZED,
                "User not found or account disabled.",
            )

        return self._build_token_response(user)

    async def update_profile(self, user_id: str, req: UpdateProfileRequest) -> UserResponse:
        """Update authenticated user's name or avatar URL."""
        user = self.storage.get_by_id(user_id)
        if user is None:
            raise AuthError(ErrorCode.AUTH_USER_NOT_FOUND, "User not found.")

        updated = False
        if req.name is not None and req.name.strip():
            user.name = req.name.strip()
            updated = True
        if req.avatar_url is not None:
            user.avatar_url = req.avatar_url.strip() or None
            updated = True

        if updated:
            user.updated_at = self._now_iso()
            self.storage.update_user(user)

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            avatar_url=user.avatar_url,
            provider=user.provider,
            role=user.role,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )

    async def change_password(self, user_id: str, req: ChangePasswordRequest) -> None:
        """Change password for an existing local account."""
        user = self.storage.get_by_id(user_id)
        if user is None:
            raise AuthError(ErrorCode.AUTH_USER_NOT_FOUND, "User not found.")

        if not user.hashed_password:
            raise AuthError(
                ErrorCode.AUTH_INVALID_CREDENTIALS,
                "This account uses Google Sign-In and does not have a local password.",
            )

        if not verify_password(req.current_password, user.hashed_password):
            raise AuthError(
                ErrorCode.AUTH_INVALID_CREDENTIALS,
                "Current password does not match.",
            )

        user.hashed_password = hash_password(req.new_password)
        user.updated_at = self._now_iso()
        self.storage.update_user(user)
        logger.info("auth.password_changed", user_id=user.id)


# Global singleton service
auth_service = AuthService()
