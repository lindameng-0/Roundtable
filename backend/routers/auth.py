"""
Authentication router — native Google OAuth 2.0 (Authorization Code Flow).

Flow:
  1. GET  /api/auth/google/login    → redirect to Google consent screen
  2. GET  /api/auth/google/callback → exchange code, create session,
                                      redirect to frontend /auth/callback?session_token=…
  3. GET  /api/auth/me              → return current user (unchanged)
  4. POST /api/auth/logout          → delete session (unchanged)

# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
"""
import logging
import secrets
import urllib.parse
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from config import (
    db,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    FRONTEND_URL,
)

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth")

SESSION_DAYS = 7

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Short-lived CSRF state tokens: {state: expiry_datetime}
# (In a multi-process/multi-instance setup, replace with a shared store.)
_oauth_states: dict = {}


# ─── Diagnostics (no secrets) ─────────────────────────────────────────────────

@auth_router.get("/oauth-status")
async def oauth_status():
    """
    Report whether Google OAuth env vars are present. Use this to verify
    Railway (or local) env is loaded. Does not expose any secret values.
    """
    return {
        "google_oauth_configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        "redirect_uri_set": bool(GOOGLE_REDIRECT_URI),
        "frontend_url_set": bool(FRONTEND_URL),
    }


# ─── Shared session helper ────────────────────────────────────────────────────

async def _get_session_user(request: Request) -> dict:
    """
    Read session_token from cookie or Authorization header,
    validate it against the DB, and return the user dict.
    Raises HTTP 401 if not authenticated or session is expired.
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


# ─── Google OAuth routes ──────────────────────────────────────────────────────

@auth_router.get("/google/login")
async def google_login():
    """
    Redirect the browser to Google's OAuth consent screen.
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(500, "Google OAuth credentials are not configured on the server.")

    # Generate a random state token for CSRF protection
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = datetime.now(timezone.utc) + timedelta(minutes=10)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    google_url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return RedirectResponse(url=google_url, status_code=302)


@auth_router.get("/google/callback")
async def google_callback(
    code: str = None,
    state: str = None,
    error: str = None,
):
    """
    Handle the redirect from Google after user authentication.
    Exchange the authorization code for tokens, fetch the user profile,
    create (or update) the user record, store a session, then redirect
    the browser to the frontend with the session_token in the query string.
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    """
    # User denied access or Google returned an error
    if error:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error={urllib.parse.quote(error)}",
            status_code=302,
        )

    if not code:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=missing_code",
            status_code=302,
        )

    # Validate CSRF state
    if state:
        expiry = _oauth_states.pop(state, None)
        if expiry is None or datetime.now(timezone.utc) > expiry:
            logger.warning("OAuth state invalid or expired: %s", state)
            return RedirectResponse(
                url=f"{FRONTEND_URL}/login?error=invalid_state",
                status_code=302,
            )

    try:
        # ── Step 1: Exchange authorization code for tokens ─────────────────
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if token_resp.status_code != 200:
            logger.error("Token exchange failed (%s): %s", token_resp.status_code, token_resp.text)
            return RedirectResponse(
                url=f"{FRONTEND_URL}/login?error=token_exchange_failed",
                status_code=302,
            )

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("No access_token in Google response")

        # ── Step 2: Fetch Google user profile ──────────────────────────────
        async with httpx.AsyncClient(timeout=15.0) as client:
            profile_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if profile_resp.status_code != 200:
            logger.error("Userinfo failed (%s): %s", profile_resp.status_code, profile_resp.text)
            return RedirectResponse(
                url=f"{FRONTEND_URL}/login?error=userinfo_failed",
                status_code=302,
            )

        profile = profile_resp.json()
        email = profile.get("email")
        name = profile.get("name", email or "User")
        picture = profile.get("picture", "")

        if not email:
            raise ValueError("Google did not return an email address")

        # ── Step 3: Upsert user in DB ──────────────────────────────────────
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        if existing:
            user_id = existing["user_id"]
            await db.users.update_one(
                {"email": email},
                {"$set": {"name": name, "picture": picture}},
            )
        else:
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            await db.users.insert_one({
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        # ── Step 4: Create a new session ───────────────────────────────────
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # ── Step 5: Redirect browser to frontend with session token ────────
        # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
        frontend_callback_url = (
            f"{FRONTEND_URL}/auth/callback"
            f"?session_token={urllib.parse.quote(session_token)}"
        )
        redirect = RedirectResponse(url=frontend_callback_url, status_code=302)
        redirect.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=SESSION_DAYS * 24 * 3600,
            path="/",
        )
        return redirect

    except Exception as exc:
        logger.exception("Unexpected error during Google OAuth callback: %s", exc)
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=auth_failed",
            status_code=302,
        )


# ─── Session & user routes (unchanged) ───────────────────────────────────────

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
