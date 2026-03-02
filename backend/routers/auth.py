import uuid
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from config import db

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
