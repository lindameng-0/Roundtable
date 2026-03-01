import json
import re
import uuid
import asyncio
import logging
from typing import Dict, List

from utils import make_chat, now_iso, UserMessage
from config import db
from models import ReaderPersonaResponse

logger = logging.getLogger(__name__)

READER_ARCHETYPES = [
    {
        "archetype": "analytical",
        "description": "Focuses on plot logic, narrative structure, and consistency. (James-style.)",
        "temperature": 0.5,
        "default_instructions": "You focus on plot logic and narrative structure. You notice when cause and effect disconnect, when timelines feel off, when a decision contradicts established character behavior. You track setups and payoffs closely. You're the reader who notices the gun on the mantelpiece in act one. You respect tight plotting and get annoyed by convenience or coincidence that lets characters off the hook. You're direct and dry.",
    },
    {
        "archetype": "emotional",
        "description": "Reacts to emotional resonance, character relationships, and feeling. (May-style.)",
        "temperature": 0.9,
        "default_instructions": "You read for emotional connection first. You track how characters make you feel and whether the story earns its emotional beats. You notice when a character choice feels true or false to who they are. You compare moments to other books when it genuinely clicks. You catch when something feels manipulative versus genuinely moving. You're warm but you don't sugarcoat. You might say things like \"that line hit me\" or \"I don't buy this reaction from her.\"",
    },
    {
        "archetype": "genre_savvy",
        "description": "Deeply familiar with genre conventions. Compares to published books. (Priya-style.)",
        "temperature": 0.7,
        "default_instructions": "You've read hundreds of books in this genre. You constantly compare to other works, notice tropes being used well or poorly, and can usually tell when a twist is coming because you've seen the setup before. You appreciate subversion and get bored when a story follows the template too closely. You reference specific books and authors by name. You're not snobby, you just have a lot of context.",
    },
    {
        "archetype": "casual",
        "description": "Reads for pure entertainment and vibes. (Diego-style.)",
        "temperature": 0.85,
        "default_instructions": "You read for fun and don't overthink it. You care about pacing, entertainment, and whether characters feel like real people. You lose interest fast if things drag. You're the reader who says \"just get to the point\" during slow exposition. When something lands, you're fully in. You don't use literary terminology. You say what worked and what didn't in the most direct way possible.",
    },
    {
        "archetype": "skeptical",
        "description": "Hard to please. Questions everything. (Lena-style.)",
        "temperature": 0.6,
        "default_instructions": "You don't trust easily. Not the narrator, not the author, not the other characters. You question motivations, look for inconsistencies, and assume nothing is accidental. You catch plot holes, timeline errors, and moments where characters act out of convenience rather than logic. You're the reader who says \"wait, didn't they say the opposite three chapters ago?\" You give credit when the text earns your trust.",
    },
]


async def generate_single_persona(
    archetype_info: Dict,
    genre: str,
    audience: str,
    avatar_index: int,
    manuscript_id: str,
) -> Dict:
    system = """You are a creative writing assistant. Generate a realistic reader persona for a book club member.
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
        if isinstance(val, list):
            return ", ".join(str(x) for x in val)
        return val if isinstance(val, str) else default

    raw_name = data.get("name")
    if isinstance(raw_name, str):
        raw_name = raw_name.strip()
    else:
        raw_name = str(raw_name).strip() if raw_name is not None else ""
    name = raw_name if raw_name else f"Reader {avatar_index + 1}"
    # Ensure we never store a non-string (e.g. LLM returns a number)
    name = str(name).strip() or f"Reader {avatar_index + 1}"

    return {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "name": name,
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
        "personality_specific_instructions": _coerce(
            data.get("personality_specific_instructions"),
            archetype_info["default_instructions"],
        ),
        "created_at": now_iso(),
    }


async def generate_all_personas(
    manuscript_id: str, genre: str, audience: str
) -> List[ReaderPersonaResponse]:
    await db.reader_personas.delete_many({"manuscript_id": manuscript_id})
    tasks = [
        generate_single_persona(a, genre, audience, i, manuscript_id)
        for i, a in enumerate(READER_ARCHETYPES)
    ]
    personas = await asyncio.gather(*tasks)
    if personas:
        await db.reader_personas.insert_many([{**p} for p in personas])
    return [ReaderPersonaResponse(**p) for p in personas]
