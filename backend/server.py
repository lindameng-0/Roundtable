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
from pydantic import BaseModel, Field, ConfigDict, field_validator
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
    total_lines: Optional[int] = None
    created_at: str

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
    personality_specific_instructions: Optional[str] = ""
    favorite_genres: Optional[Any] = ""
    genre_preferences: Optional[Any] = ""
    reading_priority: Optional[Any] = ""
    created_at: str

    @field_validator("favorite_genres", "genre_preferences", "reading_priority",
                     "personality_specific_instructions", "reading_habits", "voice_style",
                     "quote", "occupation", mode="before")
    @classmethod
    def coerce_to_str(cls, v):
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        if v is None:
            return ""
        return v

class RegenerateRequest(BaseModel):
    reader_id: Optional[str] = None

class ModelConfigRequest(BaseModel):
    provider: str
    model: str

# ─── Helpers ─────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def make_chat(system_prompt: str, session_id: str = None) -> LlmChat:
    sid = session_id or str(uuid.uuid4())
    return LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=sid,
        system_message=system_prompt
    ).with_model(LLM_PROVIDER, LLM_MODEL)

async def send_message_async(chat: LlmChat, message: UserMessage) -> str:
    """Run blocking send_message in a thread pool so asyncio.gather truly parallelizes."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, chat.send_message, message)

def split_manuscript(raw_text: str) -> List[Dict]:
    """Split manuscript into chapters or ~2000-word chunks. Assign global line numbers to paragraphs."""
    chapter_pattern = re.compile(
        r'(?:^|\n\n+)((?:chapter|prologue|epilogue|part)\s+[\w\d]+[^\n]*)',
        re.IGNORECASE
    )
    matches = list(chapter_pattern.finditer(raw_text))

    raw_sections = []
    if len(matches) >= 2:
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
            title = match.group(1).strip()
            text = raw_text[start:end].strip()
            if len(text) > 100:
                raw_sections.append({"title": title, "text": text, "start_char": start, "end_char": end})

    if not raw_sections:
        words = raw_text.split()
        chunk_size = 2000
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            text = " ".join(chunk_words)
            raw_sections.append({
                "title": f"Section {len(raw_sections) + 1}",
                "text": text,
                "start_char": 0,
                "end_char": 0
            })

    # Assign global line numbers: each non-empty paragraph = 1 line
    sections = []
    global_line = 1
    for idx, rs in enumerate(raw_sections):
        paragraphs = [p.strip() for p in rs["text"].split("\n") if p.strip()]
        line_start = global_line
        paragraph_lines = []
        for p in paragraphs:
            paragraph_lines.append({"line": global_line, "text": p})
            global_line += 1
        line_end = global_line - 1
        sections.append({
            "section_number": idx + 1,
            "title": rs["title"],
            "text": rs["text"],
            "start_char": rs.get("start_char", 0),
            "end_char": rs.get("end_char", 0),
            "line_start": line_start,
            "line_end": line_end,
            "paragraph_lines": paragraph_lines
        })

    return sections, global_line - 1  # sections, total_lines

def compress_memory(memories: List[Dict], personality: str) -> Dict:
    if not memories:
        return {}
    combined = {
        "plot_events": [], "character_notes": {}, "predictions": [],
        "questions": [], "emotional_state": "", "memorable_quotes": []
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

    is_analytical = "analytical" in personality.lower()
    is_casual = "casual" in personality.lower() or "vibes" in personality.lower()
    keep_events = 8 if is_analytical else 3 if is_casual else 5
    combined["plot_events"] = combined["plot_events"][-keep_events:]
    combined["predictions"] = combined["predictions"][-10:]
    combined["questions"] = list(dict.fromkeys(combined["questions"]))[-8:]
    combined["memorable_quotes"] = combined["memorable_quotes"][-5:]
    return combined

def validate_inline_comments(comments: List[Dict], line_start: int, line_end: int) -> List[Dict]:
    """Clamp out-of-range line numbers to nearest valid line."""
    valid = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        line = c.get("line")
        if not isinstance(line, int):
            try:
                line = int(line)
            except (TypeError, ValueError):
                continue
        # Clamp to valid range
        line = max(line_start, min(line_end, line))
        valid.append({
            "line": line,
            "type": c.get("type", "reaction"),
            "comment": c.get("comment", "")
        })
    return valid

# ─── Config endpoints ─────────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    return {"message": "Roundtable API"}

@api_router.get("/config/models")
async def get_available_models():
    return {
        "current_provider": LLM_PROVIDER,
        "current_model": LLM_MODEL,
        "available": [
            {"provider": "openai", "model": "gpt-4o", "label": "GPT-4o"},
            {"provider": "openai", "model": "gpt-4.1", "label": "GPT-4.1"},
            {"provider": "openai", "model": "gpt-4.1-mini", "label": "GPT-4.1 Mini"},
            {"provider": "openai", "model": "gpt-4.1-nano", "label": "GPT-4.1 Nano"},
            {"provider": "anthropic", "model": "claude-4-sonnet-20250514", "label": "Claude Sonnet 4"},
            {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
            {"provider": "gemini", "model": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            {"provider": "gemini", "model": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
        ]
    }

@api_router.post("/config/model")
async def update_model(req: ModelConfigRequest):
    global LLM_MODEL, LLM_PROVIDER
    LLM_MODEL = req.model
    LLM_PROVIDER = req.provider
    return {"provider": LLM_PROVIDER, "model": LLM_MODEL}

# ─── Manuscript endpoints ─────────────────────────────────────────────────────

@api_router.post("/manuscripts", response_model=ManuscriptResponse)
async def create_manuscript(manuscript: ManuscriptCreate):
    raw_text = manuscript.raw_text.strip()
    if not raw_text:
        raise HTTPException(400, "Manuscript text cannot be empty")

    doc_id = str(uuid.uuid4())
    sections, total_lines = split_manuscript(raw_text)

    genre_prompt = """You are a literary analyst. Analyze the manuscript excerpt and return ONLY a JSON object (no markdown) with:
{"genre":"primary genre","target_audience":"target reader description","age_range":"Adult/YA/Middle Grade/New Adult","comparable_books":["Book by Author","Book by Author","Book by Author"]}"""

    chat = make_chat(genre_prompt)
    sample = raw_text[:3000]
    response = await chat.send_message(UserMessage(text=f"Analyze:\n\n{sample}"))
    genre_data = {}
    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        genre_data = json.loads(clean)
    except Exception:
        genre_data = {"genre": "Fiction", "target_audience": "General readers", "age_range": "Adult", "comparable_books": []}

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
        "total_lines": total_lines,
        "created_at": now_iso()
    }
    await db.manuscripts.insert_one({**doc})
    return ManuscriptResponse(**doc)

@api_router.post("/manuscripts/upload")
async def upload_manuscript(file: UploadFile = File(...), title: str = Form("Untitled Manuscript")):
    if not file.filename.endswith('.txt'):
        raise HTTPException(400, "Only .txt files are supported")
    content = await file.read()
    raw_text = content.decode('utf-8', errors='replace').strip()
    if not raw_text:
        raise HTTPException(400, "File is empty")
    return await create_manuscript(ManuscriptCreate(title=title or file.filename, raw_text=raw_text))

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

READER_ARCHETYPES = [
    {
        "archetype": "analytical",
        "description": "Focuses on plot logic, narrative structure, and consistency.",
        "temperature": 0.5,
        "default_instructions": "You focus on plot logic and structure. You notice when cause and effect don't connect, when timelines feel off, or when a character's decision contradicts what you know about them. You tend to think a few steps ahead."
    },
    {
        "archetype": "emotional",
        "description": "Reacts to emotional resonance, character relationships, and feeling.",
        "temperature": 0.9,
        "default_instructions": "You read for emotional connection first, analysis second. You track how characters make you feel and whether the story earns its emotional moments. You notice when something feels manipulative versus genuinely moving."
    },
    {
        "archetype": "casual",
        "description": "Reads for pure entertainment and vibes.",
        "temperature": 0.9,
        "default_instructions": "You read for fun and don't overthink things. You care about whether you're entertained and whether characters feel like people you'd want to know. You lose interest fast if the pacing drags."
    },
    {
        "archetype": "skeptical",
        "description": "Hard to please. Questions everything.",
        "temperature": 0.7,
        "default_instructions": "You don't trust the narrator or the author easily. You question character motivations, look for inconsistencies, and assume nothing is accidental. You're the reader who catches plot holes."
    },
    {
        "archetype": "genre_savvy",
        "description": "Deeply familiar with genre conventions. Compares to published books.",
        "temperature": 0.7,
        "default_instructions": "You've read hundreds of books in this genre. You constantly compare what you're reading to other works. You notice tropes being used well or poorly, and you can tell when a twist is coming because you've seen the setup before."
    }
]

async def generate_single_persona(archetype_info: Dict, genre: str, audience: str, avatar_index: int, manuscript_id: str) -> Dict:
    system = f"""You are a creative writing assistant. Generate a realistic reader persona for a book club member.
Return ONLY a valid JSON object (no markdown):
{{
  "name": "full name (diverse, realistic)",
  "age": 35,
  "occupation": "specific occupation",
  "reading_habits": "describe reading habits and genre preferences in one sentence",
  "favorite_genres": "2-3 genres they love",
  "genre_preferences": "specific subgenre or style preferences",
  "reading_priority": "what they most care about in a book (one sentence)",
  "liked_tropes": ["trope1", "trope2", "trope3"],
  "disliked_tropes": ["trope1", "trope2"],
  "voice_style": "how they express themselves (e.g. measured and precise, warm and chatty)",
  "quote": "a one-line quote in their voice about what makes or breaks a book",
  "personality_specific_instructions": "2-3 sentences describing their unique analytical lens as a reader — what they notice, how they process, what they're watching for"
}}"""

    chat = make_chat(system)
    response = await chat.send_message(UserMessage(
        text=f"Create a {archetype_info['archetype']} reader persona for a {genre} novel targeting {audience}. Make them feel like a real, specific person with a distinct reading lens."
    ))

    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        data = json.loads(clean)
    except Exception:
        data = {}

    def _coerce(val, default=""):
        if isinstance(val, list): return ", ".join(str(x) for x in val)
        return val if isinstance(val, str) else default

    return {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "name": data.get("name", f"Reader {avatar_index + 1}"),
        "age": data.get("age", 35) if isinstance(data.get("age"), int) else 35,
        "occupation": _coerce(data.get("occupation"), "Reader"),
        "personality": archetype_info["archetype"],
        "reading_habits": _coerce(data.get("reading_habits"), "Reads widely across genres"),
        "favorite_genres": _coerce(data.get("favorite_genres"), genre),
        "genre_preferences": _coerce(data.get("genre_preferences"), ""),
        "reading_priority": _coerce(data.get("reading_priority"), "A compelling story"),
        "liked_tropes": data.get("liked_tropes", []) if isinstance(data.get("liked_tropes"), list) else [],
        "disliked_tropes": data.get("disliked_tropes", []) if isinstance(data.get("disliked_tropes"), list) else [],
        "voice_style": _coerce(data.get("voice_style"), "thoughtful and measured"),
        "temperature": archetype_info["temperature"],
        "quote": _coerce(data.get("quote"), "A good story makes me forget the world."),
        "avatar_index": avatar_index,
        "personality_specific_instructions": _coerce(data.get("personality_specific_instructions"), archetype_info["default_instructions"]),
        "created_at": now_iso()
    }

@api_router.get("/manuscripts/{manuscript_id}/personas", response_model=List[ReaderPersonaResponse])
async def get_personas(manuscript_id: str):
    personas = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if not personas:
        manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
        if not manuscript:
            raise HTTPException(404, "Manuscript not found")
        return await _generate_all_personas(manuscript_id, manuscript.get("genre", "Fiction"), manuscript.get("target_audience", "General readers"))
    return [ReaderPersonaResponse(**p) for p in personas]

async def _generate_all_personas(manuscript_id: str, genre: str, audience: str) -> List[ReaderPersonaResponse]:
    await db.reader_personas.delete_many({"manuscript_id": manuscript_id})
    tasks = [generate_single_persona(a, genre, audience, i, manuscript_id) for i, a in enumerate(READER_ARCHETYPES)]
    personas = await asyncio.gather(*tasks)
    if personas:
        await db.reader_personas.insert_many([{**p} for p in personas])
    return [ReaderPersonaResponse(**p) for p in personas]

@api_router.post("/manuscripts/{manuscript_id}/personas/regenerate")
async def regenerate_personas(manuscript_id: str, req: RegenerateRequest):
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")
    genre = manuscript.get("genre", "Fiction")
    audience = manuscript.get("target_audience", "General readers")

    if req.reader_id:
        existing = await db.reader_personas.find_one({"id": req.reader_id, "manuscript_id": manuscript_id}, {"_id": 0})
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
        return await _generate_all_personas(manuscript_id, genre, audience)

# ─── Reading: Inline Annotation Format ───────────────────────────────────────

def build_reader_system_prompt(reader: Dict, genre: str, section_number: int, memory_str: str, numbered_text: str, line_start: int, line_end: int) -> str:
    return f"""You are {reader['name']}, {reader['age']}, a {reader['occupation']} who reads {reader.get('reading_habits', '')}.
You love {reader.get('favorite_genres', genre)} with {reader.get('genre_preferences', 'a focus on character')}.
{reader.get('reading_priority', 'You care about a compelling story.')}.

As you read, you:
- Notice when a character's choice feels true or false to who they are
- Compare moments to other books you've read (sometimes aloud in your head)
- Remember small details and wonder if they'll matter later
- React emotionally before thinking critically
- Mix praise and criticism naturally — you're honest but fair
- Express uncertainty when you're guessing
- May interpret or analyze the text, but be realistic for a human who's reading
- May generate fan theories based on earlier information

{reader.get('personality_specific_instructions', '')}

You are reading a {genre} manuscript, section {section_number}.

Here is what you remember from previous sections:
{memory_str}

---

OUTPUT FORMAT:

You are leaving comments on specific lines as you read, like margin notes on a manuscript.
Do NOT quote the text back. Reference where you are by line number only.

Lines in this section are numbered {line_start} to {line_end}.

Respond ONLY with a valid JSON object in this exact structure:

{{
  "inline_comments": [
    {{
      "line": <integer line number between {line_start} and {line_end}>,
      "type": "reaction" | "prediction" | "confusion" | "critique" | "praise" | "theory" | "comparison",
      "comment": "<your thought in 1-3 sentences, in your natural voice>"
    }}
  ],
  "section_reflection": "<optional 2-4 sentences about the section as a whole, or null>",
  "memory_update": {{
    "plot_events": ["event 1", "event 2"],
    "character_notes": {{"character_name": "updated impression"}},
    "predictions": [{{"prediction": "what you think will happen", "confidence": "high/medium/low", "evidence": "why"}}],
    "questions": ["unresolved question"],
    "emotional_state": "how you're feeling about the story right now",
    "memorable_quotes": ["any standout lines"]
  }}
}}

RULES:
- Comment only where you naturally have a reaction. Typically 4-10 comments per section, sometimes fewer.
- Keep each comment to 1-3 sentences. These are margin notes, not essays.
- Do not quote the text in your comments.
- Use the "type" field honestly.
- section_reflection should be null most of the time.
- Fan theories go in inline_comments as type "theory" AND in memory_update predictions.
- Use plain language with only commas and periods. No exclamation marks, no all caps.

Here is the section text (read it carefully):

{numbered_text}"""

async def get_reader_inline_reaction(
    reader: Dict,
    section: Dict,
    genre: str,
    manuscript_id: str
) -> Dict:
    section_number = section["section_number"]
    line_start = section["line_start"]
    line_end = section["line_end"]
    paragraph_lines = section.get("paragraph_lines", [])

    # Build numbered text for the reader
    numbered_text = "\n".join(f"{pl['line']}: {pl['text']}" for pl in paragraph_lines)

    # Get accumulated memory
    memories = await db.reader_memories.find(
        {"manuscript_id": manuscript_id, "reader_id": reader["id"]},
        {"_id": 0}
    ).sort("section_number", 1).to_list(100)
    compressed_memory = compress_memory(memories, reader.get("personality", ""))
    memory_str = json.dumps(compressed_memory, indent=2) if compressed_memory else "No previous sections read yet."

    system_prompt = build_reader_system_prompt(
        reader, genre, section_number, memory_str, numbered_text, line_start, line_end
    )

    chat = make_chat(system_prompt)
    response = await chat.send_message(UserMessage(
        text=f"Read section {section_number} and leave your inline comments."
    ))

    # Parse JSON response
    parsed = {}
    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        parsed = json.loads(clean)
    except Exception:
        # Try to find JSON in response
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                parsed = json.loads(response[start:end])
        except Exception as e:
            logger.error(f"Failed to parse reader response for {reader.get('name')}: {e}")
            parsed = {"inline_comments": [], "section_reflection": None, "memory_update": {}}

    inline_comments = validate_inline_comments(
        parsed.get("inline_comments", []), line_start, line_end
    )
    section_reflection = parsed.get("section_reflection")
    memory_update = parsed.get("memory_update", {})

    # Save reaction
    reaction_doc = {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "reader_id": reader["id"],
        "reader_name": reader["name"],
        "section_number": section_number,
        "inline_comments": inline_comments,
        "section_reflection": section_reflection,
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
        "section_number": section_number,
        "inline_comments": inline_comments,
        "section_reflection": section_reflection,
        "reaction_id": reaction_doc["id"]
    }

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
            yield f"data: {json.dumps({'type': 'section_start', 'section_number': sn, 'total_sections': total_sections})}\n\n"

            async def process_reader(reader, sec=section):
                try:
                    result = await get_reader_inline_reaction(reader, sec, genre, manuscript_id)
                    return {"type": "reader_complete", **result}
                except Exception as e:
                    logger.error(f"Error: reader {reader.get('name')} on section {sec['section_number']}: {e}")
                    return {
                        "type": "reader_error",
                        "reader_id": reader["id"],
                        "reader_name": reader.get("name", "Unknown"),
                        "section_number": sec["section_number"],
                        "error": str(e)
                    }

            tasks = [process_reader(reader) for reader in readers]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                yield f"data: {json.dumps(result)}\n\n"

            yield f"data: {json.dumps({'type': 'section_complete', 'section_number': sn})}\n\n"

        yield f"data: {json.dumps({'type': 'all_complete'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )

@api_router.get("/manuscripts/{manuscript_id}/all-reactions")
async def get_all_reactions(manuscript_id: str):
    """Return all reactions for a manuscript (for resuming existing sessions)."""
    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id}, {"_id": 0}
    ).sort("section_number", 1).to_list(1000)
    return reactions

@api_router.get("/manuscripts/{manuscript_id}/reading-status")
async def get_reading_status(manuscript_id: str):
    """Return whether all sections have been fully read by all readers."""
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise HTTPException(404, "Manuscript not found")
    total_sections = manuscript.get("total_sections", 0)
    readers = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    total_readers = len(readers)
    reactions = await db.reader_reactions.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(1000)
    sections_covered = set(r.get("section_number") for r in reactions)
    complete = (
        total_sections > 0 and
        total_readers > 0 and
        len(sections_covered) >= total_sections and
        len(reactions) >= total_sections * total_readers
    )
    return {
        "complete": complete,
        "total_sections": total_sections,
        "total_readers": total_readers,
        "reactions_count": len(reactions),
        "expected_reactions": total_sections * total_readers,
        "sections_covered": sorted(sections_covered)
    }

# Legacy endpoint for compatibility
@api_router.get("/manuscripts/{manuscript_id}/reactions/{section_number}")
async def get_reactions(manuscript_id: str, section_number: int):
    reactions = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id, "section_number": section_number}, {"_id": 0}
    ).to_list(10)
    return reactions

# ─── Editor Report ────────────────────────────────────────────────────────────

@api_router.post("/manuscripts/{manuscript_id}/editor-report")
async def generate_editor_report(manuscript_id: str):
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

    # Verify all sections have been read by all readers
    if total_sections > 0 and total_readers > 0:
        sections_covered = set(r.get("section_number") for r in reactions)
        expected_sections = set(range(1, total_sections + 1))
        missing_sections = expected_sections - sections_covered
        if missing_sections:
            raise HTTPException(400, f"Reading is not complete. Sections {sorted(missing_sections)} have not been read yet.")
        expected_total = total_sections * total_readers
        if len(reactions) < expected_total:
            raise HTTPException(400, f"Reading is not complete. {len(reactions)} of {expected_total} reader-section combinations finished.")


    # Build reactions summary from inline comments
    reactions_text = ""
    section_comment_counts = {}
    for r in reactions:
        sn = r.get("section_number", 0)
        reader_name = r.get("reader_name", "Reader")
        comments = r.get("inline_comments", [])
        reflection = r.get("section_reflection", "")
        section_comment_counts[sn] = section_comment_counts.get(sn, 0) + len(comments)

        if comments or reflection:
            reactions_text += f"\n[Section {sn}] {reader_name}:\n"
            for c in comments[:8]:
                reactions_text += f"  [{c.get('type','reaction')}] {c.get('comment','')}\n"
            if reflection:
                reactions_text += f"  [Reflection] {reflection}\n"

    editor_system = f"""You are a professional developmental editor with 20 years of experience.
You have received inline reader annotations for a {manuscript.get('genre', 'fiction')} manuscript from 5 beta readers.
Synthesize their feedback into a professional editorial report.
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

    chat = make_chat(editor_system)
    response = await chat.send_message(UserMessage(
        text=f"Reader annotations:\n{reactions_text[:8000]}\n\nGenerate the editorial report."
    ))

    report_data = {}
    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        report_data = json.loads(clean)
    except Exception as e:
        logger.error(f"Failed to parse editor report: {e}")
        report_data = {
            "executive_summary": ["The manuscript received reactions from the panel.", "Further development is recommended."],
            "consensus_findings": [],
            "character_impressions": [],
            "prediction_accuracy": [],
            "engagement_by_section": [{"section": k, "engagement_score": min(100, v * 8), "note": ""} for k, v in section_comment_counts.items()],
            "recommendations": [{"priority": "medium", "title": "Continue revision", "detail": "Address reader concerns and iterate."}]
        }

    if not report_data.get("engagement_by_section"):
        report_data["engagement_by_section"] = [
            {"section": k, "engagement_score": min(100, v * 8), "note": ""}
            for k, v in sorted(section_comment_counts.items())
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
    report = await db.editor_reports.find_one({"manuscript_id": manuscript_id}, {"_id": 0})
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
