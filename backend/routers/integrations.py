"""Browser-only management of personal MCP keys. Plaintext is shown once."""
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from config import db
from routers.auth import _get_session_user
from services.auth_security import hash_opaque_token
from services.rate_limit import enforce_rate_limit

integrations_router = APIRouter(prefix="/api/integrations", tags=["integrations"])
PUBLIC_FIELDS = ("id", "name", "permission", "prefix", "created_at", "expires_at")


class KeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    permission: Literal["read", "run"] = "read"
    expires_in_days: Literal[7, 30, 90] = 30


async def _account(request: Request, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    origins = os.environ.get("CORS_ORIGINS", "https://roundtable.works,http://localhost:3000,http://127.0.0.1:3000")
    if request.headers.get("origin") not in {v.strip() for v in origins.split(",")}:
        raise HTTPException(403, "Origin not allowed")
    user = await _get_session_user(request)
    if not user.get("email_verified"):
        raise HTTPException(403, "Verify your email before connecting an assistant")
    await enforce_rate_limit(request, "integration_management", 30, 60, identity=user["user_id"])
    return user


@integrations_router.get("/keys")
async def list_keys(request: Request, response: Response):
    user = await _account(request, response)
    rows = await db.integration_keys.find({"user_id": user["user_id"]}).sort("created_at", -1).to_list(100)
    return [{field: row.get(field) for field in PUBLIC_FIELDS} for row in rows]


@integrations_router.post("/keys", status_code=201)
async def create_key(body: KeyCreate, request: Request, response: Response):
    user = await _account(request, response)
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Give this connection a name")
    await enforce_rate_limit(request, "integration_key_create", 10, 3600, identity=user["user_id"])
    rows = await db.integration_keys.find({"user_id": user["user_id"]}).to_list(100)
    if len(rows) >= 20:
        raise HTTPException(409, "Revoke an old key before creating another")
    token = "rt_mcp_" + secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    row = {"id": str(uuid.uuid4()), "user_id": user["user_id"], "name": name,
           "permission": body.permission, "token_hash": hash_opaque_token(token),
           "prefix": token[:13], "created_at": now.isoformat(),
           "expires_at": (now + timedelta(days=body.expires_in_days)).isoformat()}
    await db.integration_keys.insert_one(row)
    return {**{field: row[field] for field in PUBLIC_FIELDS}, "key": token}


@integrations_router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(key_id: str, request: Request, response: Response):
    user = await _account(request, response)
    await db.integration_keys.delete_many({"id": key_id, "user_id": user["user_id"]})
