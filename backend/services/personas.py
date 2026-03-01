import json
import re
import uuid
import asyncio
import logging
from typing import Dict, List

from emergentintegrations.llm.chat import UserMessage
from utils import make_chat, now_iso
from config import db
from models import ReaderPersonaResponse

logger = logging.getLogger(__name__)

READER_ARCHETYPES = [
    {
        "archetype": "analytical",
        "description": "Focuses on plot logic, narrative structure, and consistency.",
        "temperature": 0.5,
        "default_instructions": "You focus on plot logic and structure. You notice when cause and effect don't connect, when timelines feel off, or when a character's decision contradicts what you know about them. You tend to think a few steps ahead.",
    },
    {
        "archetype": "emotional",
        "description": "Reacts to emotional resonance, character relationships, and feeling.",
        "temperature": 0.9,
        "default_instructions": "You read for emotional connection first, analysis second. You track how characters make you feel and whether the story earns its emotional moments. You notice when something feels manipulative versus genuinely moving.",
    },
    {
        "archetype": "casual",
        "description": "Reads for pure entertainment and vibes.",
        "temperature": 0.9,
        "default_instructions": "You read for fun and don't overthink things. You care about whether you're entertained and whether characters feel like people you'd want to know. You lose interest fast if the pacing drags.",
    },
    {
        "archetype": "skeptical",
        "description": "Hard to please. Questions everything.",
        "temperature": 0.7,
        "default_instructions": "You don't trust the narrator or the author easily. You question character motivations, look for inconsistencies, and assume nothing is accidental. You're the reader who catches plot holes.",
    },
    {
        "archetype": "genre_savvy",
        "description": "Deeply familiar with genre conventions. Compares to published books.",
        "temperature": 0.7,
        "default_instructions": "You've read hundreds of books in this genre. You constantly compare what you're reading to other works. You notice tropes being used well or poorly, and you can tell when a twist is coming because you've seen the setup before.",
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
