"""
CoreMind Backend — Google Authentication API Routes.

Endpoints:
- POST /v1/auth/google           — Sign in / Sign up with Google (ID Token or Auth Code)
- GET  /v1/auth/google/url       — Get Google OAuth2 authorization consent URL
- GET  /v1/auth/google/callback  — OAuth callback handler for browser/IDE redirect
- GET  /v1/auth/me               — Get current authenticated user profile
- PATCH /v1/auth/profile         — Update user name and avatar
- POST /v1/auth/refresh          — Refresh access token using refresh token
- POST /v1/auth/logout           — Invalidate session
"""

from __future__ import annotations

from html import escape as html_escape
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse

from src.auth.dependencies import get_current_user, get_optional_user
from src.auth.models import (
    GoogleAuthRequest,
    GoogleAuthUrlResponse,
    RefreshTokenRequest,
    TokenResponse,
    UpdateProfileRequest,
    User,
    UserResponse,
)
from src.auth.service import auth_service
from src.utils.logger import logger

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class OAuthSessionCache:
    """Thread-safe TTL cache for pending OAuth sessions (5-10 minutes validity)."""

    def __init__(self, default_ttl_seconds: int = 600) -> None:
        self._default_ttl = default_ttl_seconds
        self._lock = threading.Lock()
        self._store: dict[str, tuple[dict[str, Any], float]] = {}

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expire_at = time.time() + ttl
        with self._lock:
            self._cleanup_expired()
            self._store[key] = (value, expire_at)

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            self._cleanup_expired()
            entry = self._store.get(key)
            if entry is None:
                return None
            val, expire_at = entry
            if time.time() > expire_at:
                del self._store[key]
                return None
            return val

    def pop(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            self._cleanup_expired()
            entry = self._store.pop(key, None)
            if entry is None:
                return None
            val, expire_at = entry
            if time.time() > expire_at:
                return None
            return val

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]


oauth_session_store = OAuthSessionCache()
# States issued by /v1/auth/google/url. A callback completes a sign-in only for a state issued here, once.
oauth_pending_states = OAuthSessionCache()


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
    result = auth_service.get_google_auth_url(state=state, redirect_uri=redirect_uri)
    oauth_pending_states.set(result.state, {"issued": True}, ttl_seconds=600)
    return result


def _callback_error_page(message: str) -> str:
    return (
        "<!DOCTYPE html><html><head><title>Authentication Error</title></head>"
        "<body style='background:#0F172A;color:#EF4444;font-family:sans-serif;"
        "display:flex;align-items:center;justify-content:center;height:100vh;margin:0;'>"
        "<div style='text-align:center;background:#1E293B;padding:40px;border-radius:16px;border:1px solid #334155;'>"
        f"<h2 style='color:#EF4444;margin-bottom:8px;'>Authentication Error</h2><p style='color:#94A3B8;'>{html_escape(message)}</p>"
        "<a href='/auth' style='color:#3B82F6;'>Return to Sign In</a></div></body></html>"
    )


@router.get("/google/callback")
async def google_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> Any:
    """
    Handle Google OAuth callback redirect after Chrome sign-in.
    Exchanges code for tokens, persists profile/avatar, caches session for desktop polling,
    and returns a clean confirmation page.
    """
    if error:
        logger.error("api.auth.google.callback_error", error=error)
        html = (
            "<!DOCTYPE html><html><head><title>Google Sign-In Error</title></head>"
            "<body style='background:#0F172A;color:#EF4444;font-family:sans-serif;"
            "display:flex;align-items:center;justify-content:center;height:100vh;margin:0;'>"
            "<div style='text-align:center;background:#1E293B;padding:40px;border-radius:16px;border:1px solid #334155;'>"
            f"<h2 style='color:#EF4444;margin-bottom:8px;'>Authentication Failed</h2><p style='color:#94A3B8;'>{html_escape(error)}</p>"
            "<a href='/auth' style='color:#3B82F6;'>Return to Sign In</a></div></body></html>"
        )
        return HTMLResponse(html, status_code=400)

    if not code:
        return JSONResponse({"error": "No authorization code provided by Google"}, status_code=400)

    # Only a state this backend issued, and has not used yet, may complete a sign-in.
    if not state or oauth_pending_states.pop(state) is None:
        return HTMLResponse(
            _callback_error_page("This sign-in link has expired or was not started by CoreMind."),
            status_code=400,
        )

    try:
        token_response = await auth_service.google_auth(GoogleAuthRequest(code=code))
        token_dict = token_response.model_dump()

        # Held for 10 minutes and handed out once to the client that knows this state (see get_session).
        oauth_session_store.set(state, token_dict, ttl_seconds=600)
        # Copy for the sign-in portal at /auth. JSON-escaped so no value can close the script block.
        auth_js = (
            token_response.model_dump_json()
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )

        html = f"""<!DOCTYPE html>
<html>
  <head><title>CoreMind IDE — Sign-in Complete</title></head>
  <body style="font-family: sans-serif; background: #0F172A; color: #F8FAFC; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
    <div style="text-align: center; background: #1E293B; padding: 40px; border-radius: 16px; border: 1px solid #334155; max-width: 440px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);">
      <h2 style="color: #3B82F6; margin-bottom: 8px;">Authentication Successful</h2>
      <p style="color: #94A3B8;">You can now close this tab and return to CoreMind IDE.</p>
    </div>
    <script>
      if (window.opener) {{
        try {{
          // No token here. Desktop clients fetch it from /v1/auth/session with their state value.
          window.opener.postMessage({{ type: 'COREMIND_AUTH_SUCCESS' }}, '*');
        }} catch (e) {{}}
      }}
      try {{
        localStorage.setItem('coremind_auth', JSON.stringify({auth_js}));
      }} catch (e) {{}}
    </script>
  </body>
</html>"""
        return HTMLResponse(html)
    except Exception as exc:
        logger.error("api.auth.google.callback_exchange_failed", error=str(exc))
        err_html = (
            "<!DOCTYPE html><html><head><title>Authentication Error</title></head>"
            "<body style='background:#0F172A;color:#EF4444;font-family:sans-serif;"
            "display:flex;align-items:center;justify-content:center;height:100vh;margin:0;'>"
            "<div style='text-align:center;background:#1E293B;padding:40px;border-radius:16px;border:1px solid #334155;'>"
            f"<h2 style='color:#EF4444;margin-bottom:8px;'>Authentication Error</h2><p style='color:#94A3B8;'>{html_escape(str(exc))}</p>"
            "<a href='/auth' style='color:#3B82F6;'>Return to Sign In</a></div></body></html>"
        )
        return HTMLResponse(err_html, status_code=400)


@router.get("/session", response_model=TokenResponse)
async def get_session(state: str | None = Query(default=None)) -> Any:
    """
    Desktop polling endpoint to check if Google sign-in finished in Chrome.
    Returns AuthTokens schema if authenticated, or 404 pending status.
    """
    if not state:
        return JSONResponse(
            {"error": {"code": "AUTH_UNAUTHORIZED", "message": "A state value from /v1/auth/google/url is required."}},
            status_code=400,
        )
    # Tokens are handed out once, to the client that holds the state value. There is no "latest" fallback.
    session_data = oauth_session_store.pop(state)
    if session_data:
        return TokenResponse(**session_data)
    return JSONResponse({"status": "pending"}, status_code=404)


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Get the currently authenticated Google user's profile."""
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


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshTokenRequest) -> TokenResponse:
    """Exchange a valid refresh token for a fresh access token."""
    return await auth_service.refresh_token(req)


@router.post("/logout")
async def logout(
    current_user: Annotated[User | None, Depends(get_optional_user)] = None,
) -> dict[str, str]:
    """Logout current user and invalidate client credentials."""
    if current_user:
        logger.info("api.auth.logout", user_id=current_user.id)
    return {"status": "ok", "message": "Successfully logged out"}
