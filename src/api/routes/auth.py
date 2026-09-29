"""
CoreMind Backend — Authentication API Routes.

Endpoints:
- POST /v1/auth/register         — Create a new account with email & password
- POST /v1/auth/login            — Sign in with email & password
- POST /v1/auth/google           — Sign in / Sign up with Google (ID Token or Auth Code)
- GET  /v1/auth/google/url       — Get Google OAuth2 authorization consent URL
- GET  /v1/auth/google/callback  — OAuth callback handler for browser/IDE redirect
- GET  /v1/auth/me               — Get current authenticated user profile
- PATCH /v1/auth/profile         — Update user name and avatar
- POST /v1/auth/change-password  — Change account password
- POST /v1/auth/refresh          — Refresh access token using refresh token
- POST /v1/auth/logout           — Invalidate session
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse

from src.auth.dependencies import get_current_user
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
from src.auth.service import auth_service
from src.utils.logger import logger

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: UserRegisterRequest) -> TokenResponse:
    """Create a new user account with email and password."""
    logger.info("api.auth.register", email=req.email)
    return await auth_service.register(req)


@router.post("/login", response_model=TokenResponse)
async def login(req: UserLoginRequest) -> TokenResponse:
    """Sign in to an existing account with email and password."""
    logger.info("api.auth.login", email=req.email)
    return await auth_service.login(req)


@router.post("/google", response_model=TokenResponse)
async def google_auth(req: GoogleAuthRequest) -> TokenResponse:
    """
    Continue with Google.
    Accepts a Google ID token (from frontend/IDE Google button)
    or an OAuth authorization code.
    """
    logger.info("api.auth.google", has_id_token=bool(req.id_token), has_code=bool(req.code))
    return await auth_service.google_auth(req)


@router.get("/google/url", response_model=GoogleAuthUrlResponse)
async def get_google_auth_url(
    state: str | None = Query(default=None, description="Client state parameter"),
    redirect_uri: str | None = Query(default=None, description="Custom redirect URI"),
) -> GoogleAuthUrlResponse:
    """Retrieve the Google OAuth2 consent URL for browser or webview sign-in."""
    return auth_service.get_google_auth_url(state=state, redirect_uri=redirect_uri)


@router.get("/google/callback")
async def google_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> Any:
    """
    Handle Google OAuth callback redirect.
    Exchanges code for tokens and renders a success message with token for the client.
    """
    if error:
        logger.error("api.auth.google.callback_error", error=error)
        html = (
            "<!DOCTYPE html><html><head><title>Google Sign-In Error</title></head>"
            "<body style='background:#0a0a0f;color:#ff5555;font-family:sans-serif;"
            "text-align:center;padding:40px;'>"
            f"<h2>Authentication Failed</h2><p>{error}</p>"
            "<a href='/auth' style='color:#00ffaa;'>Back to Sign In</a></body></html>"
        )
        return HTMLResponse(html, status_code=400)

    if not code:
        return JSONResponse({"error": "No code provided by Google"}, status_code=400)

    try:
        token_response = await auth_service.google_auth(GoogleAuthRequest(code=code))
        token_json = token_response.model_dump_json()
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>CoreMind — Authenticated</title>
    <style>
        body {{
            background: #0d0f17; color: #f0f3f6;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex; align-items: center; justify-content: center;
            height: 100vh; margin: 0;
        }}
        .card {{
            background: #161b26; border: 1px solid #30363d; border-radius: 12px;
            padding: 32px; max-width: 420px; text-align: center;
            box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        }}
        .success-icon {{ font-size: 48px; color: #10b981; margin-bottom: 12px; }}
        .btn {{
            display: inline-block; margin-top: 20px; padding: 10px 24px;
            background: linear-gradient(135deg, #10b981, #06b6d4);
            color: #000; font-weight: 600; text-decoration: none; border-radius: 8px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="success-icon">✓</div>
        <h2>Welcome, {token_response.user.name}!</h2>
        <p>Google sign-in successful: <strong>{token_response.user.email}</strong></p>
        <p style="font-size:12px; color:#8b949e;">You may close this window or return.</p>
        <a class="btn" href="/auth">Open CoreMind Portal</a>
    </div>
    <script>
        if (window.opener) {{
            window.opener.postMessage({{
                type: 'COREMIND_AUTH_SUCCESS',
                token: {token_json}
            }}, '*');
        }}
        try {{
            localStorage.setItem('coremind_auth', JSON.stringify({token_json}));
        }} catch (e) {{}}
    </script>
</body>
</html>"""
        return HTMLResponse(html)
    except Exception as exc:
        logger.error("api.auth.google.callback_exchange_failed", error=str(exc))
        err_html = (
            "<!DOCTYPE html><html><head><title>Authentication Error</title></head>"
            "<body style='background:#0a0a0f;color:#ff5555;font-family:sans-serif;"
            "text-align:center;padding:40px;'>"
            f"<h2>Authentication Error</h2><p>{exc}</p>"
            "<a href='/auth' style='color:#00ffaa;'>Back to Sign In</a></body></html>"
        )
        return HTMLResponse(err_html, status_code=400)


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Get the currently authenticated user's profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        avatar_url=current_user.avatar_url,
        provider=current_user.provider,
        role=current_user.role,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    req: UpdateProfileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Update profile information (name, avatar) for current user."""
    return await auth_service.update_profile(current_user.id, req)


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    """Change the password for the current local account."""
    await auth_service.change_password(current_user.id, req)
    return {"status": "ok", "message": "Password changed successfully."}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshTokenRequest) -> TokenResponse:
    """Exchange a valid refresh token for a fresh access token."""
    return await auth_service.refresh_token(req)


@router.post("/logout")
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    """Logout current user and invalidate client credentials."""
    logger.info("api.auth.logout", user_id=current_user.id)
    return {"status": "ok", "message": "Successfully logged out."}
