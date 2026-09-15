"""Authenticated API for enqueueing and reconnecting to durable AI jobs."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

import config as cfg
from config import db
from routers.auth import _get_session_user
from services.ai_jobs import enqueue_ai_job, public_job, reading_idempotency_key
from services.cost_control import preflight_estimate
from services.rate_limit import enforce_rate_limit

jobs_router = APIRouter(prefix="/api")


async def _owned(manuscript_id: str, request: Request):
    user = await _get_session_user(request)
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")
    if manuscript.get("user_id") != user.get("user_id"):
        raise HTTPException(403, "You do not have access to this manuscript")
    return user, manuscript


async def _limit_enqueue(request: Request, user_id: str):
    await enforce_rate_limit(
        request, "ai_account", cfg.AI_ACCOUNT_RATE_PER_HOUR, 3600,
        identity=f"user:{user_id}",
    )
    await enforce_rate_limit(request, "ai_ip", cfg.AI_IP_RATE_PER_HOUR, 3600)


def _reader_ids(value: Optional[str]) -> List[str]:
    return sorted({item.strip() for item in (value or "").split(",") if item.strip()})


@jobs_router.post("/manuscripts/{manuscript_id}/jobs/reading")
async def enqueue_reading(
    manuscript_id: str, request: Request,
    reader_ids: Optional[str] = Query(None, description="Comma-separated selected reader IDs"),
    retry: bool = Query(False, description="Explicitly retry a terminal job"),
):
    if not cfg.AI_JOBS_ENABLED:
        raise HTTPException(503, "Durable AI jobs are not enabled until the worker is ready")
    user, manuscript = await _owned(manuscript_id, request)
    selected = _reader_ids(reader_ids)
    available = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if not available:
        raise HTTPException(400, "No readers found. Generate readers first.")
    available_ids = {reader.get("id") for reader in available}
    if selected and not set(selected).issubset(available_ids):
        raise HTTPException(400, "One or more selected readers are invalid")
    if not selected:
        selected = sorted(available_ids)
    estimate = await preflight_estimate(
        manuscript, [reader for reader in available if reader.get("id") in set(selected)], "readers"
    )
    if not estimate.get("can_start"):
        raise HTTPException(402, {"code": "budget_insufficient", "estimate": estimate})
    await _limit_enqueue(request, user["user_id"])
    key = request.headers.get("idempotency-key") or reading_idempotency_key(manuscript_id, selected)
    job = await enqueue_ai_job(
        user_id=user["user_id"], manuscript_id=manuscript_id, job_type="reading",
        idempotency_key=key, payload={"reader_ids": selected}, retry_failed=retry,
    )
    await db.manuscripts.update_one({"id": manuscript_id}, {"$set": {"reader_config_locked": True}})
    return JSONResponse(public_job(job), status_code=202)


@jobs_router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    user = await _get_session_user(request)
    job = await db.ai_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "AI job not found")
    if job.get("user_id") != user.get("user_id"):
        raise HTTPException(403, "You do not have access to this AI job")
    return public_job(job)


@jobs_router.get("/manuscripts/{manuscript_id}/jobs")
async def list_jobs(
    manuscript_id: str, request: Request,
    job_type: Optional[str] = Query(None, pattern="^(reading|editor_report|copy_edit)$"),
):
    user, _ = await _owned(manuscript_id, request)
    filters = {"manuscript_id": manuscript_id, "user_id": user["user_id"]}
    if job_type:
        filters["job_type"] = job_type
    rows = await db.ai_jobs.find(filters, {"_id": 0}).sort("created_at", -1).to_list(50)
    return [public_job(row) for row in rows]
