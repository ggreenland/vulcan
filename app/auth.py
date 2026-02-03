import secrets
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
import httpx
from itsdangerous import URLSafeSerializer

from app.config import config
from app import database

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

serializer = URLSafeSerializer(config.SECRET_KEY)


def create_oauth_state() -> str:
    """Create a signed state parameter for CSRF protection."""
    return serializer.dumps({"nonce": secrets.token_urlsafe(16)})


def verify_oauth_state(state: str) -> bool:
    """Verify the OAuth state parameter."""
    try:
        serializer.loads(state)
        return True
    except Exception:
        return False


def get_google_auth_url(state: str) -> str:
    """Generate Google OAuth authorization URL."""
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": f"{config.BASE_URL}/auth/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}"


async def exchange_code_for_token(code: str) -> dict:
    """Exchange authorization code for access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": f"{config.BASE_URL}/auth/callback",
            },
        )
        response.raise_for_status()
        return response.json()


async def get_google_user_info(access_token: str) -> dict:
    """Get user info from Google."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


def set_session_cookie(response: RedirectResponse, session_id: str):
    """Set the session cookie on a response."""
    signed_session = serializer.dumps(session_id)
    response.set_cookie(
        key="session",
        value=signed_session,
        httponly=True,
        secure=config.BASE_URL.startswith("https"),
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )


def get_session_id_from_cookie(request: Request) -> Optional[str]:
    """Extract and verify session ID from cookie."""
    cookie = request.cookies.get("session")
    if not cookie:
        return None
    try:
        return serializer.loads(cookie)
    except Exception:
        return None


async def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from session cookie."""
    session_id = get_session_id_from_cookie(request)
    if not session_id:
        return None

    session = await database.get_session(session_id)
    if not session:
        return None

    return {
        "user_id": session["user_id"],
        "email": session["email"],
        "name": session["name"],
        "picture": session["picture"],
    }


async def get_current_user_or_api_key(request: Request) -> Optional[dict]:
    """Get current user from session or API key."""
    # First try session
    user = await get_current_user(request)
    if user:
        return user

    # Then try API key (only if enabled)
    if config.ENABLE_API_KEYS:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            key_info = await database.validate_api_key(api_key)
            if key_info:
                return {
                    "user_id": key_info["user_id"],
                    "email": key_info["email"],
                    "name": key_info["name"],
                    "via_api_key": True,
                }

    return None


async def require_auth(request: Request) -> dict:
    """Dependency that requires authentication."""
    user = await get_current_user_or_api_key(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_session(request: Request) -> dict:
    """Dependency that requires session authentication (not API key)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
