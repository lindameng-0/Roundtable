import json
import re
import uuid
import asyncio
import logging
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Request
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
)
from utils import now_iso, make_chat, UserMessage

from services.manuscript import split_manuscript
from services.personas import READER_ARCHETYPES, generate_single_persona, generate_all_personas
from services.readers import reader_pipeline
from services.editor import generate_editor_report as _build_editor_report
from routers.auth import _get_session_user

api_router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


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
    try:
        user = await _get_session_user(request)
        user_id = user["user_id"]
    except HTTPException:
        pass  # anonymous submission still allowed

    doc_id = str(uuid.uuid4())
    sections, total_lines = split_manuscript(raw_text)

    # Genre detection via LLM — fall back to defaults if key missing or API fails
    genre_data: Dict = {"genre": "Fiction", "target_audience": "General readers", "age_range": "Adult", "comparable_books": []}
    try:
        genre_prompt = """You are a literary analyst. Analyze the manuscript excerpt and return ONLY a JSON object (no markdown) with:
{"genre":"primary genre","target_audience":"target reader description","age_range":"Adult/YA/Middle Grade/New Adult","comparable_books":["Book by Author","Book by Author","Book by Author"]}"""
        chat = make_chat(genre_prompt)
        sample = raw_text[:3000]
        response = await chat.send_message(UserMessage(text=f"Analyze:\n\n{sample}"))
        try:
            clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
            genre_data = json.loads(clean)
        except Exception:
            pass  # keep defaults
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
    """Accept .txt or .docx file. Form parsed with max_part_size=100MB for full-length books."""
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
        elif filename.endswith(".txt"):
            content = await file.read()
            raw_text = content.decode("utf-8", errors="replace").strip()
        else:
            raise HTTPException(400, "Please upload a .txt or .docx file")

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
    allowed = {"genre", "target_audience", "age_range", "comparable_books"}
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
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Persona generation failed for manuscript %s", manuscript_id)
            msg = str(e).strip() or "LLM or database error"
            raise HTTPException(503, f"Reader generation failed: {msg}")
    return [ReaderPersonaResponse(**p) for p in personas]


@api_router.post("/manuscripts/{manuscript_id}/personas/regenerate")
async def regenerate_personas(manuscript_id: str, req: RegenerateRequest):
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")
    genre = manuscript.get("genre", "Fiction")
    audience = manuscript.get("target_audience", "General readers")

    if req.reader_id:
        existing = await db.reader_personas.find_one(
            {"id": req.reader_id, "manuscript_id": manuscript_id}, {"_id": 0}
        )
        if not existing:
            raise HTTPException(404, "Reader not found")
        avatar_index = existing.get("avatar_index", 0)
        archetype = READER_ARCHETYPES[avatar_index % len(READER_ARCHETYPES)]
        new_persona = await generate_single_persona(archetype, genre, audience, avatar_index, manuscript_id)
        new_persona["id"] = req.reader_id
        await db.reader_personas.replace_one({"id": req.reader_id}, {**new_persona})
        await db.reader_memories.delete_many({"reader_id": req.reader_id})
        await db.reader_reactions.delete_many({"reader_id": req.reader_id})
        return ReaderPersonaResponse(**new_persona)
    else:
        await db.reader_memories.delete_many({"manuscript_id": manuscript_id})
        await db.reader_reactions.delete_many({"manuscript_id": manuscript_id})
        return await generate_all_personas(manuscript_id, genre, audience)


# ─── Reading: SSE Stream ──────────────────────────────────────────────────────

@api_router.get("/manuscripts/{manuscript_id}/read-all")
async def read_all_sections_stream(manuscript_id: str):
    """SSE: auto-reads all sections sequentially, 5 readers in parallel per section."""
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")

    sections = manuscript.get("sections", [])
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if not readers:
        raise HTTPException(404, "No readers found. Generate personas first.")

    genre = manuscript.get("genre", "Fiction")

    async def event_generator():
        total_sections = len(sections)
        yield f"data: {json.dumps({'type': 'start', 'total_sections': total_sections, 'total_readers': len(readers)})}\n\n"

        for section in sorted(sections, key=lambda s: s["section_number"]):
            sn = section["section_number"]

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
                yield f"data: {json.dumps({'type': 'reader_thinking', 'reader_id': reader['id'], 'reader_name': reader.get('name'), 'avatar_index': reader.get('avatar_index', 0), 'personality': reader.get('personality', ''), 'section_number': sn})}\n\n"

            # Launch all readers in parallel
            reader_tasks = [
                asyncio.create_task(reader_pipeline(r, section, genre, manuscript_id, queue))
                for r in readers
            ]

            # Drain queue counting terminal events.
            # Poll every 15s max so we can send heartbeat pings to keep the SSE
            # connection alive through nginx and browser proxies.
            # Overall 120-second section safety net via elapsed time.
            terminal_count = 0
            section_deadline = asyncio.get_event_loop().time() + 120
            while terminal_count < len(readers):
                remaining = section_deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.error(f"Section {sn}: 120s deadline reached — some readers stalled. Moving on.")
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
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")

    total_sections = manuscript.get("total_sections", 0)
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    total_readers = len(readers)
    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id}, {"_id": 0}
    ).sort("section_number", 1).to_list(500)

    if not reactions:
        raise HTTPException(400, "No reader reactions found. Read the manuscript first.")

    if total_sections > 0 and total_readers > 0:
        sections_covered = set(r.get("section_number") for r in reactions)
        missing_sections = set(range(1, total_sections + 1)) - sections_covered
        if missing_sections:
            raise HTTPException(400, f"Reading is not complete. Sections {sorted(missing_sections)} have not been read yet.")
        if len(reactions) < total_sections * total_readers:
            raise HTTPException(400, f"Reading is not complete. {len(reactions)} of {total_sections * total_readers} reader-section combinations finished.")

    report_data = await _build_editor_report(manuscript, reactions)

    report_doc = {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "report_json": report_data,
        "created_at": now_iso(),
    }
    await db.editor_reports.insert_one({**report_doc})
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
