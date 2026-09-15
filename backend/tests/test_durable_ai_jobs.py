import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from config import db
from server import app
from services.ai_jobs import enqueue_ai_job
from services.auth_security import hash_opaque_token
from worker import run_worker


def _job(user_id, manuscript_id, key):
    return enqueue_ai_job(
        user_id=user_id, manuscript_id=manuscript_id, job_type="reading",
        idempotency_key=key, payload={"reader_ids": ["reader-1"]},
    )


def test_enqueue_is_idempotent_and_does_not_execute_in_web_process():
    async def scenario():
        db.clear()
        first = await _job("user-1", "manuscript-1", "same-operation")
        second = await _job("user-1", "manuscript-1", "same-operation")
        assert first["id"] == second["id"]
        assert second["status"] == "queued"
        assert second["attempts"] == 0
    asyncio.run(scenario())


def test_atomic_claim_honors_global_and_per_user_concurrency():
    async def scenario():
        db.clear()
        await _job("user-1", "manuscript-1", "u1-first")
        await _job("user-1", "manuscript-1", "u1-second")
        await _job("user-2", "manuscript-2", "u2-first")
        first = await db.claim_ai_job("worker-a", 2, 1, 600)
        second = await db.claim_ai_job("worker-b", 2, 1, 600)
        third = await db.claim_ai_job("worker-c", 2, 1, 600)
        assert first["user_id"] == "user-1"
        assert second["user_id"] == "user-2"
        assert third is None
    asyncio.run(scenario())


def test_expired_lease_requeues_same_job_for_idempotent_retry():
    async def scenario():
        db.clear()
        queued = await _job("user-1", "manuscript-1", "lease-retry")
        claimed = await db.claim_ai_job("dead-worker", 2, 1, 60)
        await db.ai_jobs.update_one({"id": claimed["id"]}, {"$set": {
            "lease_expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }})
        assert await db.requeue_stale_ai_jobs() == 1
        retried = await db.claim_ai_job("new-worker", 2, 1, 60)
        assert retried["id"] == queued["id"]
        assert retried["attempts"] == 2
    asyncio.run(scenario())


def test_job_status_is_private_to_its_account():
    async def seed():
        db.clear()
        for user_id in ("owner", "intruder"):
            await db.users.insert_one({
                "user_id": user_id, "email": f"{user_id}@example.com", "name": user_id,
                "email_verified": True, "created_at": datetime.now(timezone.utc).isoformat(),
            })
        await _job("owner", "manuscript-1", "private-job")
        raw = "intruder-session"
        await db.user_sessions.insert_one({
            "user_id": "intruder", "token_hash": hash_opaque_token(raw),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return raw, db.ai_jobs._rows[0]["id"]

    raw, job_id = asyncio.run(seed())
    with TestClient(app, cookies={"session_token": raw}) as client:
        assert client.get(f"/api/jobs/{job_id}").status_code == 403


def test_reading_finishes_after_originating_browser_closes():
    db.clear()
    raw = "closed-browser-session"
    asyncio.run(db.users.insert_one({
        "user_id": "browser-user", "email": "browser@example.com", "name": "Browser",
        "email_verified": True, "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    asyncio.run(db.user_sessions.insert_one({
        "user_id": "browser-user", "token_hash": hash_opaque_token(raw),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    with TestClient(app, cookies={"session_token": raw}) as browser:
        manuscript = browser.post("/api/manuscripts", json={
            "title": "Close me", "raw_text": "Chapter One\n\nA durable scene unfolds. " * 20,
        }).json()
        personas = browser.get(f"/api/manuscripts/{manuscript['id']}/personas").json()
        queued = browser.post(
            f"/api/manuscripts/{manuscript['id']}/jobs/reading?reader_ids={personas[0]['id']}"
        )
        assert queued.status_code == 202
        job_id = queued.json()["id"]

    # No request/client remains alive while the standalone worker executes.
    asyncio.run(run_worker(once=True))

    with TestClient(app, cookies={"session_token": raw}) as reopened_browser:
        job = reopened_browser.get(f"/api/jobs/{job_id}")
        assert job.status_code == 200
        assert job.json()["status"] == "completed"
        reactions = reopened_browser.get(f"/api/manuscripts/{manuscript['id']}/all-reactions").json()
        assert len(reactions) == manuscript["total_sections"]

        # Tabs loaded before the durable-jobs frontend release still use this
        # SSE URL. It must translate stored job progress without rerunning AI.
        legacy = reopened_browser.get(
            f"/api/manuscripts/{manuscript['id']}/read-all?reader_ids={personas[0]['id']}"
        )
        assert legacy.status_code == 200
        assert '\"type\": \"reader_complete\"' in legacy.text
        assert '\"type\": \"all_complete\"' in legacy.text


def test_queue_compares_offset_timestamps_as_instants():
    async def scenario():
        db.clear()
        now = datetime.now(timezone.utc)
        due = await _job("user-offset", "manuscript-offset", "due-offset")
        future = await _job("user-future", "manuscript-future", "future-offset")
        await db.ai_jobs.update_one({"id": due["id"]}, {"$set": {
            "available_at": (now - timedelta(hours=1)).astimezone(timezone(timedelta(hours=14))).isoformat(),
        }})
        await db.ai_jobs.update_one({"id": future["id"]}, {"$set": {
            "available_at": (now + timedelta(hours=1)).astimezone(timezone(timedelta(hours=-12))).isoformat(),
        }})
        claimed = await db.claim_ai_job("offset-worker", 2, 1, 60)
        assert claimed["id"] == due["id"]
        assert await db.claim_ai_job("other-worker", 2, 1, 60) is None
        await db.ai_jobs.update_one({"id": due["id"]}, {"$set": {
            "lease_expires_at": (now - timedelta(hours=1)).astimezone(timezone(timedelta(hours=14))).isoformat(),
        }})
        assert await db.requeue_stale_ai_jobs() == 1
    asyncio.run(scenario())


def test_progress_published_before_slowest_reader_finishes(monkeypatch):
    from services import ai_jobs

    async def scenario():
        db.clear()
        await db.manuscripts.insert_one({"id": "live", "user_id": "user", "sections": [
            {"section_number": 1, "paragraph_lines": [{"line": 1, "text": "A scene."}]}
        ]})
        for reader_id in ("fast", "slow"):
            await db.reader_personas.insert_one({"id": reader_id, "manuscript_id": "live"})
        published = asyncio.Event()
        completed = set()
        updates = []

        async def no_op(*args, **kwargs):
            return {}

        async def ledger(*args):
            return {"completed_tasks": len(completed), "total_tasks": 2, "failed_tasks": 0,
                    "complete": len(completed) == 2, "tasks": []}

        async def pipeline(reader, *args):
            if reader["id"] == "slow":
                await asyncio.wait_for(published.wait(), timeout=2)
            completed.add(reader["id"])

        async def save(job, progress):
            updates.append(progress)
            if progress.get("completed") == 1:
                assert "slow" not in completed
                published.set()

        monkeypatch.setattr(ai_jobs, "ensure_task_ledger", no_op)
        monkeypatch.setattr(ai_jobs, "preflight_estimate", no_op)
        monkeypatch.setattr(ai_jobs, "_require_affordable", lambda _: None)
        monkeypatch.setattr(ai_jobs, "workflow_status", ledger)
        monkeypatch.setattr(ai_jobs, "reader_pipeline", pipeline)
        monkeypatch.setattr(ai_jobs, "_save_progress", save)
        monkeypatch.setattr(ai_jobs._cfg, "READER_START_STAGGER_SECONDS", 0)
        monkeypatch.setattr(ai_jobs._cfg, "READER_MAX_CONCURRENCY", 2)
        result = await ai_jobs.execute_reading_job({"manuscript_id": "live", "user_id": "user"})
        assert result["workflow"]["completed_tasks"] == 2
        assert any(row.get("section") == 1 and row["completed"] == 0 for row in updates)
        assert published.is_set()

    asyncio.run(scenario())
