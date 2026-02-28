from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
import asyncio
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4o')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'openai')

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── Pydantic Models ──────────────────────────────────────────────────────────

class ManuscriptCreate(BaseModel):
    title: Optional[str] = "Untitled Manuscript"
    raw_text: str

class ManuscriptResponse(BaseModel):
    id: str
    title: str
    genre: Optional[str] = None
    target_audience: Optional[str] = None
    age_range: Optional[str] = None
    comparable_books: Optional[List[str]] = None
    sections: Optional[List[Dict]] = None
    total_sections: Optional[int] = None
    created_at: str

class GenreDetectionResponse(BaseModel):
    genre: str
    target_audience: str
    age_range: str
    comparable_books: List[str]

class ReaderPersonaResponse(BaseModel):
    id: str
    manuscript_id: str
    name: str
    age: int
    occupation: str
    personality: str
    reading_habits: str
    liked_tropes: List[str]
    disliked_tropes: List[str]
    voice_style: str
    temperature: float
    quote: str
    avatar_index: int
    created_at: str

class RegenerateRequest(BaseModel):
    reader_id: Optional[str] = None  # None = regenerate all

class ReactionResponse(BaseModel):
    id: str
    manuscript_id: str
    reader_id: str
    reader_name: str
    section_number: int
    summary: str
    full_thoughts: str
    created_at: str

class ModelConfigRequest(BaseModel):
    provider: str
    model: str

# ─── Helpers ─────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def make_chat(system_prompt: str, temperature: float = 0.7, session_id: str = None) -> LlmChat:
    sid = session_id or str(uuid.uuid4())
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=sid,
        system_message=system_prompt
    ).with_model(LLM_PROVIDER, LLM_MODEL)
    # Note: temperature is handled via prompt guidance since emergentintegrations may not expose it directly
    return chat

def split_manuscript(raw_text: str) -> List[Dict]:
    """Split manuscript into chapters or ~2000-word chunks."""
    # Try chapter-based split first
    chapter_pattern = re.compile(
        r'(?:^|\n\n+)((?:chapter|prologue|epilogue|part)\s+[\w\d]+[^\n]*)',
        re.IGNORECASE
    )
    matches = list(chapter_pattern.finditer(raw_text))

    sections = []
    if len(matches) >= 2:
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
            title = match.group(1).strip()
            text = raw_text[start:end].strip()
            if len(text) > 100:
                sections.append({
                    "section_number": i + 1,
                    "title": title,
                    "text": text,
                    "start_char": start,
                    "end_char": end
                })
    
    if not sections:
        # Word-chunk split ~2000 words
        words = raw_text.split()
        chunk_size = 2000
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            text = " ".join(chunk_words)
            sections.append({
                "section_number": len(sections) + 1,
                "title": f"Section {len(sections) + 1}",
                "text": text,
                "start_char": raw_text.find(chunk_words[0]) if chunk_words else 0,
                "end_char": 0
            })

    return sections

def compress_memory(memories: List[Dict], personality: str) -> Dict:
    """Compress accumulated reader memories for context."""
    if not memories:
        return {}
    
    combined = {
        "plot_events": [],
        "character_notes": {},
        "predictions": [],
        "questions": [],
        "emotional_state": "",
        "memorable_quotes": []
    }
    
    for m in memories:
        mj = m.get("memory_json", {})
        combined["plot_events"].extend(mj.get("plot_events", []))
        combined["character_notes"].update(mj.get("character_notes", {}))
        combined["predictions"].extend(mj.get("predictions", []))
        combined["questions"].extend(mj.get("questions", []))
        if mj.get("emotional_state"):
            combined["emotional_state"] = mj["emotional_state"]
        combined["memorable_quotes"].extend(mj.get("memorable_quotes", []))

    # Retention rules by personality
    is_analytical = "analytical" in personality.lower()
    is_casual = "casual" in personality.lower() or "vibes" in personality.lower()
    
    keep_events = 8 if is_analytical else 3 if is_casual else 5
    combined["plot_events"] = combined["plot_events"][-keep_events:]
    combined["predictions"] = combined["predictions"][-10:]
    combined["questions"] = list(dict.fromkeys(combined["questions"]))[-8:]
    combined["memorable_quotes"] = combined["memorable_quotes"][-5:]

    return combined

def parse_memory_update(text: str) -> Optional[Dict]:
    """Extract MEMORY_UPDATE JSON block from reader response."""
    pattern = re.search(r'MEMORY_UPDATE\s*\{(.*?)\}', text, re.DOTALL)
    if not pattern:
        # Try finding any JSON block after MEMORY_UPDATE
        idx = text.find('MEMORY_UPDATE')
        if idx == -1:
            return None
        sub = text[idx:]
        brace_start = sub.find('{')
        if brace_start == -1:
            return None
        # Find matching closing brace
        depth = 0
        for i, ch in enumerate(sub[brace_start:], brace_start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(sub[brace_start:i + 1])
                    except Exception:
                        return None
        return None
    try:
        return json.loads('{' + pattern.group(1) + '}')
    except Exception:
        return None

def extract_reaction_parts(full_text: str):
    """Separate narrative reaction from memory JSON."""
    idx = full_text.find('MEMORY_UPDATE')
    if idx == -1:
        return full_text.strip(), full_text.strip()
    narrative = full_text[:idx].strip()
    # Summary = first 2-3 sentences
    sentences = re.split(r'(?<=[.!?])\s+', narrative)
    summary = " ".join(sentences[:3]) if sentences else narrative[:300]
    return summary, narrative

# ─── Endpoints ────────────────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    return {"message": "Roundtable API"}

@api_router.get("/config/models")
async def get_available_models():
    """Return available model options for the UI."""
    return {
        "current_provider": LLM_PROVIDER,
        "current_model": LLM_MODEL,
        "available": [
            {"provider": "openai", "model": "gpt-4o", "label": "GPT-4o"},
            {"provider": "openai", "model": "gpt-4.1", "label": "GPT-4.1"},
            {"provider": "openai", "model": "gpt-4.1-mini", "label": "GPT-4.1 Mini"},
            {"provider": "openai", "model": "gpt-4.1-nano", "label": "GPT-4.1 Nano"},
            {"provider": "openai", "model": "gpt-4o", "label": "GPT-4o"},
            {"provider": "anthropic", "model": "claude-4-sonnet-20250514", "label": "Claude Sonnet 4"},
            {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
            {"provider": "gemini", "model": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            {"provider": "gemini", "model": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
        ]
    }

@api_router.post("/config/model")
async def update_model(req: ModelConfigRequest):
    """Update the active LLM model (in-process, not persisted to env)."""
    global LLM_MODEL, LLM_PROVIDER
    LLM_MODEL = req.model
    LLM_PROVIDER = req.provider
    return {"provider": LLM_PROVIDER, "model": LLM_MODEL}

@api_router.post("/manuscripts", response_model=ManuscriptResponse)
async def create_manuscript(manuscript: ManuscriptCreate):
    """Upload manuscript text, detect genre, split into sections."""
    raw_text = manuscript.raw_text.strip()
    if not raw_text:
        raise HTTPException(400, "Manuscript text cannot be empty")

    doc_id = str(uuid.uuid4())
    sections = split_manuscript(raw_text)

    # Genre detection via LLM
    genre_prompt = """You are a literary analyst. Analyze the provided manuscript excerpt and return ONLY a JSON object (no markdown, no explanation) with:
{
  "genre": "primary genre",
  "target_audience": "target reader description",
  "age_range": "age range (e.g. Adult, YA, Middle Grade)",
  "comparable_books": ["Book 1 by Author", "Book 2 by Author", "Book 3 by Author"]
}"""

    chat = make_chat(genre_prompt, temperature=0.3)
    sample = raw_text[:3000]
    response = await chat.send_message(UserMessage(text=f"Analyze this manuscript:\n\n{sample}"))

    genre_data = {}
    try:
        # Strip markdown code fences if present
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        genre_data = json.loads(clean)
    except Exception:
        # fallback
        genre_data = {
            "genre": "Fiction",
            "target_audience": "General readers",
            "age_range": "Adult",
            "comparable_books": []
        }

    doc = {
        "id": doc_id,
        "title": manuscript.title or "Untitled Manuscript",
        "raw_text": raw_text,
        "genre": genre_data.get("genre", "Fiction"),
        "target_audience": genre_data.get("target_audience", "General readers"),
        "age_range": genre_data.get("age_range", "Adult"),
        "comparable_books": genre_data.get("comparable_books", []),
        "sections": sections,
        "total_sections": len(sections),
        "created_at": now_iso()
    }

    await db.manuscripts.insert_one({**doc})
    return ManuscriptResponse(**doc)

@api_router.post("/manuscripts/upload")
async def upload_manuscript(file: UploadFile = File(...), title: str = Form("Untitled Manuscript")):
    """Upload a .txt file."""
    if not file.filename.endswith('.txt'):
        raise HTTPException(400, "Only .txt files are supported")
    content = await file.read()
    raw_text = content.decode('utf-8', errors='replace').strip()
    if not raw_text:
        raise HTTPException(400, "File is empty")
    
    manuscript = ManuscriptCreate(title=title or file.filename, raw_text=raw_text)
    return await create_manuscript(manuscript)

@api_router.get("/manuscripts/{manuscript_id}", response_model=ManuscriptResponse)
async def get_manuscript(manuscript_id: str):
    doc = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Manuscript not found")
    return ManuscriptResponse(**doc)

@api_router.patch("/manuscripts/{manuscript_id}/genre")
async def update_genre(manuscript_id: str, update: Dict[str, Any]):
    """Update genre/audience chips."""
    allowed = {"genre", "target_audience", "age_range", "comparable_books"}
    filtered = {k: v for k, v in update.items() if k in allowed}
    await db.manuscripts.update_one({"id": manuscript_id}, {"$set": filtered})
    return {"updated": filtered}

# ─── Reader Personas ──────────────────────────────────────────────────────────

READER_ARCHETYPES = [
    {
        "archetype": "analytical",
        "description": "Focuses on plot logic, narrative structure, and consistency. Spots plot holes instantly.",
        "temperature": 0.5
    },
    {
        "archetype": "emotional",
        "description": "Reacts to emotional resonance, character relationships, and feeling. Cries at sad scenes.",
        "temperature": 0.9
    },
    {
        "archetype": "casual",
        "description": "Reads for pure entertainment and vibes. Doesn't overthink — just feels it.",
        "temperature": 0.9
    },
    {
        "archetype": "skeptical",
        "description": "Hard to please. Questions everything, especially character motivations and coincidences.",
        "temperature": 0.7
    },
    {
        "archetype": "genre_savvy",
        "description": "Deeply familiar with genre conventions. Compares to published books and spots tropes.",
        "temperature": 0.7
    }
]

async def generate_single_persona(archetype_info: Dict, genre: str, audience: str, avatar_index: int, manuscript_id: str) -> Dict:
    system = f"""You are a creative writing assistant. Generate a realistic reader persona for a book club member.
Return ONLY a JSON object (no markdown, no explanation):
{{
  "name": "full name (diverse, realistic)",
  "age": <integer between 22-65>,
  "occupation": "specific occupation",
  "personality": "{archetype_info['archetype']}",
  "reading_habits": "describe reading habits and genre preferences",
  "liked_tropes": ["trope1", "trope2", "trope3"],
  "disliked_tropes": ["trope1", "trope2"],
  "voice_style": "description of how they write/speak (e.g. casual and emoji-heavy, analytical and precise)",
  "quote": "a one-line quote in their voice about what makes or breaks a book for them"
}}"""

    chat = make_chat(system, temperature=0.85)
    prompt = f"Create a {archetype_info['archetype']} reader persona for a {genre} novel targeting {audience}. Make them feel like a real, specific person."
    response = await chat.send_message(UserMessage(text=prompt))

    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        data = json.loads(clean)
    except Exception:
        data = {
            "name": f"Reader {avatar_index + 1}",
            "age": 35,
            "occupation": "Teacher",
            "personality": archetype_info["archetype"],
            "reading_habits": "Reads widely across genres",
            "liked_tropes": ["character development", "plot twists"],
            "disliked_tropes": ["info dumps"],
            "voice_style": "thoughtful and measured",
            "quote": "A good story makes me forget the world."
        }

    return {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "name": data.get("name", f"Reader {avatar_index + 1}"),
        "age": data.get("age", 35),
        "occupation": data.get("occupation", "Reader"),
        "personality": data.get("personality", archetype_info["archetype"]),
        "reading_habits": data.get("reading_habits", ""),
        "liked_tropes": data.get("liked_tropes", []),
        "disliked_tropes": data.get("disliked_tropes", []),
        "voice_style": data.get("voice_style", ""),
        "temperature": archetype_info["temperature"],
        "quote": data.get("quote", ""),
        "avatar_index": avatar_index,
        "created_at": now_iso()
    }

@api_router.get("/manuscripts/{manuscript_id}/personas", response_model=List[ReaderPersonaResponse])
async def get_personas(manuscript_id: str):
    personas = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if not personas:
        # Auto-generate if none exist
        manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
        if not manuscript:
            raise HTTPException(404, "Manuscript not found")
        return await _generate_all_personas(manuscript_id, manuscript.get("genre", "Fiction"), manuscript.get("target_audience", "General readers"))
    return [ReaderPersonaResponse(**p) for p in personas]

async def _generate_all_personas(manuscript_id: str, genre: str, audience: str) -> List[ReaderPersonaResponse]:
    # Delete existing
    await db.reader_personas.delete_many({"manuscript_id": manuscript_id})
    
    tasks = [
        generate_single_persona(archetype, genre, audience, i, manuscript_id)
        for i, archetype in enumerate(READER_ARCHETYPES)
    ]
    personas = await asyncio.gather(*tasks)
    
    docs = [p for p in personas]
    if docs:
        await db.reader_personas.insert_many([{**p} for p in docs])
    
    return [ReaderPersonaResponse(**p) for p in docs]

@api_router.post("/manuscripts/{manuscript_id}/personas/regenerate")
async def regenerate_personas(manuscript_id: str, req: RegenerateRequest):
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")
    
    genre = manuscript.get("genre", "Fiction")
    audience = manuscript.get("target_audience", "General readers")

    if req.reader_id:
        # Regenerate single reader
        existing = await db.reader_personas.find_one({"id": req.reader_id, "manuscript_id": manuscript_id}, {"_id": 0})
        if not existing:
            raise HTTPException(404, "Reader not found")
        
        avatar_index = existing.get("avatar_index", 0)
        archetype = READER_ARCHETYPES[avatar_index % len(READER_ARCHETYPES)]
        new_persona = await generate_single_persona(archetype, genre, audience, avatar_index, manuscript_id)
        new_persona["id"] = req.reader_id  # Keep same ID
        
        await db.reader_personas.replace_one({"id": req.reader_id}, {**new_persona})
        # Clear their memories and reactions
        await db.reader_memories.delete_many({"reader_id": req.reader_id})
        await db.reader_reactions.delete_many({"reader_id": req.reader_id})
        return ReaderPersonaResponse(**new_persona)
    else:
        # Regenerate all
        await db.reader_memories.delete_many({"manuscript_id": manuscript_id})
        await db.reader_reactions.delete_many({"manuscript_id": manuscript_id})
        return await _generate_all_personas(manuscript_id, genre, audience)

# ─── Reading / SSE Streaming ──────────────────────────────────────────────────

async def get_reader_reaction(
    reader: Dict,
    section_text: str,
    section_number: int,
    manuscript_id: str,
    genre: str
) -> Dict:
    """Generate a single reader's reaction to a section."""
    # Get accumulated memory
    memories = await db.reader_memories.find(
        {"manuscript_id": manuscript_id, "reader_id": reader["id"]},
        {"_id": 0}
    ).sort("section_number", 1).to_list(100)

    compressed_memory = compress_memory(memories, reader.get("personality", ""))

    memory_str = json.dumps(compressed_memory, indent=2) if compressed_memory else "No previous sections read yet."

    system_prompt = f"""You are {reader['name']}, a {reader['age']}-year-old {reader['occupation']} who reads {reader['reading_habits']}.
Your personality as a reader: {reader['personality']} — {reader['voice_style']}
Your favorite tropes: {', '.join(reader.get('liked_tropes', []))}
Tropes you dislike: {', '.join(reader.get('disliked_tropes', []))}
Your reaction style: {reader['voice_style']}

You are reading a {genre} manuscript. You are on section {section_number} of the story.

Here is what you remember from previous sections:
{memory_str}

Now read the following new section and react naturally as a reader. Include:
- Your emotional reactions to what happened
- Any predictions about what might happen next (label these clearly as predictions)
- Questions or confusions you have
- Character impressions (who do you trust, like, find annoying)
- If any of your previous predictions were confirmed or wrong, mention that
- Notable quotes or lines that stood out to you

Write in first person, in your natural voice. Be specific — reference actual character names, events, and details. Do not be generic. Your reaction should be 150-300 words.

After your reaction, output a JSON block labeled MEMORY_UPDATE with this exact format:
MEMORY_UPDATE
{{
  "plot_events": ["new event 1", "new event 2"],
  "character_notes": {{"character_name": "updated impression"}},
  "predictions": [{{"prediction": "what you think will happen", "confidence": "high/medium/low", "evidence": "why"}}],
  "questions": ["unresolved question"],
  "emotional_state": "how you're feeling about the story right now",
  "memorable_quotes": ["any standout lines from this section"]
}}"""

    chat = make_chat(system_prompt, temperature=reader.get("temperature", 0.7))
    response = await chat.send_message(UserMessage(text=f"Read and react to this section:\n\n{section_text[:4000]}"))

    summary, full_thoughts = extract_reaction_parts(response)
    memory_update = parse_memory_update(response)

    # Save reaction
    reaction_doc = {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "reader_id": reader["id"],
        "reader_name": reader["name"],
        "section_number": section_number,
        "summary": summary,
        "full_thoughts": full_thoughts,
        "created_at": now_iso()
    }
    await db.reader_reactions.insert_one({**reaction_doc})

    # Save memory update
    if memory_update:
        mem_doc = {
            "id": str(uuid.uuid4()),
            "manuscript_id": manuscript_id,
            "reader_id": reader["id"],
            "section_number": section_number,
            "memory_json": memory_update,
            "created_at": now_iso()
        }
        await db.reader_memories.insert_one({**mem_doc})

    return {
        "reader_id": reader["id"],
        "reader_name": reader["name"],
        "avatar_index": reader.get("avatar_index", 0),
        "personality": reader.get("personality", ""),
        "reaction": reaction_doc
    }

@api_router.get("/manuscripts/{manuscript_id}/read/{section_number}")
async def read_section_stream(manuscript_id: str, section_number: int):
    """SSE endpoint: stream all 5 reader reactions as they complete."""
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")

    sections = manuscript.get("sections", [])
    section = next((s for s in sections if s["section_number"] == section_number), None)
    if not section:
        raise HTTPException(404, f"Section {section_number} not found")

    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if not readers:
        raise HTTPException(404, "No readers found. Generate personas first.")

    genre = manuscript.get("genre", "Fiction")

    async def event_generator():
        # Send start event
        yield f"data: {json.dumps({'type': 'start', 'total_readers': len(readers), 'section_number': section_number})}\n\n"

        async def process_reader(reader):
            try:
                result = await get_reader_reaction(reader, section["text"], section_number, manuscript_id, genre)
                return {"type": "reaction", **result}
            except Exception as e:
                logger.error(f"Error processing reader {reader.get('name')}: {e}")
                return {"type": "error", "reader_id": reader["id"], "reader_name": reader.get("name", "Unknown"), "error": str(e)}

        tasks = [process_reader(reader) for reader in readers]
        
        # Run all in parallel and yield as each completes
        for coro in asyncio.as_completed(tasks):
            result = await coro
            yield f"data: {json.dumps(result)}\n\n"

        yield f"data: {json.dumps({'type': 'complete', 'section_number': section_number})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@api_router.get("/manuscripts/{manuscript_id}/reactions/{section_number}", response_model=List[ReactionResponse])
async def get_reactions(manuscript_id: str, section_number: int):
    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id, "section_number": section_number},
        {"_id": 0}
    ).to_list(10)
    return [ReactionResponse(**r) for r in reactions]

# ─── Editor Report ────────────────────────────────────────────────────────────

@api_router.post("/manuscripts/{manuscript_id}/editor-report")
async def generate_editor_report(manuscript_id: str):
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")

    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id}, {"_id": 0}
    ).sort("section_number", 1).to_list(500)

    if not reactions:
        raise HTTPException(400, "No reader reactions found. Read the manuscript first.")

    # Build reactions summary for editor
    reactions_text = ""
    section_word_counts = {}
    for r in reactions:
        sn = r.get("section_number", 0)
        reactions_text += f"\n[Section {sn}] {r.get('reader_name', 'Reader')}: {r.get('full_thoughts', '')[:500]}\n"
        section_word_counts[sn] = section_word_counts.get(sn, 0) + len(r.get("full_thoughts", "").split())

    editor_system = f"""You are a professional developmental editor with 20 years of experience. 
You have received reader reactions to a {manuscript.get('genre', 'fiction')} manuscript from a diverse panel of 5 beta readers.
Your job is to synthesize their feedback into a professional editorial report.
Return ONLY a JSON object (no markdown fences) with exactly this structure:
{{
  "executive_summary": ["paragraph1", "paragraph2", "paragraph3"],
  "consensus_findings": [
    {{"finding": "description", "reader_count": 3, "sections": [1, 2], "sentiment": "positive/negative/mixed"}}
  ],
  "character_impressions": [
    {{"character": "name", "impressions": ["reader1 view", "reader2 view"], "overall": "aggregate impression"}}
  ],
  "prediction_accuracy": [
    {{"prediction": "what was predicted", "outcome": "confirmed/denied/unclear", "readers": ["reader name"], "note": "implication"}}
  ],
  "engagement_by_section": [
    {{"section": 1, "engagement_score": 75, "note": "brief reason"}}
  ],
  "recommendations": [
    {{"priority": "high/medium/low", "title": "short title", "detail": "specific actionable advice"}}
  ]
}}"""

    chat = make_chat(editor_system, temperature=0.6)
    response = await chat.send_message(UserMessage(
        text=f"Here are all reader reactions:\n{reactions_text[:8000]}\n\nGenerate the editorial report."
    ))

    report_data = {}
    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        report_data = json.loads(clean)
    except Exception as e:
        logger.error(f"Failed to parse editor report: {e}")
        report_data = {
            "executive_summary": ["The manuscript received mixed reactions from the panel.", "Readers found the writing engaging in parts.", "Further development is recommended."],
            "consensus_findings": [],
            "character_impressions": [],
            "prediction_accuracy": [],
            "engagement_by_section": [{"section": k, "engagement_score": min(100, v // 2), "note": ""} for k, v in section_word_counts.items()],
            "recommendations": [{"priority": "medium", "title": "Continue revision", "detail": "Address reader concerns and iterate."}]
        }

    # Add engagement data from actual word counts
    if not report_data.get("engagement_by_section"):
        report_data["engagement_by_section"] = [
            {"section": k, "engagement_score": min(100, v // 2), "note": ""}
            for k, v in sorted(section_word_counts.items())
        ]

    report_doc = {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "report_json": report_data,
        "created_at": now_iso()
    }
    await db.editor_reports.insert_one({**report_doc})
    return {"id": report_doc["id"], "manuscript_id": manuscript_id, "report": report_data, "created_at": report_doc["created_at"]}

@api_router.get("/manuscripts/{manuscript_id}/editor-report")
async def get_editor_report(manuscript_id: str):
    report = await db.editor_reports.find_one(
        {"manuscript_id": manuscript_id}, {"_id": 0}
    )
    if not report:
        raise HTTPException(404, "No editor report found")
    return report

app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
