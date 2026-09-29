"""
CoreMind Backend — JWT Security and Token Utilities.

Provides secure signed JWT access and refresh token issuing and decoding via pyjwt.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from src.config import settings
from src.utils.errors import AuthError, ErrorCode


def create_access_token(
    user_id: str,
    email: str,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """
    Generate a signed JWT access token.
    Returns (token_string, expires_in_seconds).
    """
    now = datetime.now(UTC)
    delta = expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expire = now + delta

    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    expires_in = int(delta.total_seconds())
    return token, expires_in


def create_refresh_token(
    user_id: str,
    email: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Generate a signed JWT refresh token."""
    now = datetime.now(UTC)
    delta = expires_delta or timedelta(days=settings.jwt_refresh_token_expire_days)
    expire = now + delta

    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "refresh",
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """
    Decode and validate a JWT token.
    Raises AuthError on expiration or invalid signature.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError(
            ErrorCode.AUTH_TOKEN_EXPIRED,
            "Authentication token has expired. Please sign in again.",
        ) from exc
    except jwt.PyJWTError as exc:
        raise AuthError(
            ErrorCode.AUTH_TOKEN_INVALID,
            f"Invalid authentication token: {exc}",
        ) from exc

    token_type = payload.get("type")
    if token_type != expected_type:
        raise AuthError(
            ErrorCode.AUTH_TOKEN_INVALID,
            f"Expected {expected_type} token, but got {token_type}",
        )

    return payload
