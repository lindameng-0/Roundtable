"""Exercise the real HTTP MCP transport, account boundaries and paid job gates."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
from server import app
from services.auth_security import hash_opaque_token
from services.rate_limit import limiter

ORIGIN = {"origin": "https://roundtable.works"}


@pytest.fixture
def client(monkeypatch):
    config.db.clear()
    limiter.clear()
    monkeypatch.setenv("CORS_ORIGINS", ORIGIN["origin"])
    monkeypatch.setattr(config, "AI_JOBS_ENABLED", True)
    for uid in ("writer", "other"):
        config.db._data["users"].append({"user_id": uid, "name": uid,
                                        "email": f"{uid}@example.com", "email_verified": True})
        config.db._data["user_sessions"].append({"user_id": uid, "token_hash": hash_opaque_token(uid),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    with TestClient(app) as client:
        client.cookies.set("session_token", "writer")
        yield client
    config.db.clear()
    limiter.clear()


def key(client, permission="read"):
    result = client.post("/api/integrations/keys", headers=ORIGIN,
                         json={"name": "Test assistant", "permission": permission})
    assert result.status_code == 201, result.text
    assert result.headers["cache-control"] == "private, no-store"
    return result.json()


def rpc(client, token, method, params=None, extra_headers=None):
    return client.post("/api/mcp/", headers={"authorization": f"Bearer {token}",
        "accept": "application/json, text/event-stream", "mcp-protocol-version": "2025-06-18",
        **(extra_headers or {})}, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def call(client, token, name, **arguments):
    response = rpc(client, token, "tools/call", {"name": name, "arguments": arguments})
    assert response.status_code == 200, response.text
    assert "no-store" in response.headers["cache-control"]
    result = response.json()
    assert "error" not in result, result
    return result["result"]


def data(result):
    assert not result.get("isError"), result
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


def test_key_management_requires_verified_cookie_and_origin(client):
    assert client.post("/api/integrations/keys", json={"name": "x"}).status_code == 403
    assert client.post("/api/integrations/keys", headers={"origin": "https://evil.example"}, json={"name": "x"}).status_code == 403
    client.cookies.clear()
    assert client.post("/api/integrations/keys", headers=ORIGIN, json={"name": "x"}).status_code == 401
    client.cookies.set("session_token", "writer")
    config.db._data["users"][0]["email_verified"] = False
    assert client.post("/api/integrations/keys", headers=ORIGIN, json={"name": "x"}).status_code == 403


def test_hash_only_storage_revocation_expiry_and_account_boundary(client):
    created = key(client)
    stored = config.db._data["integration_keys"][0]
    assert stored["token_hash"] == hash_opaque_token(created["key"])
    assert created["key"] not in json.dumps(stored)
    listed = client.get("/api/integrations/keys", headers=ORIGIN).json()
    assert "token_hash" not in listed[0] and "key" not in listed[0]
    client.cookies.set("session_token", "other")
    assert client.get("/api/integrations/keys", headers=ORIGIN).json() == []
    client.delete(f"/api/integrations/keys/{created['id']}", headers=ORIGIN)
    assert rpc(client, created["key"], "tools/list").status_code == 200
    client.cookies.set("session_token", "writer")
    client.delete(f"/api/integrations/keys/{created['id']}", headers=ORIGIN)
    assert rpc(client, created["key"], "tools/list").status_code == 401
    expired = key(client)
    config.db._data["integration_keys"][0]["expires_at"] = "2020-01-01T00:00:00+00:00"
    assert rpc(client, expired["key"], "tools/list").status_code == 401


def test_initialize_tools_auth_and_dns_rebinding(client):
    token = key(client)["key"]
    result = rpc(client, token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                               "clientInfo": {"name": "test", "version": "1"}})
    assert result.status_code == 200, result.text
    assert result.json()["result"]["serverInfo"]["name"] == "Roundtable"
    tools = rpc(client, token, "tools/list").json()["result"]["tools"]
    assert {"create_manuscript", "start_reading", "get_editorial_report", "set_reader_focus"}.issubset({t["name"] for t in tools})
    assert all("ctx" not in t["inputSchema"].get("properties", {}) for t in tools)
    assert client.post("/api/mcp/", json={}).status_code == 401  # website cookie is insufficient
    assert rpc(client, "invalid", "tools/list").status_code == 401
    assert rpc(client, token, "tools/list", extra_headers={"origin": "https://evil.example"}).status_code == 403
    assert rpc(client, token, "tools/list", extra_headers={"host": "evil.example"}).status_code == 421
    client.cookies.clear()
    assert client.get("/api/auth/me", headers={"authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/integrations/keys", headers={**ORIGIN, "authorization": f"Bearer {token}"}).status_code == 401


def test_read_only_cannot_spend_or_access_other_accounts(client):
    token = key(client)["key"]
    config.db._data["manuscripts"].extend([
        {"id": "mine", "user_id": "writer", "title": "Mine", "raw_text": "private", "sections": [], "created_at": "2026-01-01"},
        {"id": "theirs", "user_id": "other", "title": "Secret title", "raw_text": "secret content", "created_at": "2026-01-01"},
    ])
    listed = data(call(client, token, "list_manuscripts"))
    assert [m["id"] for m in listed["manuscripts"]] == ["mine"]
    assert "raw_text" not in listed["manuscripts"][0]
    for tool in ("get_manuscript", "list_readers", "get_reading_results", "get_editorial_report"):
        result = call(client, token, tool, manuscript_id="theirs")
        assert result["isError"]
        assert "secret content" not in json.dumps(result)
    result = call(client, token, "create_manuscript", title="No", text="Should not save", confirm_credit_use=True)
    assert result["isError"] and "read-only" in json.dumps(result)
    result = call(client, token, "prepare_readers", manuscript_id="mine", confirm_credit_use=True)
    assert result["isError"]
    assert config.db._data["reader_personas"] == []
    assert len(config.db._data["manuscripts"]) == 2


def test_consent_estimate_and_idempotent_queue(client):
    token = key(client, "run")["key"]
    rejected = call(client, token, "create_manuscript", title="A cup", text="A short scene.", confirm_credit_use=False)
    assert rejected["isError"] and not config.db._data["manuscripts"]
    created = data(call(client, token, "create_manuscript", title="A cup", text="A short scene.", confirm_credit_use=True))
    manuscript_id = created["id"]
    assert call(client, token, "estimate_reading", manuscript_id=manuscript_id)["isError"]
    data(call(client, token, "prepare_readers", manuscript_id=manuscript_id, confirm_credit_use=True))
    result = data(call(client, token, "list_readers", manuscript_id=manuscript_id))
    reader_id = result["readers"][0]["id"]
    data(call(client, token, "set_reader_focus", manuscript_id=manuscript_id, reader_id=reader_id, primary_focus="plot_logic"))
    assert call(client, token, "estimate_reading", manuscript_id=manuscript_id, reader_ids=["foreign-reader"])["isError"]
    estimate = data(call(client, token, "estimate_reading", manuscript_id=manuscript_id, reader_ids=[reader_id]))
    assert estimate["can_start"]
    args = {"manuscript_id": manuscript_id, "reader_ids": [reader_id], "confirm_credit_use": True, "approved_estimate_credits": 0}
    assert call(client, token, "start_reading", **args)["isError"]
    assert not config.db._data["ai_jobs"]
    args["approved_estimate_credits"] = 10000
    first = data(call(client, token, "start_reading", **args))
    second = data(call(client, token, "start_reading", **args))
    assert first["id"] == second["id"] and first["status"] == "queued"
    assert len(config.db._data["ai_jobs"]) == 1
    assert call(client, token, "set_reader_focus", manuscript_id=manuscript_id, reader_id=reader_id, primary_focus="dialogue")["isError"]
    assert call(client, token, "create_editorial_report", manuscript_id=manuscript_id, confirm_credit_use=True, approved_estimate_credits=10000)["isError"]
    assert data(call(client, token, "get_job", job_id=first["id"]))["id"] == first["id"]


def test_credit_mode_blocks_unfunded_reading(client, monkeypatch):
    """Exercise the production credit-estimate path, not only legacy dollar budgets."""
    token = key(client, "run")["key"]
    created = data(call(client, token, "create_manuscript", title="Credits", text="Clara waited beside the cold tea.", confirm_credit_use=True))
    manuscript_id = created["id"]
    data(call(client, token, "prepare_readers", manuscript_id=manuscript_id, confirm_credit_use=True))
    monkeypatch.setattr(config, "CREDITS_ENABLED", True)
    monkeypatch.setattr(config, "STARTER_CREDITS", 0)
    estimate = data(call(client, token, "estimate_reading", manuscript_id=manuscript_id))
    assert estimate["estimated_credits"] > 0
    assert estimate["available_credits"] == 0 and not estimate["can_start"]
    result = call(client, token, "start_reading", manuscript_id=manuscript_id,
                  confirm_credit_use=True, approved_estimate_credits=10000)
    assert result["isError"] and config.db._data["ai_jobs"] == []


def test_real_three_section_reading_through_mcp(client, monkeypatch):
    """Run the actual worker pipeline in mock mode on three sections, then fetch the report."""
    from worker import run_worker
    from routers.api import split_manuscript
    monkeypatch.setattr(config, "READER_PIPELINE_VERSION", "v1")
    token = key(client, "run")["key"]
    text = "\n\n".join(["Chapter 1\nClara set out two cups. Her brother was late.",
                         "Chapter 2\nHer brother arrived with their mother's suitcase.",
                         "Chapter 3\nA floorboard creaked upstairs. Clara turned the letter over."])
    draft = data(call(client, token, "create_manuscript", title="Three sections", text=text, confirm_credit_use=True))
    manuscript_id = draft["id"]
    # A deliberately short three-section fixture exercises section progression.
    sections = []
    for i, line in enumerate(text.split("\n\n"), 1):
        section = split_manuscript(line)[0][0]
        section["section_number"] = i
        sections.append(section)
    config.db._data["manuscripts"][0].update(sections=sections, total_sections=3)
    readers = data(call(client, token, "prepare_readers", manuscript_id=manuscript_id, confirm_credit_use=True))["readers"]
    reading = data(call(client, token, "start_reading", manuscript_id=manuscript_id, reader_ids=[readers[0]["id"]],
                        confirm_credit_use=True, approved_estimate_credits=10000))
    async def run_next():
        await run_worker(once=True)
    asyncio.run(run_next())
    status = data(call(client, token, "get_job", job_id=reading["id"]))
    assert status["status"] == "completed", status
    results = data(call(client, token, "get_reading_results", manuscript_id=manuscript_id))
    assert results["reactions"]
    report = data(call(client, token, "create_editorial_report", manuscript_id=manuscript_id,
                       confirm_credit_use=True, approved_estimate_credits=10000))
    asyncio.run(run_next())
    assert data(call(client, token, "get_job", job_id=report["id"]))["status"] == "completed"
    assert data(call(client, token, "get_editorial_report", manuscript_id=manuscript_id))
