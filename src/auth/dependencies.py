"""
CoreMind Backend — FastAPI Authentication Dependencies.

Provides dependency injection for protecting endpoints via JWT Bearer tokens.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.models import User
from src.auth.security import decode_token
from src.auth.storage import user_storage
from src.config import settings
from src.utils.errors import AuthError, CoreMindError, ErrorCode

bearer_scheme = HTTPBearer(auto_error=False)


def resolve_user_from_token(token: str) -> User:
    """
    Validates an access token and returns the user it belongs to.
    Raises AuthError when the token or its user is not acceptable.
    """
    payload = decode_token(token, expected_type="access")
    user_id = payload.get("sub")
    if not user_id:
        raise AuthError(ErrorCode.AUTH_TOKEN_INVALID, "Invalid token claims.")

    user = user_storage.get_by_id(user_id)
    if user is None:
        raise AuthError(
            ErrorCode.AUTH_USER_NOT_FOUND,
            "User belonging to this token no longer exists.",
        )

    if not user.is_active:
        raise AuthError(
            ErrorCode.AUTH_FORBIDDEN,
            "User account has been disabled.",
        )

    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """
    Validate the Bearer token in the Authorization header.
    Returns the authenticated User model.
    """
    if credentials is None:
        raise AuthError(
            ErrorCode.AUTH_UNAUTHORIZED,
            "Missing Authorization Bearer token header.",
        )
    return resolve_user_from_token(credentials.credentials)


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency that guarantees the user is active."""
    return current_user


async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency that guarantees the user has the admin role."""
    if current_user.role != "admin":
        raise AuthError(
            ErrorCode.AUTH_FORBIDDEN,
            "Administrator privileges required for this action.",
        )
    return current_user


async def require_direct_execution() -> None:
    """Refuses direct command execution endpoints unless DIRECT_EXECUTION_ENABLED is set."""
    if not settings.direct_execution_enabled:
        raise CoreMindError(
            ErrorCode.TOOL_PERMISSION_DENIED,
            "Direct command execution is disabled on this backend. Set DIRECT_EXECUTION_ENABLED=true to enable it.",
            status_code=403,
        )


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User | None:
    """
    Optionally authenticate a user. Returns None if unauthenticated
    or invalid, without raising an error.
    """
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id = payload.get("sub")
        if not user_id:
            return None
        return user_storage.get_by_id(user_id)
    except Exception:
        return None
