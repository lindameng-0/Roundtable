"""Railway worker process for durable Roundtable AI jobs."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import time
import uuid

import config as cfg
from config import db
from services.ai_jobs import PermanentJobError, execute_ai_job
from utils import now_iso

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("roundtable.worker")


async def _heartbeat(job_id: str, worker_id: str) -> None:
    interval = max(20, cfg.AI_JOB_LEASE_SECONDS // 3)
    while True:
        await asyncio.sleep(interval)
        await db.touch_ai_worker(worker_id)
        if not await db.heartbeat_ai_job(job_id, worker_id, cfg.AI_JOB_LEASE_SECONDS):
            raise RuntimeError("AI job lease was lost")


async def _execute_with_heartbeat(job, worker_id):
    execution = asyncio.create_task(execute_ai_job(job))
    heartbeat = asyncio.create_task(_heartbeat(job["id"], worker_id))
    done, _ = await asyncio.wait({execution, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
    if heartbeat in done:
        execution.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await execution
        return await heartbeat
    heartbeat.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await heartbeat
    return await execution


async def _worker_slot(worker_id: str, *, once: bool = False) -> None:
    logger.info("AI worker %s ready", worker_id)
    last_heartbeat = 0.0
    while True:
        if time.monotonic() - last_heartbeat >= 10:
            await db.touch_ai_worker(worker_id)
            last_heartbeat = time.monotonic()
        recovered = await db.requeue_stale_ai_jobs()
        if recovered:
            logger.warning("Recovered %s AI job(s) with expired leases", recovered)
        job = await db.claim_ai_job(
            worker_id, cfg.AI_JOB_GLOBAL_CONCURRENCY,
            cfg.AI_JOB_USER_CONCURRENCY, cfg.AI_JOB_LEASE_SECONDS,
        )
        if not job:
            if once:
                return
            await asyncio.sleep(cfg.AI_JOB_POLL_SECONDS)
            continue

        logger.info("Claimed %s job %s (attempt %s)", job["job_type"], job["id"], job["attempts"])
        try:
            result = await _execute_with_heartbeat(job, worker_id)
            progress = {"stage": "completed", "completed": 1, "total": 1}
            if job["job_type"] == "reading" and result.get("workflow"):
                workflow = result["workflow"]
                progress = {
                    "stage": "completed", "completed": workflow["completed_tasks"],
                    "total": workflow["total_tasks"], "failed": workflow["failed_tasks"],
                }
            if not await db.complete_ai_job(job["id"], worker_id, result, progress):
                logger.error("Could not complete job %s because its lease was lost", job["id"])
            else:
                logger.info("Completed job %s", job["id"])
        except PermanentJobError as exc:
            await db.ai_jobs.update_one(
                {"id": job["id"], "worker_id": worker_id, "status": "running"},
                {"$set": {
                    "status": "failed", "error": str(exc)[:4000], "finished_at": now_iso(),
                    "updated_at": now_iso(), "worker_id": None, "lease_expires_at": None,
                }},
            )
            logger.warning("Job %s permanently failed: %s", job["id"], exc)
        except Exception as exc:
            delay = min(300, 10 * (2 ** max(0, int(job.get("attempts") or 1) - 1)))
            await db.fail_ai_job(job["id"], worker_id, str(exc), delay)
            logger.exception("Job %s failed; retry policy applied", job["id"])
        if once:
            return


async def run_worker(*, once: bool = False) -> None:
    if cfg.ENVIRONMENT == "production" and cfg.DATABASE_BACKEND != "postgres":
        raise RuntimeError("The production AI worker requires DATABASE_BACKEND=postgres")
    initialize = getattr(db, "initialize", None)
    if initialize:
        await initialize()
    base_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    try:
        if once:
            await _worker_slot(f"{base_id}-0", once=True)
        else:
            await asyncio.gather(*(
                _worker_slot(f"{base_id}-{slot}") for slot in range(cfg.AI_JOB_WORKER_SLOTS)
            ))
    finally:
        close = getattr(db, "close", None)
        if close:
            await close()


if __name__ == "__main__":
    asyncio.run(run_worker())
