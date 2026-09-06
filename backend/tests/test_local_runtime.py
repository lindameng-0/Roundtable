"""End-to-end smoke test for the no-Supabase/no-LLM local runtime."""
import os
import asyncio
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_BACKEND"] = "memory"
os.environ["LLM_BACKEND"] = "mock"
os.environ["ENVIRONMENT"] = "test"
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)

from fastapi.testclient import TestClient

from server import app
from config import db
from services.auth_security import hash_opaque_token


def test_authenticated_local_workflow():
    db.clear()
    with TestClient(app) as client:
        raw_session = "local-smoke-session"
        asyncio.run(db.users.insert_one({
            "user_id": "local-user", "email": "local@example.com", "name": "Local Writer",
            "email_verified": True, "auth_provider": "email", "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        asyncio.run(db.user_sessions.insert_one({
            "user_id": "local-user", "token_hash": hash_opaque_token(raw_session),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        client.cookies.set("session_token", raw_session)
        created = client.post("/api/manuscripts", json={
            "title": "Local smoke test",
            "raw_text": "Chapter One\n\n" + ("A small story begins here. " * 30),
        })
        assert created.status_code == 200, created.text
        manuscript = created.json()
        manuscript_id = manuscript["id"]
        assert client.get(f"/api/manuscripts/{manuscript_id}").status_code == 200

        personas_response = client.get(f"/api/manuscripts/{manuscript_id}/personas")
        assert personas_response.status_code == 200, personas_response.text
        personas = personas_response.json()
        assert len(personas) == 3

        stream = client.get(
            f"/api/manuscripts/{manuscript_id}/read-all?reader_ids={personas[0]['id']}",
        )
        assert stream.status_code == 200, stream.text
        assert '"type": "reader_complete"' in stream.text
        assert '"type": "all_complete"' in stream.text

        workflow = client.get(f"/api/manuscripts/{manuscript_id}/workflow-status")
        assert workflow.status_code == 200, workflow.text
        assert workflow.json()["complete"] is False  # only one of the three configured readers ran
        assert workflow.json()["completed_tasks"] == manuscript["total_sections"]

        report = client.post(f"/api/manuscripts/{manuscript_id}/editor-report")
        assert report.status_code == 200, report.text
        report_json = report.json()["report"]
        assert report_json["schema_version"] == 3
        assert report_json["executive_summary"]["synopsis"]
        assert report_json["revision_plan"]

        cached = client.post(f"/api/manuscripts/{manuscript_id}/editor-report")
        assert cached.status_code == 200, cached.text
        assert cached.json()["cached"] is True
        assert cached.json()["id"] == report.json()["id"]
