import json
import uuid
import asyncio
import io
import logging
import zipfile
from pathlib import Path
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse

import config as _cfg
from config import db
from models import (
    ManuscriptCreate,
    ManuscriptResponse,
    ReaderPersonaResponse,
    ReaderFocusUpdate,
    RegenerateRequest,
    ModelConfigRequest,
    AppendTextRequest,
    WaitlistRequest,
    FeedbackRequest,
    BudgetUpdateRequest,
)
from utils import now_iso

from services.manuscript import split_manuscript
from services.personas import (
    READER_ARCHETYPES,
    DEFAULT_READER_COUNT,
    generate_single_persona,
    generate_all_personas,
    add_one_persona,
)
from services.readers import reader_pipeline
from services.editor import (
    generate_copy_edit_appendix as _build_copy_edit_appendix,
    generate_editor_report as _build_editor_report,
)
from services.workflow import ensure_task_ledger, update_task, workflow_status
from services.report_versions import append_report_version, list_report_versions
from services.cost_control import CostLimitExceeded, budget_status, preflight_estimate
from services.llm_gateway import structured_completion
from services.model_routing import route_for_role
from services.reader_focus import FOCUS_GROUPS
from services.rate_limit import enforce_rate_limit
from services.ai_jobs import enqueue_ai_job, public_job, reading_idempotency_key
from routers.auth import _get_session_user

api_router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

WORDS_LIMIT = 30_000
AVAILABLE_READER_MODELS = {
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
}
DEFAULT_READER_MODEL = "gemini-2.5-flash"


def _count_words(text: str) -> int:
    """Count words the same way the frontend does: split on whitespace, ignore empty."""
    return len(text.split()) if text else 0


async def _get_optional_user(request: Request):
    """Return current user or None if not authenticated."""
    try:
        return await _get_session_user(request)
    except HTTPException:
        return None


def _is_admin(email: str) -> bool:
    return email and (email.strip().lower() in [e.strip().lower() for e in getattr(_cfg, "ADMIN_EMAILS", [])])


async def _get_owned_manuscript(manuscript_id: str, request: Request) -> Dict[str, Any]:
    """Load a manuscript and enforce strict authenticated account ownership."""
    user = await _get_session_user(request)
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")
    if not manuscript.get("user_id") or user.get("user_id") != manuscript.get("user_id"):
        raise HTTPException(403, "You do not have access to this manuscript")
    return manuscript


async def _ensure_reader_config_unlocked(manuscript: Dict[str, Any]) -> None:
    """Reader configuration becomes permanently immutable when a reading run starts."""
    if manuscript.get("reader_config_locked"):
        raise HTTPException(409, "Reader focus is locked because this manuscript's reading run has started.")
    manuscript_id = manuscript["id"]
    # Backfill the permanent flag for runs created before this column existed.
    if (
        await db.reader_reactions.count_documents({"manuscript_id": manuscript_id})
        or await db.workflow_tasks.count_documents({"manuscript_id": manuscript_id})
    ):
        await db.manuscripts.update_one({"id": manuscript_id}, {"$set": {"reader_config_locked": True}})
        raise HTTPException(409, "Reader focus is locked because this manuscript's reading run has started.")


async def _limit_ai_operation(request: Request, manuscript: Dict[str, Any]) -> None:
    """Apply shared per-account and per-IP limits before any costly AI work."""
    owner_id = manuscript.get("user_id")
    await enforce_rate_limit(
        request, "ai_account", _cfg.AI_ACCOUNT_RATE_PER_HOUR, 3600,
        identity=f"user:{owner_id}",
    )
    await enforce_rate_limit(request, "ai_ip", _cfg.AI_IP_RATE_PER_HOUR, 3600)


def _selected_readers_complete(existing_reactions: List[Dict], readers: List[Dict]) -> bool:
    completed_reader_ids = {
        reaction.get("reader_id") for reaction in existing_reactions
        if reaction.get("reader_id")
    }
    selected_reader_ids = {reader.get("id") for reader in readers if reader.get("id")}
    return bool(selected_reader_ids) and selected_reader_ids.issubset(completed_reader_ids)


def _require_affordable(estimate: Dict) -> None:
    if not estimate.get("can_start"):
        budget = estimate.get("budget") or {}
        raise HTTPException(402, {
            "code": "budget_insufficient",
            "message": "The estimated cost is above this manuscript's remaining AI budget.",
            "estimate": estimate,
            "remaining_usd": budget.get("remaining_usd"),
        })


# ─── Root & Config ────────────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    return {
        "message": "Roundtable API",
        "database_backend": _cfg.DATABASE_BACKEND,
        "llm_backend": _cfg.LLM_BACKEND,
    }


@api_router.get("/health")
async def health():
    ping = getattr(db, "ping", None)
    database_ready = await ping() if ping else True
    if not database_ready:
        raise HTTPException(503, "Database is not ready")
    worker_count = getattr(db, "active_ai_workers", None)
    active_workers = await worker_count() if worker_count else 0
    return {
        "status": "ready",
        "database_backend": _cfg.DATABASE_BACKEND,
        "database_ready": True,
        "database_private_network": ".railway.internal" in (_cfg.DATABASE_URL or ""),
        "ai_jobs_enabled": _cfg.AI_JOBS_ENABLED,
        "ai_job_api_version": 2,
        "ai_worker_ready": active_workers > 0,
        "ai_worker_count": active_workers,
    }


@api_router.get("/config/models")
async def get_available_models():
    from services.model_routing import reader_routes, route_for_role
    routes = reader_routes()
    return {
        "current_provider": routes[0].provider,
        "current_model": routes[0].model,
        "scope": "manuscript_reader",
        "pipeline_version": _cfg.READER_PIPELINE_VERSION,
        "reader_pool": [{"provider": route.provider, "model": route.model} for route in routes],
        "memory_strategy": "state_delta_in_reader_call" if _cfg.READER_PIPELINE_VERSION == "v2" else "second_model_call",
        "editor_model": {
            "provider": route_for_role("editor").provider,
            "model": route_for_role("editor").model,
        },
        "editor_map_model": {
            "provider": route_for_role("editor_map").provider,
            "model": route_for_role("editor_map").model,
        },
        "reader_focus_options": FOCUS_GROUPS,
        "available": [
            {"provider": "gemini", "model": model, "label": label}
            for model, label in AVAILABLE_READER_MODELS.items()
        ],
    }


@api_router.post("/config/model")
async def update_model(req: ModelConfigRequest, request: Request):
    await _get_session_user(request)
    if req.provider != "gemini" or req.model not in AVAILABLE_READER_MODELS:
        raise HTTPException(400, "This reading pipeline currently supports Gemini 2.5 Flash or Pro")
    _cfg.LLM_MODEL = req.model
    _cfg.LLM_PROVIDER = "gemini"
    return {
        "provider": _cfg.LLM_PROVIDER,
        "model": _cfg.LLM_MODEL,
        "scope": "setup_generation_default",
        "note": "Set the reader model per manuscript when creating or updating it.",
    }


# ─── User usage (word-budget limit) ──────────────────────────────────────────

@api_router.get("/user/usage")
async def get_user_usage(request: Request):
    """
    Return cumulative word usage for the current user.
    Response: { words_used, words_limit, is_admin }
    Unauthenticated → words_used 0, words_limit WORDS_LIMIT, is_admin false.
    """
    user = await _get_optional_user(request)
    if not user:
        return {"words_used": 0, "words_limit": WORDS_LIMIT, "is_admin": False}
    email = (user.get("email") or "").strip()
    is_admin = _is_admin(email)
    words_used = 0
    if not is_admin:
        manuscripts = await db.manuscripts.find(
            {"user_id": user["user_id"]}, None
        ).to_list(1000)
        words_used = sum(
            _count_words(m.get("raw_text") or "")
            for m in manuscripts
        )
    return {
        "words_used": words_used,
        "words_limit": WORDS_LIMIT,
        "is_admin": is_admin,
        "email": email or None,
    }


# ─── Waitlist (when user hits manuscript limit) ─────────────────────────────────

@api_router.post("/waitlist")
async def join_waitlist(request: Request, body: WaitlistRequest):
    """Add email to waitlist. Optional auth to attach user_id."""
    email = (body.email or "").strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email required")
    user = await _get_optional_user(request)
    user_id = user.get("user_id") if user else None
    try:
        await db.waitlist.insert_one({
            "email": email,
            "user_id": user_id,
            "created_at": now_iso(),
        })
    except Exception as e:
        err_msg = str(getattr(e, "message", e)) if hasattr(e, "message") else str(e)
        if "23505" in err_msg or "duplicate" in err_msg.lower() or "unique" in err_msg.lower():
            pass  # already on waitlist, treat as success
        else:
            raise HTTPException(503, f"Database error: {str(e)}")
    return {"ok": True}


@api_router.get("/waitlist/status")
async def waitlist_status(request: Request):
    """Return { joined: true/false } for the current user (by email or user_id)."""
    user = await _get_optional_user(request)
    if not user:
        return {"joined": False}
    email = (user.get("email") or "").strip()
    user_id = user.get("user_id")
    if email:
        row = await db.waitlist.find_one({"email": email}, {"_id": 0})
        if row:
            return {"joined": True}
    if user_id:
        row = await db.waitlist.find_one({"user_id": user_id}, {"_id": 0})
        if row:
            return {"joined": True}
    return {"joined": False}


@api_router.post("/feedback")
async def submit_feedback(request: Request, body: FeedbackRequest):
    """Store free-text feedback from a limit-reached user."""
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(400, "Message is required")
    user = await _get_optional_user(request)
    user_id = user.get("user_id") if user else None
    await db.feedback.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "message": message,
        "created_at": now_iso(),
    })
    return {"ok": True}


# ─── Manuscripts ──────────────────────────────────────────────────────────────

@api_router.get("/manuscripts")
async def list_manuscripts(request: Request):
    """List all manuscripts for the current authenticated user."""
    user = await _get_session_user(request)
    docs = await db.manuscripts.find(
        {"user_id": user["user_id"]},
        None,
    ).sort("created_at", -1).to_list(100)
    # Strip heavy fields for list response (Supabase returns full row)
    for d in docs:
        d.pop("raw_text", None)
        d.pop("sections", None)
    return docs


@api_router.post("/manuscripts", response_model=ManuscriptResponse)
async def create_manuscript(manuscript: ManuscriptCreate, request: Request):
    raw_text = manuscript.raw_text.strip()
    if not raw_text:
        raise HTTPException(400, "Manuscript text cannot be empty")
    if len(raw_text.encode("utf-8")) > MAX_BODY_SIZE_BYTES:
        raise HTTPException(413, f"Manuscript exceeds the {_cfg.MAX_UPLOAD_MB} MB limit")

    # Every manuscript belongs to the authenticated account that creates it.
    user = await _get_session_user(request)
    user_id = user["user_id"]
    await enforce_rate_limit(
        request,
        "manuscript_create",
        _cfg.MANUSCRIPT_CREATE_RATE_PER_HOUR,
        3600,
        identity=f"user:{user_id}",
    )
    await enforce_rate_limit(
        request,
        "manuscript_create_ip",
        _cfg.MANUSCRIPT_CREATE_IP_RATE_PER_HOUR,
        3600,
    )

    # Usage limit: non-admin authenticated users get WORDS_LIMIT total words
    if user_id and user:
        if not _is_admin(user.get("email") or ""):
            manuscript_words = _count_words(raw_text)
            manuscripts = await db.manuscripts.find(
                {"user_id": user_id}, None
            ).to_list(1000)
            current_words_used = sum(
                _count_words(m.get("raw_text") or "")
                for m in manuscripts
            )
            words_remaining = max(0, WORDS_LIMIT - current_words_used)
            if current_words_used + manuscript_words > WORDS_LIMIT:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "limit_reached",
                        "words_used": current_words_used,
                        "words_limit": WORDS_LIMIT,
                        "words_remaining": words_remaining,
                        "manuscript_words": manuscript_words,
                    },
                )

    doc_id = str(uuid.uuid4())
    sections, total_lines = split_manuscript(raw_text)

    # Genre detection via LLM — fall back to defaults if key missing or API fails
    genre_data: Dict = {"genre": "Fiction", "target_audience": "General readers", "age_range": "Adult", "comparable_books": []}
    genre_detection_cost = 0.0
    try:
        if _cfg.MOCK_LLM:
            raise RuntimeError("mock LLM mode")
        genre_prompt = """You are a literary analyst. Analyze the manuscript excerpt and return ONLY a JSON object (no markdown) with:
{"genre":"primary genre","target_audience":"target reader description","age_range":"Adult/YA/Middle Grade/New Adult","comparable_books":["Book by Author","Book by Author","Book by Author"]}"""
        sample = raw_text[:3000]
        completion = await asyncio.wait_for(
            structured_completion(
                route=route_for_role("persona"), role="genre", system_prompt=genre_prompt,
                user_prompt=f"Analyze:\n\n{sample}", max_tokens=500,
            ),
            timeout=45.0,
        )
        genre_data = completion.data
        genre_detection_cost = float(completion.usage.estimated_cost_usd or 0)
    except asyncio.TimeoutError:
        logger.warning("Genre detection timed out after 45s, using defaults")
    except Exception as e:
        logger.warning("Genre detection failed, using defaults: %s", e)

    doc = {
        "id": doc_id,
        "title": manuscript.title or "Untitled Manuscript",
        "user_id": user_id,
        "raw_text": raw_text,
        "genre": genre_data.get("genre", "Fiction"),
        "target_audience": genre_data.get("target_audience", "General readers"),
        "age_range": genre_data.get("age_range", "Adult"),
        "comparable_books": genre_data.get("comparable_books", []),
        "model": manuscript.model if manuscript.model in AVAILABLE_READER_MODELS else DEFAULT_READER_MODEL,
        "sections": sections,
        "total_sections": len(sections),
        "total_lines": total_lines,
        "cost_limit_usd": manuscript.cost_limit_usd if manuscript.cost_limit_usd is not None else _cfg.MAX_WORKFLOW_COST_USD,
        "cost_spent_usd": genre_detection_cost,
        "cost_reserved_usd": 0,
        "reader_config_locked": False,
        "created_at": now_iso(),
    }
    try:
        inserted = await db.manuscripts.insert_one({**doc})
        if inserted:
            doc = inserted  # use DB-returned row so id (and any defaults) match
    except Exception as e:
        logger.exception("Failed to save manuscript to database")
        raise HTTPException(503, f"Database error: {str(e)}")
    return ManuscriptResponse(**doc)


@api_router.patch("/manuscripts/{manuscript_id}/append-text", response_model=ManuscriptResponse)
async def append_manuscript_text(manuscript_id: str, body: AppendTextRequest, request: Request):
    """Append text to an existing manuscript and re-run sectioning. Used for chunked uploads to avoid 413."""
    chunk = body.raw_text_chunk
    if not chunk:
        raise HTTPException(400, "raw_text_chunk cannot be empty")
    doc = await _get_owned_manuscript(manuscript_id, request)
    await _ensure_reader_config_unlocked(doc)
    new_raw = (doc.get("raw_text") or "") + chunk
    if len(new_raw.encode("utf-8")) > MAX_BODY_SIZE_BYTES:
        raise HTTPException(413, f"Manuscript exceeds the {_cfg.MAX_UPLOAD_MB} MB limit")
    sections, total_lines = split_manuscript(new_raw)
    update = {
        "raw_text": new_raw,
        "sections": sections,
        "total_sections": len(sections),
        "total_lines": total_lines,
    }
    await db.manuscripts.update_one({"id": manuscript_id}, {"$set": update})
    updated = await db.manuscripts.find_one({"id": manuscript_id}, None)
    return ManuscriptResponse(**updated)


MAX_BODY_SIZE_BYTES = _cfg.MAX_UPLOAD_MB * 1024 * 1024
MAX_DOCX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024


async def _read_bounded_upload(file) -> bytes:
    declared_size = getattr(file, "size", None)
    if declared_size is not None and declared_size > MAX_BODY_SIZE_BYTES:
        raise HTTPException(413, f"File exceeds the {_cfg.MAX_UPLOAD_MB} MB upload limit")
    content = await file.read(MAX_BODY_SIZE_BYTES + 1)
    if len(content) > MAX_BODY_SIZE_BYTES:
        raise HTTPException(413, f"File exceeds the {_cfg.MAX_UPLOAD_MB} MB upload limit")
    return content


@api_router.post("/manuscripts/upload")
async def upload_manuscript(request: Request):
    """Accept a bounded, signature-validated .txt, .docx, or .pdf manuscript."""
    # Authenticate before parsing or buffering a potentially large request body.
    await _get_session_user(request)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_SIZE_BYTES + 1024 * 1024:
                raise HTTPException(413, f"Request exceeds the {_cfg.MAX_UPLOAD_MB} MB upload limit")
        except ValueError:
            raise HTTPException(400, "Invalid Content-Length header")
    async with request.form(max_part_size=MAX_BODY_SIZE_BYTES) as form:
        file = form.get("file")
        if not file or not getattr(file, "filename", None):
            raise HTTPException(400, "No file provided")
        title = form.get("title") or "Untitled Manuscript"
        if isinstance(title, list):
            title = title[0] if title else "Untitled Manuscript"
        title = str(title).strip()[:200] or "Untitled Manuscript"
        filename = file.filename or ""
        extension = Path(filename).suffix.lower()
        content = await _read_bounded_upload(file)
        if extension == ".docx":
            try:
                from docx import Document
                if not content.startswith(b"PK\x03\x04"):
                    raise ValueError("file signature is not DOCX")
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    names = set(archive.namelist())
                    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                        raise ValueError("DOCX structure is invalid")
                    if len(names) > 10_000 or sum(item.file_size for item in archive.infolist()) > MAX_DOCX_UNCOMPRESSED_BYTES:
                        raise ValueError("DOCX expands beyond the safe processing limit")
                doc = Document(io.BytesIO(content))
                paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                raw_text = "\n\n".join(paragraphs)
            except Exception as e:
                raise HTTPException(400, f"Failed to read .docx file: {e}")
        elif extension == ".pdf":
            try:
                import fitz  # PyMuPDF
                if not content.startswith(b"%PDF-"):
                    raise ValueError("file signature is not PDF")
                doc = fitz.open(stream=content, filetype="pdf")
                parts = []
                for page in doc:
                    parts.append(page.get_text())
                doc.close()
                raw_text = "\n\n".join(p.strip() for p in parts if p.strip())
            except Exception as e:
                raise HTTPException(400, f"Failed to read .pdf file: {e}")
        elif extension == ".txt":
            if b"\x00" in content:
                raise HTTPException(400, "Text files cannot contain null bytes")
            raw_text = content.decode("utf-8-sig", errors="replace").strip()
        else:
            raise HTTPException(400, "Please upload a .txt, .docx, or .pdf file")

    if not raw_text:
        raise HTTPException(400, "File is empty")

    return await create_manuscript(
        ManuscriptCreate(title=title or filename or "Untitled Manuscript", raw_text=raw_text),
        request,
    )


@api_router.get("/manuscripts/{manuscript_id}", response_model=ManuscriptResponse)
async def get_manuscript(manuscript_id: str, request: Request):
    doc = await _get_owned_manuscript(manuscript_id, request)
    return ManuscriptResponse(**doc)


@api_router.patch("/manuscripts/{manuscript_id}/genre")
async def update_genre(manuscript_id: str, update: Dict[str, Any], request: Request):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    await _ensure_reader_config_unlocked(manuscript)
    allowed = {"genre", "target_audience", "age_range", "comparable_books", "model"}
    filtered = {k: v for k, v in update.items() if k in allowed}
    if "model" in filtered and filtered["model"] not in AVAILABLE_READER_MODELS:
        raise HTTPException(400, "Unsupported reader model")
    await db.manuscripts.update_one({"id": manuscript_id}, {"$set": filtered})
    return {"updated": filtered}


# ─── Reader Personas ──────────────────────────────────────────────────────────

@api_router.get("/manuscripts/{manuscript_id}/personas", response_model=List[ReaderPersonaResponse])
async def get_personas(manuscript_id: str, request: Request):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    personas = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if not personas:
        await _limit_ai_operation(request, manuscript)
        try:
            return await generate_all_personas(
                manuscript_id,
                manuscript.get("genre", "Fiction"),
                manuscript.get("target_audience", "General readers"),
                manuscript.get("age_range", "Adult"),
                count=DEFAULT_READER_COUNT,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Persona generation failed for manuscript %s", manuscript_id)
            msg = str(e).strip() or "LLM or database error"
            raise HTTPException(503, f"Reader generation failed: {msg}")

    def _normalize_persona(p: dict) -> dict:
        p = dict(p)
        name = (p.get("name") or "").strip() if isinstance(p.get("name"), str) else ""
        if not name:
            p["name"] = f"Reader {(p.get('avatar_index') or 0) + 1}"
        return p

    return [ReaderPersonaResponse(**_normalize_persona(p)) for p in personas]


@api_router.post("/manuscripts/{manuscript_id}/personas/regenerate")
async def regenerate_personas(manuscript_id: str, req: RegenerateRequest, request: Request):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    await _limit_ai_operation(request, manuscript)
    await _ensure_reader_config_unlocked(manuscript)
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")
    genre = manuscript.get("genre", "Fiction")
    audience = manuscript.get("target_audience", "General readers")
    age_range = manuscript.get("age_range", "Adult")

    if req.reader_id:
        existing = await db.reader_personas.find_one(
            {"id": req.reader_id, "manuscript_id": manuscript_id}, {"_id": 0}
        )
        if not existing:
            raise HTTPException(404, "Reader not found")
        avatar_index = existing.get("avatar_index", 0)
        archetype = READER_ARCHETYPES[avatar_index % len(READER_ARCHETYPES)]
        new_persona = await generate_single_persona(archetype, genre, audience, age_range, avatar_index, manuscript_id)
        new_persona["id"] = req.reader_id
        await db.reader_personas.replace_one({"id": req.reader_id}, {**new_persona})
        await db.reader_memories.delete_many({"reader_id": req.reader_id})
        await db.reader_reactions.delete_many({"reader_id": req.reader_id})
        await db.workflow_tasks.delete_many({"reader_id": req.reader_id})
        return ReaderPersonaResponse(**new_persona)
    else:
        await db.reader_memories.delete_many({"manuscript_id": manuscript_id})
        await db.reader_reactions.delete_many({"manuscript_id": manuscript_id})
        await db.workflow_tasks.delete_many({"manuscript_id": manuscript_id})
        existing_personas = await db.reader_personas.find({"manuscript_id": manuscript_id}).to_list(10)
        current_count = len(existing_personas)
        return await generate_all_personas(
            manuscript_id, genre, audience, age_range, count=min(current_count, len(READER_ARCHETYPES))
        )


@api_router.post("/manuscripts/{manuscript_id}/personas/add", response_model=ReaderPersonaResponse)
async def add_persona(manuscript_id: str, request: Request):
    """Add the next reader from the preset list (max 5)."""
    try:
        manuscript = await _get_owned_manuscript(manuscript_id, request)
        await _limit_ai_operation(request, manuscript)
        await _ensure_reader_config_unlocked(manuscript)
        return await add_one_persona(manuscript_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@api_router.patch("/manuscripts/{manuscript_id}/personas/{reader_id}/focus", response_model=ReaderPersonaResponse)
async def update_reader_focus(
    manuscript_id: str, reader_id: str, body: ReaderFocusUpdate, request: Request,
):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    await _ensure_reader_config_unlocked(manuscript)
    reader = await db.reader_personas.find_one({"id": reader_id, "manuscript_id": manuscript_id}, {"_id": 0})
    if not reader:
        raise HTTPException(404, "Reader not found")
    # Generated tastes may be dismissed, but this endpoint cannot invent new tastes.
    original_likes = set(reader.get("liked_tropes") or [])
    original_dislikes = set(reader.get("disliked_tropes") or [])
    if not set(body.liked_tropes).issubset(original_likes) or not set(body.disliked_tropes).issubset(original_dislikes):
        raise HTTPException(400, "Generated personal tastes may be removed but not rewritten.")
    values = {
        "primary_focus": body.primary_focus,
        "secondary_focuses": body.secondary_focuses,
        "writer_focus_note": body.writer_focus_note,
        "liked_tropes": body.liked_tropes,
        "disliked_tropes": body.disliked_tropes,
    }
    await db.reader_personas.update_one({"id": reader_id}, {"$set": values})
    return ReaderPersonaResponse(**{**reader, **values})


# ─── Reading: SSE Stream ──────────────────────────────────────────────────────

@api_router.get("/manuscripts/{manuscript_id}/read-all")
async def read_all_sections_stream(
    manuscript_id: str,
    request: Request,
    reader_ids: str | None = Query(None, description="Comma-separated reader IDs to use; if omitted, all readers are used"),
):
    """Legacy SSE facade; durable deployments keep processing after disconnect."""
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    if _cfg.AI_JOBS_ENABLED:
        await _limit_ai_operation(request, manuscript)
        all_readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
        selected_ids = {item.strip() for item in (reader_ids or "").split(",") if item.strip()}
        readers = [reader for reader in all_readers if not selected_ids or reader.get("id") in selected_ids]
        if selected_ids and {reader.get("id") for reader in readers} != selected_ids:
            raise HTTPException(400, "One or more selected readers are invalid")
        if not readers:
            raise HTTPException(400, "No readers found. Generate readers first.")
        initial_estimate = await preflight_estimate(manuscript, readers, "readers")
        _require_affordable(initial_estimate)
        selected_ids = {reader["id"] for reader in readers}
        readers_by_id = {reader["id"]: reader for reader in readers}
        job = await enqueue_ai_job(
            user_id=manuscript["user_id"], manuscript_id=manuscript_id,
            job_type="reading",
            idempotency_key=reading_idempotency_key(manuscript_id, list(selected_ids)),
            payload={"reader_ids": sorted(selected_ids)}, retry_failed=True,
        )
        await db.manuscripts.update_one({"id": manuscript_id}, {"$set": {"reader_config_locked": True}})

        async def durable_compatibility_stream():
            """Translate stored worker progress into the legacy SSE event contract."""
            initial = await workflow_status(manuscript, readers)
            yield f"data: {json.dumps({'type': 'start', 'total_sections': manuscript.get('total_sections', 0), 'total_readers': len(readers), 'total_tasks': initial['total_tasks'], 'completed_tasks': initial['completed_tasks'], 'usage': initial.get('usage'), 'budget': initial.get('budget'), 'cost_estimate': initial_estimate})}\n\n"
            emitted = set()
            while True:
                if await request.is_disconnected():
                    return
                reactions = await db.reader_reactions.find(
                    {"manuscript_id": manuscript_id}, {"_id": 0}
                ).sort("section_number", 1).to_list(5000)
                for reaction in reactions:
                    pair = (reaction.get("reader_id"), reaction.get("section_number"))
                    if pair in emitted or reaction.get("reader_id") not in selected_ids:
                        continue
                    emitted.add(pair)
                    response_json = reaction.get("response_json") or {}
                    reader = readers_by_id.get(reaction.get("reader_id"), {})
                    event = {
                        **response_json,
                        "type": "reader_complete", "reader_id": reaction.get("reader_id"),
                        "reader_name": reaction.get("reader_name"),
                        "avatar_index": reader.get("avatar_index", 0),
                        "personality": reader.get("personality", ""),
                        "section_number": reaction.get("section_number"),
                        "inline_comments": reaction.get("inline_comments") or [],
                        "section_reflection": reaction.get("section_reflection"),
                        "reaction_id": reaction.get("id", ""),
                    }
                    yield f"data: {json.dumps(event)}\n\n"

                latest = await db.ai_jobs.find_one({"id": job["id"]}, {"_id": 0})
                if not latest:
                    yield f"data: {json.dumps({'type': 'reader_error', 'message': 'Reading job no longer exists'})}\n\n"
                    return
                if latest.get("status") == "completed":
                    final = await workflow_status(manuscript, readers)
                    yield f"data: {json.dumps({'type': 'all_complete', 'workflow': final})}\n\n"
                    return
                if latest.get("status") == "failed":
                    yield f"data: {json.dumps({'type': 'reader_error', 'message': latest.get('error') or 'Reading failed after automatic retries'})}\n\n"
                    final = await workflow_status(manuscript, readers)
                    yield f"data: {json.dumps({'type': 'all_complete', 'workflow': final})}\n\n"
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(_cfg.AI_JOB_POLL_SECONDS)

        return StreamingResponse(
            durable_compatibility_stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    await _limit_ai_operation(request, manuscript)

    sections = manuscript.get("sections", [])
    raw_text = (manuscript.get("raw_text") or "").strip()
    # Re-section if any section has no paragraph_lines (e.g. old manuscripts) so readers run on all sections
    if raw_text and any(
        not s.get("paragraph_lines")
        or s.get("line_start", 0) > s.get("line_end", -1)
        or any(not paragraph.get("paragraph_id") for paragraph in s.get("paragraph_lines", []))
        for s in sections
    ):
        logger.info("Manuscript has sections with no paragraph_lines or invalid range — re-sectioning from raw_text")
        new_sections, total_lines = split_manuscript(raw_text)
        update = {"sections": new_sections, "total_sections": len(new_sections), "total_lines": total_lines}
        await db.manuscripts.update_one({"id": manuscript_id}, {"$set": update})
        manuscript["sections"] = new_sections
        manuscript["total_sections"] = len(new_sections)
        manuscript["total_lines"] = total_lines
        sections = new_sections

    all_readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if not all_readers:
        raise HTTPException(404, "No readers found. Generate personas first.")

    if reader_ids:
        id_set = {rid.strip() for rid in reader_ids.split(",") if rid.strip()}
        readers = [r for r in all_readers if r.get("id") in id_set]
        if len(readers) != len(id_set):
            found_ids = {r.get("id") for r in readers}
            missing = id_set - found_ids
            logger.warning("read-all: some reader_ids not found for manuscript: %s", missing)
    else:
        readers = all_readers

    if not readers:
        raise HTTPException(400, "Select at least one valid reader")

    genre = manuscript.get("genre", "Fiction")
    initial_estimate = await preflight_estimate(manuscript, readers, "readers")
    _require_affordable(initial_estimate)
    await db.manuscripts.update_one({"id": manuscript_id}, {"$set": {"reader_config_locked": True}})
    manuscript["reader_config_locked"] = True
    initial_workflow = await workflow_status(manuscript, readers)

    async def event_generator():
        total_sections = len(sections)
        yield f"data: {json.dumps({'type': 'start', 'total_sections': total_sections, 'total_readers': len(readers), 'total_tasks': initial_workflow['total_tasks'], 'completed_tasks': initial_workflow['completed_tasks'], 'usage': initial_workflow['usage'], 'budget': initial_workflow.get('budget'), 'cost_estimate': initial_estimate, 'reader_models': sorted({task.get('actual_model') or task.get('planned_model') for task in initial_workflow['tasks'] if task.get('actual_model') or task.get('planned_model')})})}\n\n"

        for section in sorted(sections, key=lambda s: s["section_number"]):
            if await request.is_disconnected():
                logger.info("Client disconnected — pausing read-all stream")
                return

            sn = section["section_number"]
            paragraph_lines = section.get("paragraph_lines") or []
            line_start = section.get("line_start", 0)
            line_end = section.get("line_end", 0)
            if not paragraph_lines or line_start > line_end:
                logger.warning("Section %s has no paragraph_lines or invalid line range, skipping", sn)
                yield f"data: {json.dumps({'type': 'section_skipped', 'section_number': sn})}\n\n"
                continue

            # A reconnect is idempotent per selected reader. A raw count can
            # incorrectly skip work when the user changes the reader panel.
            existing_reactions = await db.reader_reactions.find(
                {"manuscript_id": manuscript_id, "section_number": sn}, {"_id": 0}
            ).to_list(10)
            completed_ids = {row.get("reader_id") for row in existing_reactions}
            missing_readers = [reader for reader in readers if reader.get("id") not in completed_ids]
            if not missing_readers:
                yield f"data: {json.dumps({'type': 'section_skipped', 'section_number': sn})}\n\n"
                continue

            yield f"data: {json.dumps({'type': 'section_start', 'section_number': sn, 'total_sections': total_sections})}\n\n"

            queue: asyncio.Queue = asyncio.Queue()

            # Emit thinking events immediately for all readers (before any await)
            for reader in missing_readers:
                rname = (reader.get("name") or "").strip() or f"Reader {reader.get('avatar_index', 0) + 1}"
                yield f"data: {json.dumps({'type': 'reader_thinking', 'reader_id': reader['id'], 'reader_name': rname, 'avatar_index': reader.get('avatar_index', 0), 'personality': reader.get('personality', ''), 'section_number': sn})}\n\n"

            semaphore = asyncio.Semaphore(_cfg.READER_MAX_CONCURRENCY)

            async def run_reader_with_delay(delay: float, r: dict, sec: dict, g: str, mid: str, q: asyncio.Queue):
                if delay > 0:
                    await asyncio.sleep(delay)
                async with semaphore:
                    return await reader_pipeline(r, sec, g, mid, q)

            section_with_total = {**section, "total_sections": total_sections, "model": manuscript.get("model") or DEFAULT_READER_MODEL}
            reader_tasks = [
                asyncio.create_task(run_reader_with_delay(i * _cfg.READER_START_STAGGER_SECONDS, r, section_with_total, genre, manuscript_id, queue))
                for i, r in enumerate(missing_readers)
            ]

            # Drain queue counting terminal events.
            # Poll every 15s max so we can send heartbeat pings to keep the SSE
            # connection alive through nginx and browser proxies.
            # Overall 120-second section safety net via elapsed time.
            terminal_count = 0
            terminal_reader_ids = set()
            section_deadline = asyncio.get_event_loop().time() + 180
            while terminal_count < len(missing_readers):
                if await request.is_disconnected():
                    logger.info("Client disconnected — cancelling reader tasks for section %s", sn)
                    for t in reader_tasks:
                        t.cancel()
                    await asyncio.gather(*reader_tasks, return_exceptions=True)
                    return

                remaining = section_deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.error(f"Section {sn}: section deadline reached — some readers stalled. Moving on.")
                    yield f"data: {json.dumps({'type': 'section_error', 'section_number': sn, 'message': 'Some readers stalled on this section'})}\n\n"
                    for task in reader_tasks:
                        if not task.done():
                            task.cancel()
                    for reader in missing_readers:
                        if reader["id"] not in terminal_reader_ids:
                            await update_task(
                                manuscript_id, reader["id"], sn, "failed",
                                error="Section execution deadline reached",
                            )
                    break
                try:
                    result = await asyncio.wait_for(queue.get(), timeout=min(15, remaining))
                except asyncio.TimeoutError:
                    # Send heartbeat so nginx / browser proxies know the connection is alive
                    yield ": heartbeat\n\n"
                    continue
                yield f"data: {json.dumps(result)}\n\n"
                if result.get("type") in ("reader_complete", "reader_error"):
                    terminal_count += 1
                    if result.get("reader_id"):
                        terminal_reader_ids.add(result["reader_id"])

            await asyncio.gather(*reader_tasks, return_exceptions=True)
            yield f"data: {json.dumps({'type': 'section_complete', 'section_number': sn})}\n\n"
            yield ": keep-alive\n\n"

            current_workflow = await workflow_status(manuscript, readers)
            current_budget = current_workflow.get("budget") or {}
            if not current_budget.get("unlimited") and float(current_budget.get("remaining_usd") or 0) <= 0:
                yield f"data: {json.dumps({'type': 'budget_exhausted', 'limit_usd': current_budget.get('limit_usd'), 'spent_usd': current_budget.get('spent_usd'), 'workflow': current_workflow})}\n\n"
                return

            # 2s pause between sections so we don't slam the API when all readers start section N+1
            await asyncio.sleep(2)

        logger.info("All reader pipelines complete. Sending reading_complete event.")
        final_workflow = await workflow_status(manuscript, readers)
        yield f"data: {json.dumps({'type': 'all_complete', 'workflow': final_workflow})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@api_router.get("/manuscripts/{manuscript_id}/all-reactions")
async def get_all_reactions(manuscript_id: str, request: Request):
    await _get_owned_manuscript(manuscript_id, request)
    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id}, {"_id": 0}
    ).sort("section_number", 1).to_list(1000)
    return reactions


@api_router.get("/manuscripts/{manuscript_id}/reading-status")
async def get_reading_status(manuscript_id: str, request: Request):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    status = await workflow_status(manuscript, readers)
    return {
        **status,
        "total_sections": manuscript.get("total_sections", 0),
        "total_readers": len(readers),
        "reactions_count": status["completed_tasks"],
        "expected_reactions": status["total_tasks"],
        "sections_covered": sorted({
            task["section_number"] for task in status["tasks"] if task.get("status") == "completed"
        }),
    }


@api_router.get("/manuscripts/{manuscript_id}/workflow-status")
async def get_workflow_status(manuscript_id: str, request: Request):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    return await workflow_status(manuscript, readers)


@api_router.get("/manuscripts/{manuscript_id}/cost-estimate")
async def get_cost_estimate(
    manuscript_id: str,
    request: Request,
    operation: str = Query("remaining", pattern="^(remaining|readers|editor|editor_regeneration|copyedit)$"),
    reader_ids: str | None = Query(None),
):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if reader_ids:
        selected = {item.strip() for item in reader_ids.split(",") if item.strip()}
        readers = [reader for reader in readers if reader.get("id") in selected]
    return await preflight_estimate(manuscript, readers, operation)


@api_router.get("/manuscripts/{manuscript_id}/budget")
async def get_manuscript_budget(manuscript_id: str, request: Request):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    return await budget_status(manuscript)


@api_router.patch("/manuscripts/{manuscript_id}/budget")
async def update_manuscript_budget(manuscript_id: str, body: BudgetUpdateRequest, request: Request):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    committed = float(manuscript.get("cost_spent_usd") or 0) + float(manuscript.get("cost_reserved_usd") or 0)
    if body.cost_limit_usd > 0 and body.cost_limit_usd < committed:
        raise HTTPException(409, f"Budget cannot be lower than the ${committed:.4f} already spent or reserved.")
    await db.manuscripts.update_one({"id": manuscript_id}, {"$set": {"cost_limit_usd": body.cost_limit_usd}})
    manuscript["cost_limit_usd"] = body.cost_limit_usd
    return await budget_status(manuscript)


@api_router.get("/manuscripts/{manuscript_id}/reactions/{section_number}")
async def get_reactions(manuscript_id: str, section_number: int, request: Request):
    await _get_owned_manuscript(manuscript_id, request)
    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id, "section_number": section_number}, {"_id": 0}
    ).to_list(10)
    return reactions


# ─── Editor Report ────────────────────────────────────────────────────────────

@api_router.post("/manuscripts/{manuscript_id}/editor-report")
async def create_editor_report(
    manuscript_id: str,
    request: Request,
    force: bool = Query(False, description="Explicitly regenerate an existing report"),
):
    manuscript_id = (manuscript_id or "").strip()
    if not manuscript_id or manuscript_id.lower() == "undefined":
        raise HTTPException(400, "Manuscript ID is missing. Open the report from the reading page or use a valid report URL.")

    manuscript = await _get_owned_manuscript(manuscript_id, request)

    existing_report = await db.editor_reports.find_one({"manuscript_id": manuscript_id}, {"_id": 0})
    if existing_report and not force:
        return {
            "id": existing_report.get("id"),
            "manuscript_id": manuscript_id,
            "report": existing_report.get("report_json") or {},
            "created_at": existing_report.get("created_at"),
            "cached": True,
        }
    await _limit_ai_operation(request, manuscript)

    if _cfg.AI_JOBS_ENABLED:
        key = request.headers.get("idempotency-key")
        if not key:
            key = f"editor-report:{manuscript_id}:initial" if not force else f"editor-report:{manuscript_id}:{uuid.uuid4()}"
        job = await enqueue_ai_job(
            user_id=manuscript["user_id"], manuscript_id=manuscript_id,
            job_type="editor_report", idempotency_key=key, payload={"force": force}, retry_failed=True,
        )
        return JSONResponse(public_job(job), status_code=202)

    total_sections = manuscript.get("total_sections", 0)
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    total_readers = len(readers)
    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id}, {"_id": 0}
    ).sort("section_number", 1).to_list(500)

    if not reactions:
        # Fallback: some Supabase/PostgREST setups return empty when .order() is chained; fetch without sort and sort in Python
        reactions = await db.reader_reactions.find(
            {"manuscript_id": manuscript_id}, {"_id": 0}
        ).to_list(500)
        if reactions:
            reactions.sort(key=lambda r: (r.get("section_number") or 0, r.get("reader_name") or ""))

    if not reactions:
        raise HTTPException(400, "No reader reactions found. Read at least one section first.")

    editor_estimate = await preflight_estimate(manuscript, readers, "editor_regeneration" if force else "editor")
    _require_affordable(editor_estimate)

    # Generate report from whatever reactions we have (partial OK if some readers/sections errored)
    try:
        report_data = await _build_editor_report(manuscript, reactions)
    except CostLimitExceeded as exc:
        raise HTTPException(402, {"code": "budget_insufficient", "message": str(exc), **exc.details})
    except Exception as exc:
        logger.exception("Editor V3 generation failed")
        raise HTTPException(502, str(exc))

    report_doc = {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "report_json": report_data,
        "created_at": now_iso(),
    }

    try:
        await db.editor_reports.insert_one({**report_doc})
    except Exception as e:
        err_msg = str(getattr(e, "message", e)) if hasattr(e, "message") else str(e)
        if "23505" in err_msg or "duplicate key" in err_msg.lower() or "unique constraint" in err_msg.lower():
            # One report per manuscript: update existing row instead of failing
            await db.editor_reports.update_one(
                {"manuscript_id": manuscript_id},
                {"$set": {"report_json": report_data, "created_at": report_doc["created_at"]}},
            )
            existing = await db.editor_reports.find_one({"manuscript_id": manuscript_id}, {"_id": 0})
            if existing:
                version = await append_report_version(manuscript_id, report_data, "regenerated")
                return {
                    "id": existing.get("id", report_doc["id"]),
                    "manuscript_id": manuscript_id,
                    "report": report_data,
                    "created_at": existing.get("created_at", report_doc["created_at"]),
                    "version": version["version"],
                }
        raise

    version = await append_report_version(manuscript_id, report_data, "generated")
    return {
        "id": report_doc["id"],
        "manuscript_id": manuscript_id,
        "report": report_data,
        "created_at": report_doc["created_at"],
        "version": version["version"],
    }


@api_router.post("/manuscripts/{manuscript_id}/editor-report/copy-edit")
async def create_copy_edit_appendix(manuscript_id: str, request: Request):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    await _limit_ai_operation(request, manuscript)
    if _cfg.AI_JOBS_ENABLED:
        key = request.headers.get("idempotency-key") or f"copy-edit:{manuscript_id}:{uuid.uuid4()}"
        job = await enqueue_ai_job(
            user_id=manuscript["user_id"], manuscript_id=manuscript_id,
            job_type="copy_edit", idempotency_key=key, payload={},
        )
        return JSONResponse(public_job(job), status_code=202)

    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    copy_estimate = await preflight_estimate(manuscript, readers, "copyedit")
    _require_affordable(copy_estimate)
    report = await db.editor_reports.find_one({"manuscript_id": manuscript_id}, {"_id": 0})
    if not report:
        raise HTTPException(400, "Generate the Editor V3 report before running the optional copy edit.")
    try:
        appendix = await _build_copy_edit_appendix(manuscript)
    except CostLimitExceeded as exc:
        raise HTTPException(402, {"code": "budget_insufficient", "message": str(exc), **exc.details})
    except Exception as exc:
        logger.exception("Copy-edit appendix generation failed")
        raise HTTPException(502, str(exc))
    report_json = report.get("report_json") or {}
    report_json["copy_edit_appendix"] = appendix
    await db.editor_reports.update_one(
        {"manuscript_id": manuscript_id},
        {"$set": {"report_json": report_json, "created_at": now_iso()}},
    )
    version = await append_report_version(manuscript_id, report_json, "copy_edit")
    return {"manuscript_id": manuscript_id, "copy_edit_appendix": appendix, "version": version["version"]}


@api_router.get("/manuscripts/{manuscript_id}/editor-report")
async def get_editor_report(manuscript_id: str, request: Request):
    await _get_owned_manuscript(manuscript_id, request)
    report = await db.editor_reports.find_one({"manuscript_id": manuscript_id}, {"_id": 0})
    if not report:
        raise HTTPException(404, "No editor report found")
    return report


@api_router.get("/manuscripts/{manuscript_id}/editor-report/versions")
async def get_editor_report_versions(manuscript_id: str, request: Request):
    await _get_owned_manuscript(manuscript_id, request)
    return await list_report_versions(manuscript_id)


@api_router.get("/manuscripts/{manuscript_id}/editor-report/versions/{version}")
async def get_editor_report_version(manuscript_id: str, version: int, request: Request):
    await _get_owned_manuscript(manuscript_id, request)
    row = await db.report_versions.find_one({"manuscript_id": manuscript_id, "version": version}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Report version not found")
    return row


@api_router.get("/manuscripts/{manuscript_id}/export")
async def export_manuscript_workspace(manuscript_id: str, request: Request):
    manuscript = await _get_owned_manuscript(manuscript_id, request)
    safe_manuscript = dict(manuscript)
    async def rows(table, limit=5000):
        return await table.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(limit)
    current_report = await db.editor_reports.find_one({"manuscript_id": manuscript_id}, {"_id": 0})
    return {
        "format": "roundtable-workspace", "schema_version": 1, "exported_at": now_iso(),
        "manuscript": safe_manuscript,
        "personas": await rows(db.reader_personas),
        "reactions": await rows(db.reader_reactions),
        "memories": await rows(db.reader_memories),
        "workflow_tasks": await rows(db.workflow_tasks),
        "ai_jobs": [public_job(job) for job in await rows(db.ai_jobs, 100)],
        "current_report": current_report,
        "report_versions": await rows(db.report_versions, 100),
    }


@api_router.delete("/manuscripts/{manuscript_id}")
async def delete_manuscript(manuscript_id: str, request: Request, confirm: bool = Query(False)):
    await _get_owned_manuscript(manuscript_id, request)
    if not confirm:
        raise HTTPException(400, "Deletion requires confirm=true")
    if (
        await db.ai_jobs.count_documents({"manuscript_id": manuscript_id, "status": "queued"})
        or await db.ai_jobs.count_documents({"manuscript_id": manuscript_id, "status": "running"})
    ):
        raise HTTPException(409, "Wait for the active AI job to finish before deleting this manuscript")
    # PostgreSQL/Supabase cascade from manuscripts. Explicit cleanup preserves
    # identical behavior in the local memory backend.
    for table in (
        db.ai_jobs, db.report_versions, db.editor_reports, db.workflow_tasks, db.reader_memories,
        db.reader_reactions, db.reader_personas,
    ):
        await table.delete_many({"manuscript_id": manuscript_id})
    await db.manuscripts.delete_one({"id": manuscript_id})
    return {"deleted": True, "manuscript_id": manuscript_id}
