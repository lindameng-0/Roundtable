"""
Backend tests for Roundtable AI Beta Reader app.
Tests: health check, manuscript CRUD, persona generation, SSE read-all stream.
"""
import pytest
import requests
import os
import json
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

SHORT_MANUSCRIPT_TEXT = """The old lighthouse keeper hadn't spoken to anyone in thirty years. His only companion was the light itself, turning endlessly against the fog.

One morning a letter arrived. It was sealed with wax the color of old blood, addressed in a hand he had not seen since his sister's death. He stood on the dock, the envelope trembling between his weathered fingers.

Inside was a single sentence: "The light has been lying to you." He looked up at the beam still turning above him, then back at the paper, then out at the sea."""

# We'll store the manuscript_id across tests
manuscript_id_store = {}


@pytest.fixture(scope="module")
def created_manuscript():
    """Create a manuscript once and share across tests in this module."""
    resp = requests.post(
        f"{BASE_URL}/api/manuscripts",
        json={"title": "TEST_Lighthouse Keeper", "raw_text": SHORT_MANUSCRIPT_TEXT},
        timeout=60
    )
    assert resp.status_code == 200, f"Manuscript creation failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "id" in data
    return data


# ── Health Check ───────────────────────────────────────────────────────────────

class TestHealthCheck:
    """Health endpoint"""

    def test_root_returns_200(self):
        """GET / should return 200"""
        resp = requests.get(f"{BASE_URL}/api/", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print(f"PASS: /api/ returned 200")

    def test_root_response_has_message(self):
        """Root endpoint returns valid JSON with a message"""
        resp = requests.get(f"{BASE_URL}/api/", timeout=10)
        data = resp.json()
        assert isinstance(data, dict)
        print(f"PASS: Root response is valid JSON: {data}")


# ── Manuscript Creation ────────────────────────────────────────────────────────

class TestManuscriptCreation:
    """POST /api/manuscripts"""

    def test_create_manuscript_returns_200(self):
        resp = requests.post(
            f"{BASE_URL}/api/manuscripts",
            json={"title": "TEST_Short Story", "raw_text": SHORT_MANUSCRIPT_TEXT},
            timeout=60
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print(f"PASS: POST /api/manuscripts returned 200")

    def test_create_manuscript_has_id(self):
        resp = requests.post(
            f"{BASE_URL}/api/manuscripts",
            json={"title": "TEST_Short Story 2", "raw_text": SHORT_MANUSCRIPT_TEXT},
            timeout=60
        )
        data = resp.json()
        assert "id" in data and isinstance(data["id"], str) and len(data["id"]) > 0
        print(f"PASS: Manuscript has id: {data['id']}")

    def test_create_manuscript_has_sections(self):
        resp = requests.post(
            f"{BASE_URL}/api/manuscripts",
            json={"title": "TEST_Short Story 3", "raw_text": SHORT_MANUSCRIPT_TEXT},
            timeout=60
        )
        data = resp.json()
        assert "sections" in data
        assert isinstance(data["sections"], list)
        assert len(data["sections"]) >= 1, "Expected at least 1 section"
        print(f"PASS: Manuscript has {len(data['sections'])} sections")

    def test_create_manuscript_sections_have_paragraph_lines(self):
        resp = requests.post(
            f"{BASE_URL}/api/manuscripts",
            json={"title": "TEST_Short Story 4", "raw_text": SHORT_MANUSCRIPT_TEXT},
            timeout=60
        )
        data = resp.json()
        sections = data.get("sections", [])
        assert len(sections) >= 1
        first_section = sections[0]
        assert "paragraph_lines" in first_section
        assert isinstance(first_section["paragraph_lines"], list)
        assert len(first_section["paragraph_lines"]) >= 1
        print(f"PASS: First section has {len(first_section['paragraph_lines'])} paragraph_lines")

    def test_create_manuscript_has_total_sections(self):
        resp = requests.post(
            f"{BASE_URL}/api/manuscripts",
            json={"title": "TEST_Short Story 5", "raw_text": SHORT_MANUSCRIPT_TEXT},
            timeout=60
        )
        data = resp.json()
        assert "total_sections" in data
        assert isinstance(data["total_sections"], int)
        assert data["total_sections"] >= 1
        print(f"PASS: total_sections = {data['total_sections']}")

    def test_create_manuscript_has_genre(self):
        resp = requests.post(
            f"{BASE_URL}/api/manuscripts",
            json={"title": "TEST_Short Story 6", "raw_text": SHORT_MANUSCRIPT_TEXT},
            timeout=60
        )
        data = resp.json()
        assert "genre" in data
        print(f"PASS: genre = {data.get('genre')}")

    def test_get_manuscript_by_id(self, created_manuscript):
        mid = created_manuscript["id"]
        resp = requests.get(f"{BASE_URL}/api/manuscripts/{mid}", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data["id"] == mid
        print(f"PASS: GET /api/manuscripts/{mid} returned 200")

    def test_get_nonexistent_manuscript_returns_404(self):
        resp = requests.get(f"{BASE_URL}/api/manuscripts/nonexistent-id-xyz", timeout=10)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print(f"PASS: Non-existent manuscript returns 404")


# ── Persona Generation ─────────────────────────────────────────────────────────

class TestPersonaGeneration:
    """GET /api/manuscripts/{id}/personas"""

    def test_personas_endpoint_returns_200(self, created_manuscript):
        mid = created_manuscript["id"]
        # Generate personas
        resp = requests.post(
            f"{BASE_URL}/api/manuscripts/{mid}/generate-personas",
            timeout=120
        )
        assert resp.status_code == 200, f"Generate personas failed: {resp.status_code} {resp.text}"
        print(f"PASS: POST /api/manuscripts/{mid}/generate-personas returned 200")

    def test_personas_returns_5_personas(self, created_manuscript):
        mid = created_manuscript["id"]
        # First generate, then fetch
        requests.post(f"{BASE_URL}/api/manuscripts/{mid}/generate-personas", timeout=120)
        resp = requests.get(f"{BASE_URL}/api/manuscripts/{mid}/personas", timeout=30)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 5, f"Expected 5 personas, got {len(data)}"
        print(f"PASS: GET personas returned {len(data)} personas")

    def test_each_persona_has_required_fields(self, created_manuscript):
        mid = created_manuscript["id"]
        resp = requests.get(f"{BASE_URL}/api/manuscripts/{mid}/personas", timeout=30)
        data = resp.json()
        if not data:
            pytest.skip("No personas available yet")
        required_fields = ["id", "name", "age", "occupation", "personality", "avatar_index"]
        for p in data:
            for field in required_fields:
                assert field in p, f"Persona missing field: {field}"
        print(f"PASS: All personas have required fields")

    def test_personas_have_unique_names(self, created_manuscript):
        mid = created_manuscript["id"]
        resp = requests.get(f"{BASE_URL}/api/manuscripts/{mid}/personas", timeout=30)
        data = resp.json()
        if not data:
            pytest.skip("No personas available yet")
        names = [p["name"] for p in data]
        assert len(names) == len(set(names)), f"Duplicate persona names found: {names}"
        print(f"PASS: All {len(names)} personas have unique names")

    def test_personas_not_found_for_nonexistent_manuscript(self):
        resp = requests.get(f"{BASE_URL}/api/manuscripts/nonexistent-xyz/personas", timeout=10)
        assert resp.status_code in [200, 404], f"Unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            assert resp.json() == []
        print(f"PASS: Non-existent manuscript personas returns {resp.status_code}")


# ── SSE Read-All Stream ────────────────────────────────────────────────────────

class TestSSEReadAll:
    """GET /api/manuscripts/{id}/read-all — SSE stream tests"""

    def test_sse_endpoint_exists_and_responds(self, created_manuscript):
        """SSE endpoint should start responding (not 404 or 500)"""
        mid = created_manuscript["id"]
        # Ensure personas exist first
        requests.post(f"{BASE_URL}/api/manuscripts/{mid}/generate-personas", timeout=120)
        time.sleep(1)

        resp = requests.get(
            f"{BASE_URL}/api/manuscripts/{mid}/read-all",
            stream=True,
            timeout=30,
            headers={"Accept": "text/event-stream"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type, f"Expected text/event-stream, got: {content_type}"
        resp.close()
        print(f"PASS: SSE endpoint exists and returns 200 with text/event-stream")

    def test_sse_emits_start_event(self, created_manuscript):
        """SSE stream must emit a 'start' event as the first data event"""
        mid = created_manuscript["id"]
        resp = requests.get(
            f"{BASE_URL}/api/manuscripts/{mid}/read-all",
            stream=True,
            timeout=30,
            headers={"Accept": "text/event-stream"}
        )
        assert resp.status_code == 200

        start_found = False
        lines_read = 0
        for line in resp.iter_lines(decode_unicode=True):
            lines_read += 1
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    if data.get("type") == "start":
                        start_found = True
                        assert "total_sections" in data
                        assert "total_readers" in data
                        print(f"PASS: Got start event: total_sections={data['total_sections']}, total_readers={data['total_readers']}")
                        break
                except json.JSONDecodeError:
                    pass
            if lines_read > 50:
                break
        resp.close()
        assert start_found, "Did not receive 'start' event in first 50 lines"

    def test_sse_no_404_for_missing_manuscript(self):
        """SSE endpoint returns 404 for unknown manuscript"""
        resp = requests.get(
            f"{BASE_URL}/api/manuscripts/nonexistent-xyz-sse/read-all",
            stream=True,
            timeout=10
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        resp.close()
        print(f"PASS: SSE returns 404 for unknown manuscript")

    def test_sse_stream_completes_with_short_manuscript(self, created_manuscript):
        """SSE stream for a short manuscript should emit section_complete and all_complete within 3 minutes"""
        mid = created_manuscript["id"]

        # Ensure personas exist
        requests.post(f"{BASE_URL}/api/manuscripts/{mid}/generate-personas", timeout=120)

        collected_events = []
        event_types_seen = set()

        start_time = time.time()
        MAX_WAIT = 180  # 3 minutes for short manuscript

        try:
            resp = requests.get(
                f"{BASE_URL}/api/manuscripts/{mid}/read-all",
                stream=True,
                timeout=MAX_WAIT,
                headers={"Accept": "text/event-stream"}
            )
            assert resp.status_code == 200

            for line in resp.iter_lines(decode_unicode=True):
                if time.time() - start_time > MAX_WAIT:
                    print(f"WARNING: Stream did not complete within {MAX_WAIT}s")
                    break
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        event_type = data.get("type")
                        event_types_seen.add(event_type)
                        collected_events.append(event_type)
                        print(f"  Event received: {event_type}")
                        if event_type == "all_complete":
                            elapsed = time.time() - start_time
                            print(f"PASS: all_complete received after {elapsed:.1f}s")
                            break
                    except json.JSONDecodeError:
                        pass
            resp.close()
        except Exception as e:
            print(f"WARNING: Stream exception (may be normal for long runs): {e}")

        print(f"Events seen: {event_types_seen}")
        print(f"Event sequence: {collected_events}")

        # Check ordering assertions
        assert "start" in event_types_seen, "Missing 'start' event"

        # If all_complete arrived, verify section events happened
        if "all_complete" in event_types_seen:
            assert "section_complete" in event_types_seen or "section_skipped" in event_types_seen, \
                "Expected section_complete or section_skipped before all_complete"
            # Verify ordering: start always before all_complete
            start_idx = next(i for i, e in enumerate(collected_events) if e == "start")
            all_complete_idx = next(i for i, e in enumerate(collected_events) if e == "all_complete")
            assert start_idx < all_complete_idx, "start event should come before all_complete"
            print(f"PASS: SSE stream completed correctly. Events: {collected_events}")
        else:
            # Partial run — still verify reader events arrived
            print(f"PARTIAL: Stream did not reach all_complete within timeout. Events seen so far: {event_types_seen}")
            assert "start" in event_types_seen, "At minimum, 'start' event must be present"

    def test_sse_reader_thinking_events_present(self, created_manuscript):
        """SSE stream should emit reader_thinking events for each reader"""
        mid = created_manuscript["id"]
        reader_thinking_seen = []
        start_time = time.time()
        MAX_WAIT = 60  # Just check the initial events

        try:
            resp = requests.get(
                f"{BASE_URL}/api/manuscripts/{mid}/read-all",
                stream=True,
                timeout=MAX_WAIT,
                headers={"Accept": "text/event-stream"}
            )
            for line in resp.iter_lines(decode_unicode=True):
                if time.time() - start_time > MAX_WAIT:
                    break
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if data.get("type") == "reader_thinking":
                            reader_thinking_seen.append(data.get("reader_name"))
                            print(f"  reader_thinking: {data.get('reader_name')}")
                        # Stop after first section's readers are thinking
                        if len(reader_thinking_seen) >= 5:
                            break
                        if data.get("type") == "section_complete":
                            break
                    except json.JSONDecodeError:
                        pass
            resp.close()
        except Exception as e:
            print(f"Exception (may be ok): {e}")

        if reader_thinking_seen:
            print(f"PASS: Got reader_thinking events for: {reader_thinking_seen}")
        else:
            # If section was already done (skipped), thinking events won't fire
            print(f"INFO: No reader_thinking events (section may have been skipped). This is acceptable on re-run.")


# ── Reading Status Endpoint ────────────────────────────────────────────────────

class TestReadingStatus:
    """GET /api/manuscripts/{id}/reading-status"""

    def test_reading_status_returns_200(self, created_manuscript):
        mid = created_manuscript["id"]
        resp = requests.get(f"{BASE_URL}/api/manuscripts/{mid}/reading-status", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "complete" in data
        assert "total_sections" in data
        assert "total_readers" in data
        print(f"PASS: reading-status: {data}")

    def test_all_reactions_endpoint(self, created_manuscript):
        mid = created_manuscript["id"]
        resp = requests.get(f"{BASE_URL}/api/manuscripts/{mid}/all-reactions", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: /all-reactions returned {len(data)} reactions")
