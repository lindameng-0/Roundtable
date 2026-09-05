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
from pydantic import BaseModel, field_validator

from config import (
    db,
    EMAIL_VERIFICATION_TTL_MINUTES,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    FRONTEND_URL,
)
from services.auth_email import send_verification_email
from services.auth_security import (
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    normalize_email,
    validate_password,
    verify_password,
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


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        normalized = " ".join((value or "").split())
        if len(normalized) < 2 or len(normalized) > 80:
            raise ValueError("Name must be between 2 and 80 characters")
        return normalized

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: str) -> str:
        return validate_password(value)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return normalize_email(value)


class VerificationRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return normalize_email(value)


def _as_utc(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _public_user(user: dict) -> dict:
    allowed = {"user_id", "email", "name", "picture", "email_verified", "auth_provider", "created_at"}
    return {key: value for key, value in user.items() if key in allowed}


async def _create_session(user_id: str, response: Response) -> str:
    session_token = secrets.token_urlsafe(32)
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
    return session_token


async def _issue_verification(user: dict) -> None:
    raw_token, token_hash = new_opaque_token()
    now = datetime.now(timezone.utc)
    await db.email_verification_tokens.delete_many({"user_id": user["user_id"]})
    await db.email_verification_tokens.insert_one({
        "user_id": user["user_id"],
        "token_hash": token_hash,
        "expires_at": (now + timedelta(minutes=EMAIL_VERIFICATION_TTL_MINUTES)).isoformat(),
        "used_at": None,
        "created_at": now.isoformat(),
    })
    await send_verification_email(user["email"], user.get("name") or "writer", raw_token)


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

# Email/password routes

@auth_router.post("/signup", status_code=202)
async def signup(body: SignupRequest):
    """Create an unverified password account and email a one-time link."""
    existing = await db.users.find_one({"email": body.email}, {"_id": 0})
    if existing and existing.get("email_verified"):
        # Deliberately avoid revealing whether an address already has an account.
        return {"message": "If this address can be registered, a verification email has been sent."}

    password_digest = hash_password(body.password)
    if existing:
        await db.users.update_one(
            {"user_id": existing["user_id"]},
            {"$set": {"name": body.name, "password_hash": password_digest, "auth_provider": "email"}},
        )
        user = {**existing, "name": body.name, "password_hash": password_digest, "auth_provider": "email"}
    else:
        user = {
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": body.email,
            "name": body.name,
            "picture": "",
            "password_hash": password_digest,
            "email_verified": False,
            "auth_provider": "email",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await db.users.insert_one(user)
        except Exception:
            logger.info("Concurrent or duplicate signup for %s", body.email)
            return {"message": "If this address can be registered, a verification email has been sent."}

    try:
        await _issue_verification(user)
    except RuntimeError as exc:
        logger.exception("Unable to send verification email")
        raise HTTPException(503, str(exc))
    return {"message": "Check your email to verify your Roundtable account."}


@auth_router.post("/verify-email")
async def verify_email(body: VerificationRequest):
    token_hash = hash_opaque_token((body.token or "").strip())
    record = await db.email_verification_tokens.find_one({"token_hash": token_hash}, {"_id": 0})
    if not record or record.get("used_at") or _as_utc(record["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(400, "This verification link is invalid or has expired")

    user = await db.users.find_one({"user_id": record["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(400, "This verification link is invalid or has expired")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"email_verified": True}})
    await db.email_verification_tokens.update_one(
        {"id": record["id"]},
        {"$set": {"used_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"message": "Email verified. You can now sign in."}


@auth_router.post("/resend-verification", status_code=202)
async def resend_verification(body: ResendVerificationRequest):
    user = await db.users.find_one({"email": body.email}, {"_id": 0})
    if user and user.get("password_hash") and not user.get("email_verified"):
        latest = await db.email_verification_tokens.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(1).to_list(1)
        if not latest or datetime.now(timezone.utc) - _as_utc(latest[0]["created_at"]) >= timedelta(seconds=60):
            try:
                await _issue_verification(user)
            except RuntimeError as exc:
                logger.exception("Unable to resend verification email")
                raise HTTPException(503, str(exc))
    return {"message": "If the account is awaiting verification, a new email has been sent."}


@auth_router.post("/login")
async def password_login(body: LoginRequest, response: Response):
    user = await db.users.find_one({"email": body.email}, {"_id": 0})
    password_digest = user.get("password_hash") if user else None
    if not password_digest or not verify_password(body.password, password_digest):
        raise HTTPException(401, "Invalid email or password")
    if not user.get("email_verified"):
        raise HTTPException(403, {"code": "email_not_verified", "message": "Verify your email before signing in."})

    session_token = await _create_session(user["user_id"], response)
    return {"user": _public_user(user), "session_token": session_token}


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

    # Validate CSRF state. A missing state is just as invalid as a mismatched one.
    expiry = _oauth_states.pop(state, None) if state else None
    if expiry is None or datetime.now(timezone.utc) > expiry:
        logger.warning("OAuth state missing, invalid, or expired")
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
        email = normalize_email(profile.get("email") or "")
        name = profile.get("name", email or "User")
        picture = profile.get("picture", "")

        if profile.get("verified_email") is False:
            raise ValueError("Google did not return a verified email address")

        # ── Step 3: Upsert user in DB ──────────────────────────────────────
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        if existing:
            user_id = existing["user_id"]
            provider = "email,google" if existing.get("password_hash") else "google"
            await db.users.update_one(
                {"email": email},
                {"$set": {"name": name, "picture": picture, "email_verified": True, "auth_provider": provider}},
            )
        else:
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            await db.users.insert_one({
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "password_hash": None,
                "email_verified": True,
                "auth_provider": "google",
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
    return _public_user(user)


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
