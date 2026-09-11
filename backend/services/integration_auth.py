"""Opaque, revocable credentials used only by the MCP transport."""
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from config import db
from services.auth_security import hash_opaque_token


class IntegrationRequest(Request):
    """An internal request, constructed after MCP bearer authentication.

    This class is never constructed from an incoming browser/REST request.
    Existing API handlers can therefore keep their ownership and rate checks
    without accepting integration keys on account, billing, or admin routes.
    """

    def __init__(self, source: Request, user: dict):
        super().__init__({**source.scope, "headers": [
            (key, value) for key, value in source.scope.get("headers", [])
            if key not in {b"cookie", b"authorization", b"idempotency-key"}
        ]})
        self.integration_user = user


async def authenticate_key(request: Request):
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.startswith("rt_mcp_") or len(token) > 200:
        raise HTTPException(401, "A Roundtable integration key is required")
    key = await db.integration_keys.find_one({"token_hash": hash_opaque_token(token)})
    if not key:
        raise HTTPException(401, "Integration key is invalid or revoked")
    expiry = datetime.fromisoformat(str(key["expires_at"]))
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        raise HTTPException(401, "Integration key has expired")
    user = await db.users.find_one({"user_id": key["user_id"]})
    if not user or not user.get("email_verified"):
        raise HTTPException(401, "A verified account is required")
    return key, user
