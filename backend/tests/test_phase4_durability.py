"""Phase 4 persistence contracts, using the deterministic memory backend."""
from fastapi.testclient import TestClient

from config import db
from server import app


def _create_workspace(client):
    created = client.post("/api/manuscripts", json={
        "title": "Durability contract",
        "raw_text": "Chapter One\n\n" + ("A durable story beat. " * 30),
    })
    assert created.status_code == 200, created.text
    body = created.json()
    return body, {"X-Manuscript-Token": body["access_token"]}


def test_report_history_export_and_confirmed_deletion():
    db.clear()
    with TestClient(app) as client:
        manuscript, headers = _create_workspace(client)
        mid = manuscript["id"]
        personas = client.get(f"/api/manuscripts/{mid}/personas", headers=headers).json()
        stream = client.get(
            f"/api/manuscripts/{mid}/read-all?reader_ids={personas[0]['id']}",
            headers=headers,
        )
        assert stream.status_code == 200

        first = client.post(f"/api/manuscripts/{mid}/editor-report", headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["version"] == 1

        cached = client.post(f"/api/manuscripts/{mid}/editor-report", headers=headers)
        assert cached.json()["cached"] is True
        versions = client.get(f"/api/manuscripts/{mid}/editor-report/versions", headers=headers)
        assert [row["version"] for row in versions.json()] == [1]

        regenerated = client.post(f"/api/manuscripts/{mid}/editor-report?force=true", headers=headers)
        assert regenerated.status_code == 200, regenerated.text
        assert regenerated.json()["version"] == 2
        old = client.get(f"/api/manuscripts/{mid}/editor-report/versions/1", headers=headers)
        assert old.status_code == 200
        assert old.json()["report_json"]["schema_version"] == 3

        exported = client.get(f"/api/manuscripts/{mid}/export", headers=headers)
        assert exported.status_code == 200
        payload = exported.json()
        assert payload["format"] == "roundtable-workspace"
        assert "access_token_hash" not in payload["manuscript"]
        assert len(payload["report_versions"]) == 2

        refused = client.delete(f"/api/manuscripts/{mid}", headers=headers)
        assert refused.status_code == 400
        deleted = client.delete(f"/api/manuscripts/{mid}?confirm=true", headers=headers)
        assert deleted.status_code == 200
        assert client.get(f"/api/manuscripts/{mid}", headers=headers).status_code == 404
        assert not db.reader_reactions._rows
        assert not db.report_versions._rows


def test_health_reports_selected_database_backend():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["database_backend"] == "memory"
