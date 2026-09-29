"""
CoreMind Backend — Google Authentication Package.

Supports Continue with Google (ID token and OAuth authorization code flows),
JWT token issuing/validation, and user profile management.
"""

from src.auth.dependencies import (
    get_current_active_user,
    get_current_admin_user,
    get_current_user,
    get_optional_user,
)
from src.auth.models import (
    GoogleAuthRequest,
    GoogleAuthUrlResponse,
    RefreshTokenRequest,
    TokenResponse,
    UpdateProfileRequest,
    User,
    UserResponse,
)
from src.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.auth.service import AuthService, auth_service
from src.auth.storage import UserStorage, user_storage

__all__ = [
    "AuthService",
    "GoogleAuthRequest",
    "GoogleAuthUrlResponse",
    "RefreshTokenRequest",
    "TokenResponse",
    "UpdateProfileRequest",
    "User",
    "UserResponse",
    "UserStorage",
    "auth_service",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_active_user",
    "get_current_admin_user",
    "get_current_user",
    "get_optional_user",
    "user_storage",
]
