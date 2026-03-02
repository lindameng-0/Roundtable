import json
import re
import uuid
import asyncio
import logging
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse

import config as _cfg
from config import db
from models import (
    ManuscriptCreate,
    ManuscriptResponse,
    ReaderPersonaResponse,
    RegenerateRequest,
    ModelConfigRequest,
    AppendTextRequest,
    WaitlistRequest,
)
from utils import now_iso, make_chat, UserMessage

from services.manuscript import split_manuscript
from services.personas import (
    READER_ARCHETYPES,
    DEFAULT_READER_COUNT,
    generate_single_persona,
    generate_all_personas,
    add_one_persona,
)
from services.readers import reader_pipeline
from services.editor import generate_editor_report as _build_editor_report
from routers.auth import _get_session_user

api_router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

MANUSCRIPT_LIMIT = 2


async def _get_optional_user(request: Request):
    """Return current user or None if not authenticated."""
    try:
        return await _get_session_user(request)
    except HTTPException:
        return None


def _is_admin(email: str) -> bool:
    return email and (email.strip().lower() in [e.strip().lower() for e in getattr(_cfg, "ADMIN_EMAILS", [])])


# ─── Root & Config ────────────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    return {"message": "Roundtable API"}


@api_router.get("/config/models")
async def get_available_models():
    return {
        "current_provider": _cfg.LLM_PROVIDER,
        "current_model": _cfg.LLM_MODEL,
        "available": [
            {"provider": "openai", "model": "gpt-4o", "label": "GPT-4o"},
            {"provider": "openai", "model": "gpt-4.1", "label": "GPT-4.1"},
            {"provider": "openai", "model": "gpt-4.1-mini", "label": "GPT-4.1 Mini"},
            {"provider": "openai", "model": "gpt-4.1-nano", "label": "GPT-4.1 Nano"},
            {"provider": "anthropic", "model": "claude-4-sonnet-20250514", "label": "Claude Sonnet 4"},
            {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
            {"provider": "gemini", "model": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            {"provider": "gemini", "model": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
        ],
    }


@api_router.post("/config/model")
async def update_model(req: ModelConfigRequest):
    _cfg.LLM_MODEL = req.model
    _cfg.LLM_PROVIDER = req.provider
    return {"provider": _cfg.LLM_PROVIDER, "model": _cfg.LLM_MODEL}


# ─── User usage (for manuscript limit) ───────────────────────────────────────

@api_router.get("/user/usage")
async def get_user_usage(request: Request):
    """Return used/manuscript limit and is_admin. Unauthenticated => used 0, limit 2, is_admin false."""
    user = await _get_optional_user(request)
    if not user:
        return {"used": 0, "limit": MANUSCRIPT_LIMIT, "is_admin": False}
    email = (user.get("email") or "").strip()
    is_admin = _is_admin(email)
    used = await db.manuscripts.count_documents({"user_id": user["user_id"]})
    return {"used": used, "limit": MANUSCRIPT_LIMIT, "is_admin": is_admin, "email": email or None}


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

    # Attach user_id if the user is authenticated (optional auth — anonymous allowed)
    user_id = None
    user = None
    try:
        user = await _get_session_user(request)
        user_id = user["user_id"]
    except HTTPException:
        pass  # anonymous submission still allowed

    # Usage limit: non-admin users get 2 free manuscripts total
    if user_id and user:
        if not _is_admin(user.get("email") or ""):
            used = await db.manuscripts.count_documents({"user_id": user_id})
            if used >= MANUSCRIPT_LIMIT:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "limit_reached",
                        "message": "You've used your 2 free reads.",
                        "used": used,
                        "limit": MANUSCRIPT_LIMIT,
                    },
                )

    doc_id = str(uuid.uuid4())
    sections, total_lines = split_manuscript(raw_text)

    # Genre detection via LLM — fall back to defaults if key missing or API fails
    genre_data: Dict = {"genre": "Fiction", "target_audience": "General readers", "age_range": "Adult", "comparable_books": []}
    try:
        genre_prompt = """You are a literary analyst. Analyze the manuscript excerpt and return ONLY a JSON object (no markdown) with:
{"genre":"primary genre","target_audience":"target reader description","age_range":"Adult/YA/Middle Grade/New Adult","comparable_books":["Book by Author","Book by Author","Book by Author"]}"""
        chat = make_chat(genre_prompt)
        sample = raw_text[:3000]
        response = await asyncio.wait_for(
            chat.send_message(UserMessage(text=f"Analyze:\n\n{sample}")),
            timeout=45.0,
        )
        try:
            clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
            genre_data = json.loads(clean)
        except Exception:
            pass  # keep defaults
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
        "model": getattr(manuscript, "model", None) or "gpt-4o-mini",
        "sections": sections,
        "total_sections": len(sections),
        "total_lines": total_lines,
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
    doc = await db.manuscripts.find_one({"id": manuscript_id}, None)
    if not doc:
        raise HTTPException(404, "Manuscript not found")
    new_raw = (doc.get("raw_text") or "") + chunk
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


# Max request body / form part size (100MB) for full-length manuscripts (500+ pages)
MAX_BODY_SIZE_BYTES = 100 * 1024 * 1024


@api_router.post("/manuscripts/upload")
async def upload_manuscript(request: Request):
    """Accept .txt, .docx, or .pdf file. Form parsed with max_part_size=100MB for full-length books."""
    async with request.form(max_part_size=MAX_BODY_SIZE_BYTES) as form:
        file = form.get("file")
        if not file or not getattr(file, "filename", None):
            raise HTTPException(400, "No file provided")
        title = form.get("title") or "Untitled Manuscript"
        if isinstance(title, list):
            title = title[0] if title else "Untitled Manuscript"
        filename = file.filename or ""
        if filename.endswith(".docx"):
            try:
                from docx import Document
                import io
                content = await file.read()
                doc = Document(io.BytesIO(content))
                paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                raw_text = "\n\n".join(paragraphs)
            except Exception as e:
                raise HTTPException(400, f"Failed to read .docx file: {e}")
        elif filename.endswith(".pdf"):
            try:
                import fitz  # PyMuPDF
                import io
                content = await file.read()
                doc = fitz.open(stream=content, filetype="pdf")
                parts = []
                for page in doc:
                    parts.append(page.get_text())
                doc.close()
                raw_text = "\n\n".join(p.strip() for p in parts if p.strip())
            except Exception as e:
                raise HTTPException(400, f"Failed to read .pdf file: {e}")
        elif filename.endswith(".txt"):
            content = await file.read()
            raw_text = content.decode("utf-8", errors="replace").strip()
        else:
            raise HTTPException(400, "Please upload a .txt, .docx, or .pdf file")

    if not raw_text:
        raise HTTPException(400, "File is empty")

    return await create_manuscript(
        ManuscriptCreate(title=title or filename or "Untitled Manuscript", raw_text=raw_text),
        request,
    )


@api_router.get("/manuscripts/{manuscript_id}", response_model=ManuscriptResponse)
async def get_manuscript(manuscript_id: str):
    doc = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Manuscript not found")
    return ManuscriptResponse(**doc)


@api_router.patch("/manuscripts/{manuscript_id}/genre")
async def update_genre(manuscript_id: str, update: Dict[str, Any]):
    allowed = {"genre", "target_audience", "age_range", "comparable_books", "model"}
    filtered = {k: v for k, v in update.items() if k in allowed}
    await db.manuscripts.update_one({"id": manuscript_id}, {"$set": filtered})
    return {"updated": filtered}


# ─── Reader Personas ──────────────────────────────────────────────────────────

@api_router.get("/manuscripts/{manuscript_id}/personas", response_model=List[ReaderPersonaResponse])
async def get_personas(manuscript_id: str):
    personas = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if not personas:
        manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
        if not manuscript:
            raise HTTPException(404, "Manuscript not found")
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
async def regenerate_personas(manuscript_id: str, req: RegenerateRequest):
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
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
        return ReaderPersonaResponse(**new_persona)
    else:
        await db.reader_memories.delete_many({"manuscript_id": manuscript_id})
        await db.reader_reactions.delete_many({"manuscript_id": manuscript_id})
        existing_personas = await db.reader_personas.find({"manuscript_id": manuscript_id}).to_list(10)
        current_count = len(existing_personas)
        return await generate_all_personas(
            manuscript_id, genre, audience, age_range, count=min(current_count, len(READER_ARCHETYPES))
        )


@api_router.post("/manuscripts/{manuscript_id}/personas/add", response_model=ReaderPersonaResponse)
async def add_persona(manuscript_id: str):
    """Add the next reader from the preset list (max 5)."""
    try:
        return await add_one_persona(manuscript_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── Reading: SSE Stream ──────────────────────────────────────────────────────

@api_router.get("/manuscripts/{manuscript_id}/read-all")
async def read_all_sections_stream(
    manuscript_id: str,
    request: Request,
    reader_ids: str | None = Query(None, description="Comma-separated reader IDs to use; if omitted, all readers are used"),
):
    """SSE: auto-reads all sections sequentially, N readers in parallel per section. Pauses when client disconnects."""
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")

    sections = manuscript.get("sections", [])
    raw_text = (manuscript.get("raw_text") or "").strip()
    # Re-section if any section has no paragraph_lines (e.g. old manuscripts) so readers run on all sections
    if raw_text and any(not (s.get("paragraph_lines")) or s.get("line_start", 0) > s.get("line_end", -1) for s in sections):
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

    genre = manuscript.get("genre", "Fiction")

    async def event_generator():
        total_sections = len(sections)
        yield f"data: {json.dumps({'type': 'start', 'total_sections': total_sections, 'total_readers': len(readers)})}\n\n"

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

            # Skip sections where all readers already have reactions (idempotent on reconnect)
            existing = await db.reader_reactions.count_documents(
                {"manuscript_id": manuscript_id, "section_number": sn}
            )
            if existing >= len(readers):
                yield f"data: {json.dumps({'type': 'section_skipped', 'section_number': sn})}\n\n"
                continue

            yield f"data: {json.dumps({'type': 'section_start', 'section_number': sn, 'total_sections': total_sections})}\n\n"

            queue: asyncio.Queue = asyncio.Queue()

            # Emit thinking events immediately for all readers (before any await)
            for reader in readers:
                rname = (reader.get("name") or "").strip() or f"Reader {reader.get('avatar_index', 0) + 1}"
                yield f"data: {json.dumps({'type': 'reader_thinking', 'reader_id': reader['id'], 'reader_name': rname, 'avatar_index': reader.get('avatar_index', 0), 'personality': reader.get('personality', ''), 'section_number': sn})}\n\n"

            # Stagger reader starts by 3s each to stay under 30k TPM (avoid 429s)
            async def run_reader_with_delay(delay: float, r: dict, sec: dict, g: str, mid: str, q: asyncio.Queue):
                if delay > 0:
                    await asyncio.sleep(delay)
                return await reader_pipeline(r, sec, g, mid, q)

            section_with_total = {**section, "total_sections": total_sections, "model": manuscript.get("model") or "gpt-4o-mini"}
            reader_tasks = [
                asyncio.create_task(run_reader_with_delay(i * 3, r, section_with_total, genre, manuscript_id, queue))
                for i, r in enumerate(readers)
            ]

            # Drain queue counting terminal events.
            # Poll every 15s max so we can send heartbeat pings to keep the SSE
            # connection alive through nginx and browser proxies.
            # Overall 120-second section safety net via elapsed time.
            terminal_count = 0
            section_deadline = asyncio.get_event_loop().time() + 180
            while terminal_count < len(readers):
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

            await asyncio.gather(*reader_tasks, return_exceptions=True)
            yield f"data: {json.dumps({'type': 'section_complete', 'section_number': sn})}\n\n"
            yield ": keep-alive\n\n"

            # 2s pause between sections so we don't slam the API when all readers start section N+1
            await asyncio.sleep(2)

        logger.info("All reader pipelines complete. Sending reading_complete event.")
        yield f"data: {json.dumps({'type': 'all_complete'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@api_router.get("/manuscripts/{manuscript_id}/all-reactions")
async def get_all_reactions(manuscript_id: str):
    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id}, {"_id": 0}
    ).sort("section_number", 1).to_list(1000)
    return reactions


@api_router.get("/manuscripts/{manuscript_id}/reading-status")
async def get_reading_status(manuscript_id: str):
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")
    total_sections = manuscript.get("total_sections", 0)
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    total_readers = len(readers)
    reactions = await db.reader_reactions.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(1000)
    sections_covered = set(r.get("section_number") for r in reactions)
    complete = (
        total_sections > 0
        and total_readers > 0
        and len(sections_covered) >= total_sections
        and len(reactions) >= total_sections * total_readers
    )
    return {
        "complete": complete,
        "total_sections": total_sections,
        "total_readers": total_readers,
        "reactions_count": len(reactions),
        "expected_reactions": total_sections * total_readers,
        "sections_covered": sorted(sections_covered),
    }


@api_router.get("/manuscripts/{manuscript_id}/reactions/{section_number}")
async def get_reactions(manuscript_id: str, section_number: int):
    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id, "section_number": section_number}, {"_id": 0}
    ).to_list(10)
    return reactions


# ─── Editor Report ────────────────────────────────────────────────────────────

@api_router.post("/manuscripts/{manuscript_id}/editor-report")
async def create_editor_report(manuscript_id: str):
    manuscript_id = (manuscript_id or "").strip()
    if not manuscript_id or manuscript_id.lower() == "undefined":
        raise HTTPException(400, "Manuscript ID is missing. Open the report from the reading page or use a valid report URL.")

    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, None)
    if not manuscript:
        logger.warning("create_editor_report: manuscript not found for id=%r", manuscript_id)
        raise HTTPException(404, "Manuscript not found")

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

    # Generate report from whatever reactions we have (partial OK if some readers/sections errored)
    report_data = await _build_editor_report(manuscript, reactions)

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
                return {
                    "id": existing.get("id", report_doc["id"]),
                    "manuscript_id": manuscript_id,
                    "report": report_data,
                    "created_at": existing.get("created_at", report_doc["created_at"]),
                }
        raise

    return {
        "id": report_doc["id"],
        "manuscript_id": manuscript_id,
        "report": report_data,
        "created_at": report_doc["created_at"],
    }


@api_router.get("/manuscripts/{manuscript_id}/editor-report")
async def get_editor_report(manuscript_id: str):
    report = await db.editor_reports.find_one({"manuscript_id": manuscript_id}, {"_id": 0})
    if not report:
        raise HTTPException(404, "No editor report found")
    return report
