"""
CoreMind Backend — Authentication Package.

Supports email/password authentication, Google OAuth2 / ID token login,
JWT token issuing and validation, and user profile management.
"""

from src.auth.dependencies import (
    get_current_active_user,
    get_current_admin_user,
    get_current_user,
    get_optional_user,
)
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
from src.auth.service import AuthService, auth_service
from src.auth.storage import UserStorage, user_storage

__all__ = [
    "AuthService",
    "ChangePasswordRequest",
    "GoogleAuthRequest",
    "GoogleAuthUrlResponse",
    "RefreshTokenRequest",
    "TokenResponse",
    "UpdateProfileRequest",
    "User",
    "UserLoginRequest",
    "UserRegisterRequest",
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
    "hash_password",
    "user_storage",
    "verify_password",
]
