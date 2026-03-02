import uuid
import secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from config import db
import config as _cfg

auth_router = APIRouter(prefix="/api/auth")

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
SESSION_DAYS = 7


async def _get_session_user(request: Request) -> dict:
    """
    Shared helper: read session_token from cookie or Authorization header,
    validate it, and return the user dict.  Raises 401 if not authenticated.
    """
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            session_token = auth[7:]
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ─── Routes ───────────────────────────────────────────────────────────────────

# Google OAuth (redirect flow). In Google Cloud Console: create OAuth 2.0 Client ID (Web application),
# add authorized redirect URI: {BACKEND_URL}/api/auth/google/callback (e.g. http://localhost:8000/api/auth/google/callback).
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@auth_router.get("/google")
async def google_oauth_start(request: Request):
    """Redirect user to Google sign-in. After auth, Google redirects to /api/auth/google/callback."""
    client_id = _cfg.GOOGLE_CLIENT_ID
    if not client_id or client_id.strip() in ("", "your-google-client-id"):
        raise HTTPException(
            503,
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env with credentials from https://console.cloud.google.com/apis/credentials (create OAuth 2.0 Client ID, type Web application, add redirect URI: {}/api/auth/google/callback)".format(_cfg.BACKEND_URL),
        )
    state = secrets.token_urlsafe(32)
    # Store state in cookie so we can verify it in callback (optional but recommended for CSRF)
    redirect_uri = f"{_cfg.BACKEND_URL}/api/auth/google/callback"
    params = {
        "client_id": _cfg.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    url = f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"
    response = RedirectResponse(url=url)
    response.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax", path="/api/auth")
    return response


@auth_router.get("/google/callback")
async def google_oauth_callback(request: Request, response: Response, code: str = "", state: str = ""):
    """Exchange code for tokens, get user info, create session, redirect to frontend."""
    if not code:
        return RedirectResponse(f"{_cfg.FRONTEND_URL}/login?error=missing_code")
    # Optional: verify state cookie to prevent CSRF (state in URL must match cookie)
    stored_state = request.cookies.get("oauth_state")
    if stored_state and state != stored_state:
        return RedirectResponse(f"{_cfg.FRONTEND_URL}/login?error=invalid_state")
    redirect_uri = f"{_cfg.BACKEND_URL}/api/auth/google/callback"
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": _cfg.GOOGLE_CLIENT_ID,
                "client_secret": _cfg.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if token_resp.status_code != 200:
        return RedirectResponse(f"{_cfg.FRONTEND_URL}/login?error=token_exchange_failed")
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(f"{_cfg.FRONTEND_URL}/login?error=no_access_token")
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if user_resp.status_code != 200:
        return RedirectResponse(f"{_cfg.FRONTEND_URL}/login?error=userinfo_failed")
    user_info = user_resp.json()
    email = (user_info.get("email") or "").strip()
    name = (user_info.get("name") or email or "User").strip()
    picture = (user_info.get("picture") or "").strip()
    if not email:
        return RedirectResponse(f"{_cfg.FRONTEND_URL}/login?error=no_email")
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"email": email}, {"$set": {"name": name, "picture": picture}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    redirect_response = RedirectResponse(url=f"{_cfg.FRONTEND_URL}/setup")
    redirect_response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )
    redirect_response.delete_cookie("oauth_state", path="/api/auth")
    return redirect_response


@auth_router.post("/session")
async def create_session(request: Request, response: Response):
    """Exchange a one-time session_id from Emergent OAuth for a persistent session."""
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(400, "session_id required")

    async with httpx.AsyncClient() as client:
        resp = await client.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": session_id})
    if resp.status_code != 200:
        raise HTTPException(401, "Invalid or expired session_id")

    data = resp.json()
    email = data["email"]
    name = data["name"]
    picture = data.get("picture", "")
    session_token = data["session_token"]

    # Find or create user (by email)
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"email": email}, {"$set": {"name": name, "picture": picture}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # Store session
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )

    return {
        "user": {"user_id": user_id, "email": email, "name": name, "picture": picture},
        "session_token": session_token,
    }


@auth_router.get("/me")
async def get_me(request: Request):
    """Return the current authenticated user."""
    user = await _get_session_user(request)
    return user


@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    """Clear the session cookie and delete the server-side session."""
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/", samesite="none", secure=True)
    return {"message": "Logged out"}
