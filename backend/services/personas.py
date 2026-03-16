import json
import re
import uuid
import asyncio
import logging
from typing import Dict, List

from utils import make_chat, now_iso, UserMessage
from config import db
from models import ReaderPersonaResponse
from services.readers import DEFAULT_ATTENTION_BY_AVATAR

logger = logging.getLogger(__name__)

# Fallback full names; order matches READER_ARCHETYPES: May, James, Lena, Priya, Diego
FALLBACK_NAMES = [
    "Maya Okonkwo",
    "James Chen",
    "Lena Kowalski",
    "Priya Sharma",
    "Diego Reyes",
]

# Target age ranges by manuscript age_range (min, max inclusive)
AGE_RANGE_BY_LABEL = {
    "middle grade": (8, 12),
    "middle-grade": (8, 12),
    "mg": (8, 12),
    "ya": (14, 22),
    "young adult": (14, 22),
    "new adult": (18, 28),
    "na": (18, 28),
    "adult": (25, 65),
}
DEFAULT_AGE_RANGE = (25, 65)


def _age_range_for_audience(age_range: str) -> tuple:
    """Return (min_age, max_age) for a given age_range label."""
    if not age_range or not isinstance(age_range, str):
        return DEFAULT_AGE_RANGE
    key = age_range.strip().lower()
    return AGE_RANGE_BY_LABEL.get(key, DEFAULT_AGE_RANGE)


def _varied_age_for_reader(min_age: int, max_age: int, avatar_index: int) -> int:
    """Pick a different age per avatar_index within [min_age, max_age]."""
    span = max(1, max_age - min_age + 1)
    # Spread 5 readers across the range (e.g. 25,35,45,55,65 for Adult)
    step = max(1, span // 5)
    offset = min(avatar_index * step, span - 1)
    return min_age + offset


# Preset order for UI: May (emotional), James (plot), Lena (skeptical), Priya (genre-savvy), Diego (casual).
# Default 3 readers = indices 0, 1, 2.
READER_ARCHETYPES = [
    {
        "archetype": "emotional",
        "description": "Reads for emotional connection",
        "temperature": 0.9,
        "default_instructions": "You read for emotional connection first. You track how characters make you feel and whether the story earns its emotional beats. You notice when a character choice feels true or false to who they are. You compare moments to other books when it genuinely clicks. You catch when something feels manipulative versus genuinely moving. You're warm but you don't sugarcoat. You might say things like \"that line hit me\" or \"I don't buy this reaction from her.\"",
    },
    {
        "archetype": "analytical",
        "description": "Focuses on plot and structure",
        "temperature": 0.5,
        "default_instructions": "You focus on plot logic and narrative structure. You notice when cause and effect disconnect, when timelines feel off, when a decision contradicts established character behavior. You track setups and payoffs closely. You're the reader who notices the gun on the mantelpiece in act one. You respect tight plotting and get annoyed by convenience or coincidence that lets characters off the hook. You're direct and dry.",
    },
    {
        "archetype": "skeptical",
        "description": "Questions everything",
        "temperature": 0.6,
        "default_instructions": "You don't trust easily. Not the narrator, not the author, not the other characters. You question motivations, look for inconsistencies, and assume nothing is accidental. You catch plot holes, timeline errors, and moments where characters act out of convenience rather than logic. You're the reader who says \"wait, didn't they say the opposite three chapters ago?\" You give credit when the text earns your trust.",
    },
    {
        "archetype": "genre_savvy",
        "description": "Deeply familiar with genre",
        "temperature": 0.7,
        "default_instructions": "You've read hundreds of books in this genre. You constantly compare to other works, notice tropes being used well or poorly, and can usually tell when a twist is coming because you've seen the setup before. You appreciate subversion and get bored when a story follows the template too closely. You reference specific books and authors by name. You're not snobby, you just have a lot of context.",
    },
    {
        "archetype": "casual",
        "description": "Reads for entertainment",
        "temperature": 0.85,
        "default_instructions": "You read for fun and don't overthink it. You care about pacing, entertainment, and whether characters feel like real people. You lose interest fast if things drag. You're the reader who says \"just get to the point\" during slow exposition. When something lands, you're fully in. You don't use literary terminology. You say what worked and what didn't in the most direct way possible.",
    },
]

DEFAULT_READER_COUNT = 3
MAX_READERS = 5


async def generate_single_persona(
    archetype_info: Dict,
    genre: str,
    audience: str,
    age_range_label: str,
    avatar_index: int,
    manuscript_id: str,
) -> Dict:
    min_age, max_age = _age_range_for_audience(age_range_label)
    default_age = _varied_age_for_reader(min_age, max_age, avatar_index)

    system = """You are a creative writing assistant. Generate a realistic reader persona for a book club member.
You MUST return a valid JSON object (no markdown). Every field must be specific and non-generic.

REQUIREMENTS:
- "name": A real-sounding full name (first and last). Use a diverse name; do NOT use "Reader" or a number.
- "age": An integer within the target age range you are given. Each persona should feel like a distinct person.
- "occupation", "reading_habits", "favorite_genres", "genre_preferences", "reading_priority": Be specific (e.g. "teaches high school English", "reads 2 books a month, mostly on commute", "literary fiction and slow-burn thrillers"). Do NOT leave generic like "Reader" or "A compelling story".
- "liked_tropes" and "disliked_tropes": Arrays of specific tropes (e.g. "enemies to lovers", "chosen one").
- "quote": One sentence in their voice about what makes or breaks a book for them.
- "persona_block": 4-6 sentences for the reader prompt. Style: Start with "You are [Name], [age], a [occupation] who..." and one line on reading habits. Then 2-3 sentences with "You tend to..." for their subtle lens (e.g. notice subtext, notice pacing, notice when they're bored). Add "You don't always comment on it. Sometimes you just note it and keep reading." or similar. End with one grounding sentence: "You're just a reader. You notice what any thoughtful person would. Your personality comes through in how you say things, not in having unusual opinions about everything." No "lens" lists; write flowing prose. This block is used as-is in the system prompt.
- You are generating one reader in a panel. Each reader in the panel has a different "attention mode" (what they naturally look at). This reader's mode will be assigned by the system; write the persona_block so it fits a reader who tends to focus on that mode. The modes are: SUBTEXT (what's not said, gaps, silence), MOMENTUM (pacing, where the chapter moves), LANGUAGE (sentences, word choice, rhythm), LOGIC (what's established vs withheld, consistency), EMOTIONAL_BEAT (emotional arc of scenes), CHARACTER (what people do vs what narrator says). Don't name the mode in the block; just write a coherent reader who would naturally lean that way.

Return ONLY this JSON (no other text):
{{
  "name": "First Last",
  "age": 30,
  "occupation": "specific job or role",
  "reading_habits": "one sentence, specific",
  "favorite_genres": "2-3 genres they love",
  "genre_preferences": "subgenres or styles they prefer",
  "reading_priority": "one sentence, what they care about most",
  "liked_tropes": ["trope1", "trope2", "trope3"],
  "disliked_tropes": ["trope1", "trope2"],
  "voice_style": "how they express themselves",
  "quote": "one line in their voice",
  "personality_specific_instructions": "2-3 sentences: their unique lens as a reader",
  "persona_block": "4-6 sentences in the style described above, flowing prose, no bullet lists"
}}"""

    user_text = (
        f"Create a {archetype_info['archetype']} reader persona for a {genre} novel. "
        f"Target audience: {audience}. "
        f"Age range for this audience: {age_range_label} (readers should be between {min_age} and {max_age} years old). "
        f"Set this persona's age to a specific number between {min_age} and {max_age} that fits the audience. "
        f"Give them a real full name and specific preferences—no generic placeholders."
    )
    chat = make_chat(system)
    response = await chat.send_message(UserMessage(text=user_text))

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
    # Reject generic or empty names; use fallback
    if not raw_name or raw_name.lower().startswith("reader") or raw_name.isdigit():
        name = FALLBACK_NAMES[avatar_index % len(FALLBACK_NAMES)]
    else:
        name = str(raw_name).strip()
    name = (name or FALLBACK_NAMES[avatar_index % len(FALLBACK_NAMES)]).strip()

    # Parse age: must be int in [min_age, max_age]; otherwise use varied default
    raw_age = data.get("age")
    try:
        age_val = int(float(raw_age)) if raw_age is not None else default_age
    except (TypeError, ValueError):
        age_val = default_age
    age = max(min_age, min(max_age, age_val)) if (min_age <= age_val <= max_age) else default_age

    # Archetype-based defaults when LLM returns empty or generic
    arch = archetype_info.get("archetype", "")
    default_occupations = {
        "analytical": "editor or copywriter",
        "emotional": "counselor or teacher",
        "genre_savvy": "bookseller or librarian",
        "casual": "works in tech or retail",
        "skeptical": "lawyer or researcher",
    }
    default_priorities = {
        "analytical": "Plot that holds together and pays off its setups.",
        "emotional": "Characters I care about and moments that earn their weight.",
        "genre_savvy": "Fresh takes on familiar tropes.",
        "casual": "Pacing and characters that feel real.",
        "skeptical": "Internal logic and consistency.",
    }
    occ = _coerce(data.get("occupation"), "")
    if not occ or occ.lower() == "reader":
        occ = default_occupations.get(arch, "reader")
    prio = _coerce(data.get("reading_priority"), "")
    if not prio or prio.lower() == "a compelling story":
        prio = default_priorities.get(arch, "A compelling story.")

    persona_block = _coerce(data.get("persona_block"), "").strip()
    if not persona_block:
        # Fallback: build a short block from fields so reader prompt still has something
        persona_block = f"You are {name}, {age}, a {occ}. {_coerce(data.get('reading_habits'), 'Reads widely.')} You love {_coerce(data.get('favorite_genres'), genre)}. You're a normal reader with opinions. Your personality comes through in how you say things."
    # Assign this reader a distinct attention mode (no duplicates in panel)
    attention_mode = DEFAULT_ATTENTION_BY_AVATAR[avatar_index % len(DEFAULT_ATTENTION_BY_AVATAR)]
    return {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "name": name,
        "age": age,
        "occupation": occ,
        "personality": archetype_info["archetype"],
        "reading_habits": _coerce(data.get("reading_habits"), "Reads widely across genres"),
        "favorite_genres": _coerce(data.get("favorite_genres"), genre),
        "genre_preferences": _coerce(data.get("genre_preferences"), ""),
        "reading_priority": prio,
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
        "persona_block": persona_block,
        "attention_mode": attention_mode,
        "created_at": now_iso(),
    }


async def generate_all_personas(
    manuscript_id: str,
    genre: str,
    audience: str,
    age_range: str = "Adult",
    count: int = 5,
) -> List[ReaderPersonaResponse]:
    """Generate up to `count` reader personas (default 5). Uses first `count` from READER_ARCHETYPES."""
    if count < 1 or count > MAX_READERS:
        count = DEFAULT_READER_COUNT
    await db.reader_personas.delete_many({"manuscript_id": manuscript_id})
    archetypes = READER_ARCHETYPES[:count]
    tasks = [
        generate_single_persona(a, genre, audience, age_range or "Adult", i, manuscript_id)
        for i, a in enumerate(archetypes)
    ]
    personas = await asyncio.gather(*tasks)
    if personas:
        await db.reader_personas.insert_many([{**p} for p in personas])
    return [ReaderPersonaResponse(**p) for p in personas]


async def add_one_persona(manuscript_id: str) -> ReaderPersonaResponse:
    """Add the next reader from the preset list. Returns 400 if already 5 readers."""
    existing = await db.reader_personas.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10)
    if len(existing) >= MAX_READERS:
        raise ValueError(f"Maximum {MAX_READERS} readers allowed.")
    manuscript = await db.manuscripts.find_one({"id": manuscript_id}, {"_id": 0})
    if not manuscript:
        raise ValueError("Manuscript not found")
    genre = manuscript.get("genre", "Fiction")
    audience = manuscript.get("target_audience", "General readers")
    age_range = manuscript.get("age_range", "Adult")
    avatar_index = len(existing)
    archetype = READER_ARCHETYPES[avatar_index]
    persona = await generate_single_persona(
        archetype, genre, audience, age_range, avatar_index, manuscript_id
    )
    await db.reader_personas.insert_one({**persona})
    return ReaderPersonaResponse(**persona)
