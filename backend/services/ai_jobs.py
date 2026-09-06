"""Persistent AI job queue and worker-side execution."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from typing import Any, Dict, List

import config as _cfg
from config import db
from services.cost_control import CostLimitExceeded, preflight_estimate
from services.editor import generate_copy_edit_appendix, generate_editor_report
from services.manuscript import split_manuscript
from services.readers import reader_pipeline
from services.report_versions import append_report_version
from services.workflow import ensure_task_ledger, update_task, workflow_status
from utils import now_iso

logger = logging.getLogger(__name__)
JOB_TYPES = {"reading", "editor_report", "copy_edit"}


class PermanentJobError(RuntimeError):
    """A job error that retrying cannot fix without user action."""


def reading_idempotency_key(manuscript_id: str, reader_ids: List[str]) -> str:
    selected = ",".join(sorted(set(reader_ids)))
    digest = hashlib.sha256(selected.encode("utf-8")).hexdigest()[:20]
    return f"reading:{manuscript_id}:{digest}"


async def enqueue_ai_job(
    *, user_id: str, manuscript_id: str, job_type: str,
    idempotency_key: str, payload: Dict[str, Any], retry_failed: bool = False,
) -> Dict[str, Any]:
    if job_type not in JOB_TYPES:
        raise ValueError(f"Unsupported AI job type: {job_type}")
    key = str(idempotency_key or "").strip()[:200]
    if not key:
        raise ValueError("An idempotency key is required")
    existing = await db.ai_jobs.find_one(
        {"user_id": user_id, "idempotency_key": key}, {"_id": 0}
    )
    if existing:
        if existing.get("manuscript_id") != manuscript_id or existing.get("job_type") != job_type:
            raise ValueError("Idempotency key was already used for a different operation")
        if existing.get("status") == "failed" and retry_failed:
            await db.ai_jobs.update_one({"id": existing["id"]}, {"$set": {
                "status": "queued", "error": None, "finished_at": None,
                "attempts": 0, "available_at": now_iso(), "updated_at": now_iso(),
            }})
            existing.update({"status": "queued", "error": None, "finished_at": None, "attempts": 0})
        return existing

    row = {
        "id": str(uuid.uuid4()), "user_id": user_id, "manuscript_id": manuscript_id,
        "job_type": job_type, "idempotency_key": key, "payload": payload,
        "status": "queued", "progress": {"stage": "queued"}, "result": None,
        "error": None, "attempts": 0, "max_attempts": _cfg.AI_JOB_MAX_ATTEMPTS,
        "available_at": now_iso(), "created_at": now_iso(), "updated_at": now_iso(),
    }
    try:
        return await db.ai_jobs.insert_one(row)
    except Exception as exc:
        if "23505" not in str(exc) and "duplicate" not in str(exc).lower():
            raise
        return await db.ai_jobs.find_one(
            {"user_id": user_id, "idempotency_key": key}, {"_id": 0}
        )


def public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: job.get(key) for key in (
            "id", "manuscript_id", "job_type", "status", "progress", "result",
            "error", "attempts", "max_attempts", "created_at", "updated_at",
            "started_at", "finished_at",
        )
    }


async def _save_progress(job: Dict[str, Any], progress: Dict[str, Any]) -> None:
    await db.ai_jobs.update_one(
        {"id": job["id"], "worker_id": job["worker_id"], "status": "running"},
        {"$set": {"progress": progress, "updated_at": now_iso()}},
    )


def _require_affordable(estimate: Dict[str, Any]) -> None:
    if not estimate.get("can_start"):
        raise PermanentJobError("The estimated cost is above this manuscript's remaining AI budget.")


async def execute_reading_job(job: Dict[str, Any]) -> Dict[str, Any]:
    manuscript_id = job["manuscript_id"]
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript or manuscript.get("user_id") != job.get("user_id"):
        raise PermanentJobError("Manuscript no longer exists or ownership changed")

    sections = manuscript.get("sections") or []
    raw_text = (manuscript.get("raw_text") or "").strip()
    if raw_text and any(
        not section.get("paragraph_lines")
        or section.get("line_start", 0) > section.get("line_end", -1)
        or any(not paragraph.get("paragraph_id") for paragraph in section.get("paragraph_lines", []))
        for section in sections
    ):
        sections, total_lines = split_manuscript(raw_text)
        await db.manuscripts.update_one({"id": manuscript_id}, {"$set": {
            "sections": sections, "total_sections": len(sections), "total_lines": total_lines,
        }})
        manuscript.update({"sections": sections, "total_sections": len(sections), "total_lines": total_lines})

    all_readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    requested = set(job.get("payload", {}).get("reader_ids") or [])
    readers = [reader for reader in all_readers if not requested or reader.get("id") in requested]
    if requested and {reader.get("id") for reader in readers} != requested:
        raise PermanentJobError("One or more selected readers no longer exist")
    if not readers:
        raise PermanentJobError("No readers found. Generate readers first.")

    await ensure_task_ledger(manuscript, readers)
    estimate = await preflight_estimate(manuscript, readers, "readers")
    _require_affordable(estimate)
    await db.manuscripts.update_one({"id": manuscript_id}, {"$set": {"reader_config_locked": True}})
    initial = await workflow_status(manuscript, readers)
    await _save_progress(job, {
        "stage": "reading", "completed": initial["completed_tasks"],
        "total": initial["total_tasks"], "failed": initial["failed_tasks"],
    })

    for section in sorted(sections, key=lambda row: row.get("section_number") or 0):
        section_number = int(section.get("section_number") or 0)
        existing = await db.reader_reactions.find(
            {"manuscript_id": manuscript_id, "section_number": section_number}, {"_id": 0}
        ).to_list(20)
        completed_ids = {row.get("reader_id") for row in existing}
        missing = [reader for reader in readers if reader.get("id") not in completed_ids]
        if not missing:
            continue

        section_payload = {
            **section, "total_sections": len(sections),
            "model": manuscript.get("model") or "gemini-2.5-flash",
        }
        queue: asyncio.Queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(_cfg.READER_MAX_CONCURRENCY)

        async def run_reader(index: int, reader: Dict[str, Any]):
            if index and _cfg.READER_START_STAGGER_SECONDS:
                await asyncio.sleep(index * _cfg.READER_START_STAGGER_SECONDS)
            async with semaphore:
                await reader_pipeline(reader, section_payload, manuscript.get("genre", "Fiction"), manuscript_id, queue)

        tasks = [asyncio.create_task(run_reader(index, reader)) for index, reader in enumerate(missing)]
        await asyncio.gather(*tasks, return_exceptions=True)
        # reader_pipeline persists both success and failure before emitting.
        while not queue.empty():
            queue.get_nowait()
        current = await workflow_status(manuscript, readers)
        await _save_progress(job, {
            "stage": "reading", "section": section_number,
            "completed": current["completed_tasks"], "total": current["total_tasks"],
            "failed": current["failed_tasks"],
        })

    final = await workflow_status(manuscript, readers)
    if final["failed_tasks"]:
        raise RuntimeError(f"{final['failed_tasks']} reader task(s) failed and will be retried")
    if not final["complete"]:
        raise RuntimeError("Reading stopped before every reader task completed")
    return {"workflow": {
        "completed_tasks": final["completed_tasks"], "total_tasks": final["total_tasks"],
        "failed_tasks": final["failed_tasks"], "complete": final["complete"],
        "usage": final.get("usage"), "budget": final.get("budget"),
        "models": sorted({
            task.get("actual_model") or task.get("planned_model")
            for task in final.get("tasks", [])
            if task.get("actual_model") or task.get("planned_model")
        }),
    }}


async def execute_editor_report_job(job: Dict[str, Any]) -> Dict[str, Any]:
    manuscript_id = job["manuscript_id"]
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript or manuscript.get("user_id") != job.get("user_id"):
        raise PermanentJobError("Manuscript no longer exists or ownership changed")
    force = bool((job.get("payload") or {}).get("force"))
    existing = await db.editor_reports.find_one({"manuscript_id": manuscript_id}, {"_id": 0})
    saved_version = await db.report_versions.find_one({"job_id": job["id"]}, {"_id": 0})
    if saved_version:
        return {"report": saved_version.get("report_json") or {}, "version": saved_version["version"], "cached": True}
    if existing and existing.get("source_job_id") == job["id"]:
        version = await append_report_version(
            manuscript_id, existing.get("report_json") or {}, "regenerated" if force else "generated", job["id"]
        )
        return {"report": existing.get("report_json") or {}, "version": version["version"], "cached": True}
    if existing and not force:
        return {"report": existing.get("report_json") or {}, "cached": True}

    reactions = await db.reader_reactions.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(5000)
    if not reactions:
        raise PermanentJobError("No reader reactions found. Read at least one section first.")
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    _require_affordable(await preflight_estimate(manuscript, readers, "editor_regeneration" if force else "editor"))
    await _save_progress(job, {"stage": "generating_report", "completed": 0, "total": 1})
    try:
        report_data = await generate_editor_report(manuscript, reactions)
    except CostLimitExceeded as exc:
        raise PermanentJobError(str(exc)) from exc

    report_doc = {
        "id": str(uuid.uuid4()), "manuscript_id": manuscript_id,
        "report_json": report_data, "created_at": now_iso(),
    }
    if existing:
        await db.editor_reports.update_one({"manuscript_id": manuscript_id}, {"$set": {
            "report_json": report_data, "created_at": report_doc["created_at"], "source_job_id": job["id"],
        }})
    else:
        try:
            await db.editor_reports.insert_one({**report_doc, "source_job_id": job["id"]})
        except Exception as exc:
            if "23505" not in str(exc) and "duplicate" not in str(exc).lower():
                raise
            await db.editor_reports.update_one({"manuscript_id": manuscript_id}, {"$set": {
                "report_json": report_data, "created_at": report_doc["created_at"], "source_job_id": job["id"],
            }})
    version = await append_report_version(
        manuscript_id, report_data, "regenerated" if force else "generated", job["id"]
    )
    return {"report": report_data, "version": version["version"], "cached": False}


async def execute_copy_edit_job(job: Dict[str, Any]) -> Dict[str, Any]:
    manuscript_id = job["manuscript_id"]
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript or manuscript.get("user_id") != job.get("user_id"):
        raise PermanentJobError("Manuscript no longer exists or ownership changed")
    report = await db.editor_reports.find_one({"manuscript_id": manuscript_id}, {"_id": 0})
    if not report:
        raise PermanentJobError("Generate the editor report before running the copy edit.")
    saved_version = await db.report_versions.find_one({"job_id": job["id"]}, {"_id": 0})
    if saved_version:
        saved_report = saved_version.get("report_json") or {}
        return {"copy_edit_appendix": saved_report.get("copy_edit_appendix") or {}, "version": saved_version["version"]}
    if report.get("source_job_id") == job["id"] and (report.get("report_json") or {}).get("copy_edit_appendix"):
        version = await append_report_version(
            manuscript_id, report["report_json"], "copy_edit", job["id"]
        )
        return {"copy_edit_appendix": report["report_json"]["copy_edit_appendix"], "version": version["version"]}
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    _require_affordable(await preflight_estimate(manuscript, readers, "copyedit"))
    await _save_progress(job, {"stage": "copy_edit", "completed": 0, "total": 1})
    try:
        appendix = await generate_copy_edit_appendix(manuscript)
    except CostLimitExceeded as exc:
        raise PermanentJobError(str(exc)) from exc
    report_json = report.get("report_json") or {}
    report_json["copy_edit_appendix"] = appendix
    await db.editor_reports.update_one({"manuscript_id": manuscript_id}, {"$set": {
        "report_json": report_json, "created_at": now_iso(), "source_job_id": job["id"],
    }})
    version = await append_report_version(manuscript_id, report_json, "copy_edit", job["id"])
    return {"copy_edit_appendix": appendix, "version": version["version"]}


async def execute_ai_job(job: Dict[str, Any]) -> Dict[str, Any]:
    if job["job_type"] == "reading":
        return await execute_reading_job(job)
    if job["job_type"] == "editor_report":
        return await execute_editor_report_job(job)
    if job["job_type"] == "copy_edit":
        return await execute_copy_edit_job(job)
    raise PermanentJobError(f"Unsupported job type: {job.get('job_type')}")
