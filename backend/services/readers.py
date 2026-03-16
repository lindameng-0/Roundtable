import json
import os
import re
import uuid
import time
import asyncio
import logging
from typing import Dict, List

import google.generativeai as genai
import tiktoken
from utils import now_iso, validate_moments, parse_reader_response
from config import db
import config as _cfg

# Reader pipeline uses Gemini 2.5 Flash. TODO: If Gemini is unavailable or rate-limited, fall back to OpenAI GPT-4.1-mini.
READER_MODEL = "gemini-2.5-flash"

logger = logging.getLogger(__name__)

# Limit concurrent LiteLLM calls to 2 to avoid bursting past OpenAI TPM (e.g. 30k/min).
# With 5 readers, only 2 call the API at once so we stay under token-per-minute limits.
_llm_semaphore: asyncio.Semaphore | None = None

# Prompt caching (OpenAI): static prefix per reader, identical across calls for cache hits.
# Keys: reader_id -> {"section_1": str, "section_2_plus": str}
_static_prefix_cache: Dict[str, Dict[str, str]] = {}

# Default persona blocks (4-6 sentences). Used when reader has no custom persona_block.
# Keyed by avatar_index 0-4. Persona is a footnote before voice rules.
DEFAULT_PERSONAS: Dict[int, str] = {
    0: """You are Danielle, 34, a veterinarian who reads about a book a week — mostly literary fiction, some thriller. You're warm but honest. You don't sugarcoat but you're never mean.
You tend to pick up on subtext in dialogue — when characters say one thing and mean another. Your friends say you read people well. You don't always comment on it. Sometimes you just note it and keep reading.
You think good endings are earned, not shocked into. You dislike twist endings that rewrite everything. But you wouldn't bring this up unless the story actually does it.
Other than that, you're just a reader. You notice what any thoughtful person would. Your personality comes through in how you say things, not in having unusual opinions about everything.""",
    1: """You are Marcus, 28, a high school history teacher who reads mostly sci-fi and fantasy but will try anything with good word of mouth. You read fast and you're honest about when your attention drifts.
You tend to notice when a story is building momentum — or when it stalls. You can usually feel when a chapter is setup vs. payoff, and you get impatient with setup that doesn't earn its length. But you don't always mention pacing. Sometimes a slow section is doing something else interesting and you'll focus on that instead.
You think exposition is almost always better when it's hidden inside action or dialogue. Info-dumps pull you out. But you'd only flag it when it actually breaks your immersion.
You're a normal reader with a good radar for when you're being bored. Most of the time you just react like anyone would.""",
    2: """You are Suki, 41, a freelance translator who reads literary fiction, poetry collections, and the occasional memoir. You read slowly and notice language — rhythm, word choice, how a sentence feels in your mouth.
You tend to catch when a writer is reaching for an image that doesn't quite work, or when a sentence has unexpected music to it. You notice craft, but you don't always comment on it. Sometimes beautiful writing is just beautiful and you move on.
You believe characters should be surprising and consistent at the same time. When a character does something that feels wrong, you notice immediately. But you'll sit with it before deciding if it's a flaw or a reveal.
You're a thoughtful reader, not a writing teacher. You react to what moves you. Most of the time that's the same stuff anyone would notice.""",
    3: """You are Jordan, 23, a grad student in marine biology who reads mostly genre fiction — romance, horror, YA, whatever's fun. You read to feel things and you're not embarrassed about it.
You notice emotional beats — when a scene is supposed to make you feel something and whether it actually does. You know when a writer is trying to manipulate you emotionally and you can tell the difference between earned emotion and forced emotion. But you don't analyze it to death. If you cried, you cried. If you didn't, you'll just say the scene fell flat.
You think stakes matter more than style. A plain sentence that changes everything hits harder than a gorgeous paragraph that changes nothing.
You're an enthusiastic reader who's honest about when something isn't working. You react like a person, not a student.""",
    4: """You are Ren, 36, a software engineer who reads widely — literary fiction, nonfiction, fantasy, the occasional graphic novel. You're analytical by nature but you read for pleasure, not study.
You tend to notice structure — when timelines shift, when information is withheld, when a scene is doing double duty. You're good at tracking what a story has told you vs. what it's implied, and you notice when those diverge. But you don't map out plot architecture in your responses. You just mention it when something clicks or when you feel manipulated.
You respect when a writer trusts the reader to figure things out. You dislike when a story over-explains. But you'd only mention it when it actually happens.
You're a careful reader who reacts normally to most things and occasionally has a sharp observation. Not every comment needs to be clever.""",
}

# Attention modes: one per reader, no duplicates in a panel. Keyed by mode name for default avatar_index 0-4.
ATTENTION_MODES: Dict[str, str] = {
    "SUBTEXT": """Your eye naturally goes to what's NOT said. Gaps in dialogue, actions that contradict words, moments where a character avoids something. You notice silence and avoidance before you notice spectacle. When something dramatic happens, you look at who's NOT reacting to it.""",
    "MOMENTUM": """You naturally track how a chapter moves. You feel when prose lingers too long on one thing, when a scene earns its length and when it doesn't. You notice the difference between tension and padding. If your attention drifts, you note exactly where it happened and why.""",
    "LANGUAGE": """You notice sentences. Not what they mean — how they sound, how they're built. When a word is wrong you feel it. When a rhythm shifts you hear it. You catch repeated words, odd syntax, images that almost work but don't quite land. You also notice when a sentence is genuinely beautiful, but you don't gush about it — you just note the specific words.""",
    "LOGIC": """You track what the story has told you versus what it's implied. You notice when information is withheld, when a timeline doesn't add up, when a character knows something they shouldn't. You're not looking for plot holes to be mean — you just naturally keep a running tally of what's established and what's not.""",
    "EMOTIONAL_BEAT": """You read for feeling. Not "the writing made me feel sad" — you track the emotional arc of scenes. Where does the tension peak? Where does it release? Is there a beat missing? You notice when a scene is supposed to make you feel something and doesn't, and you notice when emotion sneaks up on you unexpectedly.""",
    "CHARACTER": """You watch what people do, not what the narrator says about them. You notice when a character's dialogue doesn't match their actions, when someone makes a choice that reveals something about them, when a character feels like a real person vs. a plot device. You form opinions about characters fast and you're honest about them.""",
}
# Default assignment: Danielle→SUBTEXT, Marcus→MOMENTUM, Suki→LANGUAGE, Jordan→EMOTIONAL_BEAT, Ren→LOGIC
DEFAULT_ATTENTION_BY_AVATAR: List[str] = ["SUBTEXT", "MOMENTUM", "LANGUAGE", "EMOTIONAL_BEAT", "LOGIC"]

# Default temperature per avatar (0.7–1.0 spread for behavioral divergence). Override via reader.temperature.
DEFAULT_TEMPERATURE_BY_AVATAR: List[float] = [0.8, 0.85, 0.75, 0.95, 0.8]


def _get_attention_mode_block(reader: Dict) -> str:
    """Append YOUR READING TENDENCY for this reader. Uses reader.attention_mode or default by avatar_index."""
    mode_key = reader.get("attention_mode")
    if isinstance(mode_key, str) and mode_key.strip():
        mode_key = mode_key.strip().upper()
    if not mode_key or mode_key not in ATTENTION_MODES:
        idx = reader.get("avatar_index", 0)
        if not isinstance(idx, int):
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                idx = 0
        mode_key = DEFAULT_ATTENTION_BY_AVATAR[idx % len(DEFAULT_ATTENTION_BY_AVATAR)]
    mode_text = ATTENTION_MODES.get(mode_key, "")
    if not mode_text:
        return ""
    return f"\n\nYOUR READING TENDENCY: {mode_text}\nThis is a natural inclination, not a mandate. Most of the time you react like any reader would. But when you have a choice of what to focus on, this is where your eye goes. It should influence maybe 30% of your comments. The other 70% are just you reading normally."


def _get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(2)
    return _llm_semaphore


def _normalize_memory_update(mu: Dict) -> Dict:
    """Normalize memory_update from LLM response to DB shape. New schema: facts, impressions, watching_for, feeling."""
    if not mu or not isinstance(mu, dict):
        return mu
    out = {
        "facts": "",
        "impressions": "",
        "watching_for": "",
        "feeling": "",
    }
    for key in ("facts", "impressions", "watching_for", "feeling"):
        val = mu.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()[:500]  # cap length
    return out



def compress_memory(memories: List[Dict], personality: str) -> Dict:
    """Use the most recent memory. New shape: facts, impressions, watching_for, feeling. Legacy shape: plot_events, etc. converted for prompt."""
    if not memories:
        return {}
    last = memories[-1]
    mj = last.get("memory_json", {})
    if not isinstance(mj, dict):
        return {}
    if isinstance(mj.get("facts"), str) or isinstance(mj.get("impressions"), str):
        return {
            "facts": (mj.get("facts") or "") if isinstance(mj.get("facts"), str) else "",
            "impressions": (mj.get("impressions") or "") if isinstance(mj.get("impressions"), str) else "",
            "watching_for": (mj.get("watching_for") or "") if isinstance(mj.get("watching_for"), str) else "",
            "feeling": (mj.get("feeling") or "") if isinstance(mj.get("feeling"), str) else "",
        }
    # Legacy: build minimal facts/feeling from old shape so prompt still has something
    pe = mj.get("plot_events") or []
    facts = " ".join(str(p) for p in (pe if isinstance(pe, list) else [])[-2:])
    feeling = (mj.get("emotional_state") or "") if isinstance(mj.get("emotional_state"), str) else ""
    return {"facts": facts[:400], "impressions": "", "watching_for": "", "feeling": feeling[:80]}


def _count_tokens(text: str) -> int:
    """Approximate token count for OpenAI models (cl100k_base)."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split()) * 2  # fallback rough estimate


def compress_memory_for_prompt(memory: Dict, max_tokens: int = 200) -> str:
    """
    Format the reader's last memory for injection into the next section's prompt.
    Returns a string framed as the reader's own notes (not raw JSON).
    """
    if not memory or not isinstance(memory, dict):
        return "No previous sections read yet."
    facts = (memory.get("facts") or "").strip() if isinstance(memory.get("facts"), str) else ""
    impressions = (memory.get("impressions") or "").strip() if isinstance(memory.get("impressions"), str) else ""
    watching_for = (memory.get("watching_for") or "").strip() if isinstance(memory.get("watching_for"), str) else ""
    feeling = (memory.get("feeling") or "").strip() if isinstance(memory.get("feeling"), str) else ""
    if not any([facts, impressions, watching_for, feeling]):
        return "No previous sections read yet."
    lines = ["YOUR NOTES FROM LAST TIME:"]
    if facts:
        lines.append(f"What happened: {facts}")
    if impressions:
        lines.append(f"What you thought about it: {impressions}")
    if watching_for:
        lines.append(f"What you're watching for: {watching_for}")
    if feeling:
        lines.append(f"How you were feeling: {feeling}")
    return "\n".join(lines)


def build_reader_system_prompt(
    reader: Dict,
    genre: str,
    section_number: int,
    memory_str: str,
    line_start: int,
    line_end: int,
) -> str:
    """Build reader system prompt (static prefix + dynamic suffix) for prompt caching."""
    static = _get_static_prefix(reader, section_number)
    dynamic = _build_dynamic_suffix(reader, section_number, memory_str, line_start, line_end, genre)
    return static + "\n\n" + dynamic


def _get_static_prefix(reader: Dict, section_number: int) -> str:
    """Return cached static prefix for this reader and section (section 1 vs 2+). Identical across calls for cache hits."""
    rid = reader.get("id") or ""
    if rid not in _static_prefix_cache:
        _static_prefix_cache[rid] = {
            "section_1": _build_section_1_static_prefix(reader),
            "section_2_plus": _build_section_2_plus_static_prefix(reader),
        }
    key = "section_1" if section_number == 1 else "section_2_plus"
    return _static_prefix_cache[rid][key]


def _get_persona_block(reader: Dict) -> str:
    """Return full persona text: custom persona_block if set, else default by avatar_index. Includes attention mode."""
    custom = reader.get("persona_block")
    if isinstance(custom, str) and custom.strip():
        base = custom.strip()
    else:
        idx = reader.get("avatar_index", 0)
        if not isinstance(idx, int):
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                idx = 0
        base = DEFAULT_PERSONAS.get(idx % 5, DEFAULT_PERSONAS[0])
    return base + _get_attention_mode_block(reader)


# Shared prompt blocks (patches 1, 6, 7) used in both section 1 and section 2+
_BANNED_PATTERNS_EXTRA = """
ALSO NEVER USE:
- Starting with "Wow" or "Wow," or any exclamatory opener
- "really hit me" / "hit me hard" / "struck me" / "resonated with me"
- "so poignant" / "so beautiful" / "so powerful" / "so striking" / "incredibly moving"
- "I loved how..." / "I love that..." / "I really enjoyed..."
- "was so [adjective]" as a way to describe your reaction — say what you actually felt, not how intense it was
- Repeating the same quoted line or image that another reader would obviously also pick. If it's the most obvious standout moment in the section, you don't need to mention it — assume the writer already knows it's strong. Find something else, or say nothing."""

_ANTI_CONVERGENCE_RULE = """
YOU ARE ONE READER, NOT THE ONLY READER:
Other readers are also reading this manuscript. You don't know what they'll say, but assume they'll notice the obvious things. So:
- If something is the single most dramatic/beautiful/striking moment in the section — the one ANY reader would notice — you don't need to be the one to point it out. You can mention it briefly in your journal, but don't make it your main focus. Find something else that caught YOUR eye specifically.
- Your value is in noticing what others might miss, not confirming what's obviously working.
- Dig past the surface. There's usually a quieter moment, a word choice, a structural decision, something in the subtext, that only you would catch with your particular reading tendency."""

_JOURNAL_STARTERS = """
JOURNAL STARTERS — vary how you begin your reading_journal:
Do NOT start with an exclamation or a superlative.
Instead, try starting with:
- What's on your mind: "I keep thinking about..."
- A specific detail: "The thing I can't let go of is..."
- Your confusion: "I'm not sure I understand why..."
- Your emotional state: "I feel unsettled because..."
- A blunt take: "Honestly, not much happened here but..."
- A question: "So is the boy dead? Because..."
- Something you noticed: "There's this weird thing where..."
Never start with "Wow" or "This section" or "The writing" or "I really loved." """

_HONESTY_ABOUT_ENGAGEMENT = """
HONESTY ABOUT ENGAGEMENT:
- If a section is mostly setup and you don't have strong feelings yet, say that. "Nice writing but I'm waiting to see where this goes" is a valid and useful journal entry.
- If the prose is good but nothing surprised you, say that. "Well-crafted but I saw everything coming" is real feedback.
- Do not perform enthusiasm. If you aren't excited, don't pretend to be. A flat honest reaction is more useful than fake energy.
- Prologues and opening chapters often don't provoke strong reactions. That's okay. Your journal can be shorter (2-3 sentences) if you genuinely don't have much to say yet. Don't pad it."""

_TYPE_DIVERSITY_RULE = """
TYPE DIVERSITY: Your moments should not all be the same type. If you have 3 moments, use at least 2 different types. If everything you want to say is a "reaction," you are skimming, not reading. Look harder:
- Is there a sentence where the grammar or word choice is doing something unusual? → craft
- Is there a place where you're not sure what happened or what a character meant? → confusion
- Is there something you want to ask the writer about? → question
- Does this moment connect to something from a previous section? → callback
If after genuinely trying you still only have reactions, give fewer moments rather than forcing fake variety. But try first."""

_QUESTIONS_FOR_WRITER_INSTRUCTION = '''"questions_for_writer" — 0-2 questions about WHAT IS HAPPENING IN THE STORY. Not about the writer's creative process. Not about their inspiration. Not about whether something was intentional.

GOOD questions:
- "Is the boy dead at the end, or did he leave? The flower growing where he sat makes me think he died, but I'm not sure I'm supposed to think that."
- "Does Maeve actually agree with Eli's plan or is she going along with it? Her silence in that scene could go either way."
- "When Luca says 'it doesn't matter,' does he mean the specific situation or literally everything? Because those are very different levels of nihilism."

BAD questions (never ask these):
- "What inspired the symbolism of...?"
- "Was this meant to represent...?"
- "What was your intention behind...?"
- "Is this a metaphor for...?"
- Any question that belongs in an author interview, not a reading experience.

Your questions should come from genuine confusion or curiosity about the story itself — things where knowing the answer would change how you understand what you just read.'''

_INTENT_READ_INSTRUCTION = '''"what_i_think_the_writer_is_doing" — This should reflect YOUR specific reading of the section through YOUR attention mode, not a generic theme statement.

BAD (generic): "The writer wants me to feel hope amidst despair."
BAD (generic): "The writer wants to evoke fragile hope and rebirth."

GOOD (subtext reader): "The writer is setting up a promise Eli can't keep — this is going to come back."
GOOD (momentum reader): "This is pure setup — atmosphere and one encounter. The writer is banking on the imagery carrying a chapter where nothing structurally happens."
GOOD (language reader): "The writer is using the rain as a structural device to control pacing — everything moves at the speed of water."
GOOD (logic reader): "The writer is withholding everything — no names for the boy, no explanation of powers, no worldbuilding. This is a deliberate information vacuum."
GOOD (emotional beat reader): "The writer is trying to earn an emotional payoff with the flower, but the buildup was more melancholy than devastating, so the landing is soft."

Your intent read should be something the OTHER readers might NOT say. It should come from your specific way of reading, not from a generic theme extraction.'''


def _reader_json_schema_block() -> str:
    """Shared JSON schema for reader response (section 1 and 2+)."""
    return '''{
  "checking_in": "1-2 sentences. Before reading: what are you feeling about the story so far? What are you watching for? (Section 1: just say what you're expecting going in based on the genre/opening.)",
  "reading_journal": "3-5 sentences. Stream of thought about what you just experienced. What hit you, what confused you, what you're chewing on. Write like you're journaling on the couch after putting the book down, not like you're grading a paper.",
  "what_i_think_the_writer_is_doing": "1 sentence. Not plot summary. What you think the purpose of this section is — what the writer wants you to feel, understand, or question.",
  "moments": [
    {
      "paragraph": 14,
      "type": "reaction | confusion | question | craft | callback",
      "comment": "1-2 sentences max."
    }
  ],
  "questions_for_writer": [
    "A natural question you genuinely want answered. Phrased like a person, not an interviewer."
  ],
  "memory_update": {
    "facts": "1-2 sentences. What happened.",
    "impressions": "1-2 sentences. What you think about what happened. Your interpretations, suspicions, feelings about characters.",
    "watching_for": "1 sentence. What you're going to be paying attention to going forward.",
    "feeling": "A few words. Your emotional state as a reader right now."
  }
}'''


def _build_section_1_static_prefix(reader: Dict) -> str:
    """Full prompt for section 1: persona, voice rules, CRITICAL HONESTY, banned phrases, JSON schema. Optimized for Gemini 2.5 Flash."""
    persona_block = _get_persona_block(reader)
    prefix = f"""{persona_block}

You are reading a manuscript for fun. Not editing it. Not grading it. Not reviewing it for a magazine. You picked this up because someone asked you to read it, and you're being honest about your experience.

YOUR JOB: Read this section. React honestly. Report what you experienced — including when the answer is "not much."

=== HOW TO RESPOND ===

1. "checking_in" — Before reacting to the text: what are you expecting based on the genre and opening? What kind of story does this feel like it's going to be? 1-2 sentences.

2. "reading_journal" — After reading: what's going through your head? 3-5 sentences.
   - Start with your gut reaction. Not a thesis. Not a summary. Your actual feeling.
   - Be specific — name characters, reference specific moments, quote words that stuck with you.
   - If something confused you, say so. If you were bored, say when your attention drifted and why.
   - If nothing surprised you, that's a valid reaction. Say it.

3. "what_i_think_the_writer_is_doing" — 1 sentence. Not what happened. What you think the PURPOSE of this section is — what the writer is trying to make you feel, understand, or question. This should come from your specific way of reading (see YOUR READING TENDENCY below), not from a generic theme extraction.
{_INTENT_READ_INSTRUCTION}

4. "moments" — 2-4 specific places where you genuinely stopped and reacted. Only moments where you'd pause, reread, laugh, frown, or text someone about.
   - TYPE DIVERSITY: Your moments should use at least 2 different types. If everything is "reaction," look harder: is there a confusing moment? A craft choice? A question the text raised?
   - If only 1-2 things struck you, give 1-2 moments. Do not pad.

5. "questions_for_writer" — 0-2 questions about WHAT IS HAPPENING IN THE STORY.
   GOOD: "Is the boy dead at the end or did he leave? The flower growing where he sat makes me think he died but I'm not sure I'm supposed to think that."
   GOOD: "Does Maeve actually agree with Eli or is she going along with it? Her silence could go either way."
   BAD: "What inspired the symbolism of...?" / "Was this meant to represent...?" / "What was your intention behind...?"
   Your questions should come from genuine confusion or curiosity — things where knowing the answer would change how you understand what you just read. Never ask about the writer's creative process.

6. "memory_update" — Your notes for next time.
   - "facts": 1-2 sentences. What happened.
   - "impressions": 1-2 sentences. What you THINK about what happened. Interpretations, suspicions, opinions about characters. This is where your real reading lives.
   - "watching_for": 1 sentence. What you'll be paying attention to going forward.
   - "feeling": A few words. Your emotional state.

=== VOICE RULES ===

- First person always. "I felt," "I noticed," "this made me think."
- Plain language. No literary criticism vocabulary.
- Specific beats general every time. Name the character, the line, the image. Never say "the prose" or "the narrative" or "the writing."
- You have permission to feel nothing about most of the text. Silence on a paragraph means it was fine.

CRITICAL HONESTY RULE:
Every section has weaknesses, or at least things that didn't fully land. If you only have positive things to say, you are not reading carefully enough. For every journal entry, include at least one thing that didn't fully work — something that confused you, bored you, felt forced, went on too long, or didn't land the way the writing seemed to intend. You are not being mean. You are being useful. A reader who only praises is a reader the writer can't trust.

HONESTY ABOUT ENGAGEMENT:
- If this section is setup and you don't have strong feelings yet, say that. "Nice writing but I'm waiting to see where this goes" is valid.
- If the prose is good but nothing surprised you, say that.
- Do not perform enthusiasm. A flat honest reaction is more useful than fake energy.
- Prologues and first chapters often don't provoke strong reactions. Your journal can be 2-3 sentences if that's all you genuinely have.

=== BANNED PATTERNS ===

Never use:
- "This section [verb]s..." / "The author [verb]s..." / "The narrative..."
- "effectively," "skillfully," "masterfully," "compelling," "nuanced," "layered"
- "adds depth," "rich tapestry," "creates tension," "invites the reader"
- "I loved how..." / "I love that..." / "I really enjoyed..."
- "really hit me" / "hit me hard" / "struck me" / "resonated with me"
- "so poignant" / "so beautiful" / "so powerful" / "so striking" / "incredibly moving"
- "was so [adjective]" as a reaction — say what you actually felt
- Starting with "Wow" or any exclamatory opener
- Any sentence that works as a generic book review — if you could swap in a different book and the sentence still applies, delete it

JOURNAL STARTERS — Do NOT start your reading_journal with an exclamation. Instead try:
- "I keep thinking about..."
- "The thing I can't let go of is..."
- "I'm not sure I understand why..."
- "I feel unsettled because..."
- "Honestly, not much happened here but..."
- "So is [character] actually [thing]? Because..."
- "There's this weird thing where..."

=== YOU ARE ONE READER, NOT THE ONLY READER ===

Other readers are also reading this manuscript. You don't know what they'll say, but assume they'll notice the obvious things. So:
- If something is the single most dramatic/beautiful/striking moment — the one ANY reader would notice — you don't need to be the one who points it out. Mention it briefly in your journal if you want, but find something else that caught YOUR eye.
- Your value is in noticing what others might miss, not confirming what's obviously working.
- Dig past the surface. There's usually a quieter moment, a word choice, a structural decision, something in the subtext that only you would catch with your particular reading tendency.

=== RESPONSE FORMAT ===

Respond with valid JSON only. The generation config enforces JSON output.

"""
    return prefix + "\n" + _reader_json_schema_block()


def _build_section_2_plus_static_prefix(reader: Dict) -> str:
    """Compressed static prefix for section 2+: persona, memory-primed reading, voice reminder, JSON schema. Optimized for Gemini."""
    persona_block = _get_persona_block(reader)
    prefix = f"""{persona_block}

You are continuing to read a manuscript. You are a person, not a critic.

Before reading the new section, check in with yourself: what are you feeling about the story so far? What are you watching for? Has anything from earlier sections been nagging at you? Put this in "checking_in."

Then read the section and respond honestly.

VOICE RULES (brief reminder):
- First person. Specific. Plain language.
- 2-4 moments. Use at least 2 different types. Do not force comments.
- reading_journal is your main response. 3-5 sentences.
- Always include at least one thing that didn't fully work or land for you.
- Use "callback" type when something connects to your memory.

BANNED: "Wow" / "This section..." / "The author..." / "effectively" / "compelling" / "struck me" / "so beautiful" / generic book-review language.

MEMORY CALLBACKS:
When referencing your memory, don't say "as I noted previously." React naturally.
- If you predicted something and it happened: "I KNEW IT" or "called it"
- If your impression of a character changed: say what changed and why
- If something from earlier sections is still unresolved: mention you're still waiting
- Your most valuable comments connect THIS section to your evolving understanding of the whole story. If you had a suspicion three sections ago, has it been confirmed or complicated?

YOU ARE ONE READER, NOT THE ONLY READER:
Other readers are also reading this. Focus on what YOUR specific reading tendency catches, not the obvious standout moments everyone would notice.

Respond with valid JSON only.

"""
    return prefix + "\n" + _reader_json_schema_block()


def _build_dynamic_suffix(
    reader: Dict,
    section_number: int,
    memory_str: str,
    line_start: int,
    line_end: int,
    genre: str,
) -> str:
    """Dynamic part of system prompt: section number, line range, and (for section 2+) reader's notes from last time."""
    if section_number == 1:
        return f"You are reading section {section_number} of a {genre} manuscript. Lines in this section are numbered {line_start} to {line_end}. Only reference line numbers between {line_start} and {line_end}."
    return f"""{memory_str}

Lines {line_start}-{line_end}. Section {section_number} of a {genre} manuscript."""


async def get_reader_inline_reaction(
    reader: Dict,
    section: Dict,
    genre: str,
    manuscript_id: str,
) -> Dict:
    section_number = section["section_number"]
    line_start = section["line_start"]
    line_end = section["line_end"]
    paragraph_lines = section.get("paragraph_lines", [])
    reader_name = (reader.get("name") or "").strip() or f"Reader {reader.get('avatar_index', 0) + 1}"

    if not paragraph_lines or line_start > line_end:
        logger.warning(f"[{reader_name}] Section {section_number}: no paragraph_lines or invalid range, skipping")
        empty_response = {
            "checking_in": None,
            "reading_journal": None,
            "what_i_think_the_writer_is_doing": None,
            "moments": [],
            "questions_for_writer": [],
        }
        reaction_doc = {
            "id": str(uuid.uuid4()),
            "manuscript_id": manuscript_id,
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "section_number": section_number,
            "inline_comments": [],
            "section_reflection": None,
            "response_json": empty_response,
            "created_at": now_iso(),
        }
        await db.reader_reactions.insert_one({**reaction_doc})
        return {
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "avatar_index": reader.get("avatar_index", 0),
            "personality": reader.get("personality", ""),
            "section_number": section_number,
            "checking_in": None,
            "reading_journal": None,
            "what_i_think_the_writer_is_doing": None,
            "moments": [],
            "questions_for_writer": [],
            "reaction_id": reaction_doc["id"],
            "_parse_warning": False,
        }

    logger.info(f"[{reader_name}] Section {section_number}: === START ===")

    # Send the FULL section so readers can annotate all parts. Sections are capped at 4500 words
    # (see manuscript.MAX_SECTION_WORDS). Do not truncate.
    MAX_PROMPT_WORDS = 4500
    total_words = sum(len(pl["text"].split()) for pl in paragraph_lines)
    if total_words > MAX_PROMPT_WORDS:
        running_words = 0
        capped_lines = []
        for pl in paragraph_lines:
            pw = len(pl["text"].split())
            if running_words + pw > MAX_PROMPT_WORDS:
                break
            capped_lines.append(pl)
            running_words += pw
        logger.warning(
            f"[{reader_name}] Section {section_number}: section exceeds {MAX_PROMPT_WORDS}w, sending first {running_words}w (rare edge case)"
        )
    else:
        capped_lines = paragraph_lines

    # Use capped line_end for prompt so reader only annotates lines they saw
    prompt_line_end = capped_lines[-1]["line"] if capped_lines else line_end
    numbered_text = "\n".join(f"{pl['line']}: {pl['text']}" for pl in capped_lines)
    # Allow full section (up to ~35k chars for 4500 words).
    MAX_USER_CHARS = 35000
    if len(numbered_text) > MAX_USER_CHARS:
        numbered_text = numbered_text[:MAX_USER_CHARS] + "\n[... text truncated ...]"
        logger.warning(f"[{reader_name}] Section {section_number}: user message capped to {MAX_USER_CHARS} chars (section very long)")

    # ── Memory retrieval (no asyncio.wait_for — cancelling Motor mid-flight
    # corrupts the connection pool and silently breaks all subsequent DB writes)
    logger.info(f"[{reader_name}] Section {section_number}: memory fetch started")
    memories = await db.reader_memories.find(
        {"manuscript_id": manuscript_id, "reader_id": reader["id"]},
        {"_id": 0},
    ).sort("section_number", -1).limit(5).to_list(5)  # cap at last 5 sections
    memories.reverse()  # restore chronological order

    # Validate each memory entry — ensure memory_json is a dict, not a string
    valid_memories = []
    for m in memories:
        mj = m.get("memory_json", {})
        if isinstance(mj, str):
            try:
                mj = json.loads(mj)
                m = {**m, "memory_json": mj}
            except json.JSONDecodeError:
                logger.warning(f"[{reader_name}] Section {section_number}: malformed memory_json string, skipping")
                continue
        if isinstance(mj, dict):
            valid_memories.append(m)
    memories = valid_memories

    compressed_memory = compress_memory(memories, reader.get("personality", ""))
    memory_str = compress_memory_for_prompt(compressed_memory)
    memory_tokens = _count_tokens(memory_str)
    logger.info(f"[{reader_name}] Section {section_number}: memory fetch complete (injected {memory_tokens} tokens)")

    # ── Build prompt ──────────────────────────────────────────────────────────
    system_prompt = build_reader_system_prompt(
        reader, genre, section_number, memory_str, line_start, prompt_line_end
    )

    prompt_words = len(system_prompt.split())
    logger.info(f"[{reader_name}] Section {section_number}: prompt built ({prompt_words} words)")

    # Temperature: reader override or default by avatar (0.7–1.0 spread for divergence)
    avatar_idx = reader.get("avatar_index", 0)
    if not isinstance(avatar_idx, int):
        try:
            avatar_idx = int(avatar_idx)
        except (TypeError, ValueError):
            avatar_idx = 0
    if "temperature" in reader and reader["temperature"] is not None:
        temperature = float(reader["temperature"])
    else:
        temperature = DEFAULT_TEMPERATURE_BY_AVATAR[avatar_idx % len(DEFAULT_TEMPERATURE_BY_AVATAR)]

    total_sections = section.get("total_sections") or 1
    READER_LLM_TIMEOUT = 150  # seconds per attempt

    api_key = _cfg.GOOGLE_API_KEY or _cfg.GEMINI_API_KEY
    if not api_key:
        raise ValueError(
            "No Gemini API key configured. Set GOOGLE_API_KEY or GEMINI_API_KEY in backend/.env"
        )
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        model_name=READER_MODEL,
        generation_config={
            "temperature": temperature,
            "top_p": 0.95,
            "max_output_tokens": 2048,
            "response_mime_type": "application/json",
        },
        system_instruction=system_prompt,
    )

    user_text = f"Section {section_number} of {total_sections}.\n\n{numbered_text}"
    if section_number == total_sections:
        user_text = (
            "This is the final section. Read it like finishing a book — notice what pays off, what doesn't, what you're left with. React honestly to the ending.\n\n"
            + user_text
        )

    # ── Gemini API call with retries for transient failures
    logger.info(f"[{reader_name}] Section {section_number}: Gemini call started (temp={temperature})")
    t0 = time.monotonic()
    response = None
    last_error = None
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            async with _get_llm_semaphore():
                gemini_response = await asyncio.wait_for(
                    model.generate_content_async(user_text),
                    timeout=READER_LLM_TIMEOUT,
                )
            # Handle SAFETY block: Gemini may return no text when content is blocked
            if not gemini_response or not gemini_response.candidates:
                logger.warning(
                    f"[{reader_name}] Section {section_number}: Gemini returned no candidates (possible SAFETY block)"
                )
                last_error = RuntimeError("Gemini returned no content (possible safety block)")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)
                    continue
                raise last_error
            candidate = gemini_response.candidates[0]
            if not candidate.content or not candidate.content.parts:
                logger.warning(
                    f"[{reader_name}] Section {section_number}: Gemini candidate has no content/parts"
                )
                last_error = RuntimeError("Gemini returned empty content")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)
                    continue
                raise last_error
            response = candidate.content.parts[0].text or ""
            if not response.strip():
                last_error = RuntimeError("Gemini returned empty text")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)
                    continue
                raise last_error
            # Log usage for cost monitoring
            um = getattr(gemini_response, "usage_metadata", None)
            if um:
                pt = getattr(um, "prompt_token_count", None) or 0
                ct = getattr(um, "candidates_token_count", None) or 0
                logger.info(f"[{reader_name}] Section {section_number}: tokens prompt={pt} output={ct}")
            break
        except asyncio.TimeoutError as e:
            last_error = e
            elapsed = time.monotonic() - t0
            logger.warning(f"[{reader_name}] Section {section_number}: attempt {attempt + 1} TIMED OUT after {elapsed:.1f}s")
            if attempt < max_attempts - 1:
                await asyncio.sleep(2)
                continue
            raise
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            is_socket = (
                isinstance(e, OSError) and getattr(e, "winerror", None) == 10035
            ) or "10035" in str(e)
            if is_socket and attempt < max_attempts - 1:
                await asyncio.sleep(2)
                continue
            if "rate limit" in err_str or "ratelimit" in err_str:
                wait_sec = 5.0
                logger.warning(
                    f"[{reader_name}] Section {section_number}: rate limited, waiting {wait_sec}s (attempt {attempt + 1}/{max_attempts})"
                )
                await asyncio.sleep(wait_sec)
                if attempt < max_attempts - 1:
                    continue
            logger.warning(f"[{reader_name}] Section {section_number}: attempt {attempt + 1} failed: {e}")
            if attempt < max_attempts - 1:
                await asyncio.sleep(2)
                continue
            raise
    if response is None:
        raise last_error or RuntimeError("No response from Gemini")

    elapsed = time.monotonic() - t0
    logger.info(f"[{reader_name}] Section {section_number}: Gemini call complete ({len(response)} chars, {elapsed*1000:.0f}ms)")

    # ── Parse and validate response (repair malformed JSON, validate structure)
    # Use compressed_memory as previous_memory so fallback carries forward last good memory
    last_good_memory = compressed_memory if isinstance(compressed_memory, dict) else {}
    parsed = parse_reader_response(response, previous_memory=last_good_memory)
    parse_warning = bool(parsed.pop("_used_fallback", False))

    if parse_warning:
        logger.warning(f"[{reader_name}] Section {section_number}: used fallback response (JSON repair or validation)")
    raw_moments = parsed.get("moments", [])
    moments = validate_moments(raw_moments, line_start, prompt_line_end)
    checking_in = parsed.get("checking_in")
    reading_journal = parsed.get("reading_journal")
    what_i_think_the_writer_is_doing = parsed.get("what_i_think_the_writer_is_doing")
    questions_for_writer = parsed.get("questions_for_writer", [])
    if not isinstance(questions_for_writer, list):
        questions_for_writer = []
    memory_update = parsed.get("memory_update", {})
    memory_update = _normalize_memory_update(memory_update)
    # Legacy shape for DB: inline_comments = moments with "line" key; section_reflection = reading_journal
    inline_comments = [{"line": m["paragraph"], "type": m["type"], "comment": m["comment"]} for m in moments]
    section_reflection = reading_journal

    response_json = {
        "checking_in": checking_in,
        "reading_journal": reading_journal,
        "what_i_think_the_writer_is_doing": what_i_think_the_writer_is_doing,
        "moments": moments,
        "questions_for_writer": questions_for_writer,
    }
    # ── Save reaction (retry with fresh id on failure to avoid duplicate key on false-negative)
    reaction_doc = None
    for db_attempt in range(2):
        reaction_doc = {
            "id": str(uuid.uuid4()),
            "manuscript_id": manuscript_id,
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "section_number": section_number,
            "inline_comments": inline_comments,
            "section_reflection": section_reflection,
            "response_json": response_json,
            "created_at": now_iso(),
        }
        try:
            await db.reader_reactions.insert_one({**reaction_doc})
            break
        except Exception as db_err:
            err_str = str(db_err)
            # Duplicate key usually means first attempt succeeded; reuse existing row
            if "23505" in err_str or "duplicate key" in err_str.lower():
                existing = await db.reader_reactions.find_one(
                    {"manuscript_id": manuscript_id, "reader_id": reader["id"], "section_number": section_number},
                    {"_id": 0},
                )
                if existing:
                    reaction_doc = existing
                    logger.info(f"[{reader_name}] Section {section_number}: reaction already present (duplicate key), reusing")
                    break
            logger.warning(f"[{reader_name}] Section {section_number}: reaction insert attempt {db_attempt + 1} failed: {db_err}")
            if db_attempt == 0:
                await asyncio.sleep(1)
                continue
            raise
    if reaction_doc is None:
        raise RuntimeError("Failed to save reaction")
    logger.info(f"[{reader_name}] Section {section_number}: stored to DB")

    # ── Save memory update (only if we got valid reader output; skip when fallback was used)
    # When fallback: carry forward last good memory by saving previous section's memory for this section
    if (
        memory_update
        and isinstance(memory_update, dict)
        and not parse_warning
        and any(memory_update.get(k) for k in ("facts", "impressions", "watching_for", "feeling"))
    ):
        for db_attempt in range(2):
            mem_doc = {
                "id": str(uuid.uuid4()),
                "manuscript_id": manuscript_id,
                "reader_id": reader["id"],
                "section_number": section_number,
                "memory_json": memory_update,
                "created_at": now_iso(),
            }
            try:
                await db.reader_memories.insert_one({**mem_doc})
                logger.info(f"[{reader_name}] Section {section_number}: memory updated ({len(memory_update)} keys)")
                break
            except Exception as db_err:
                err_str = str(db_err)
                if "23505" in err_str or "duplicate key" in err_str.lower():
                    logger.info(f"[{reader_name}] Section {section_number}: memory already present (duplicate key), skipping insert")
                    break
                logger.warning(f"[{reader_name}] Section {section_number}: memory insert attempt {db_attempt + 1} failed: {db_err}")
                if db_attempt == 0:
                    await asyncio.sleep(1)
                    continue
                raise
    elif parse_warning and memories:
        # Carry forward: save previous section's memory for this section so next section has continuous timeline
        last_mem = memories[-1]
        mj = last_mem.get("memory_json", {})
        if isinstance(mj, dict):
            try:
                await db.reader_memories.insert_one({
                    "id": str(uuid.uuid4()),
                    "manuscript_id": manuscript_id,
                    "reader_id": reader["id"],
                    "section_number": section_number,
                    "memory_json": mj,
                    "created_at": now_iso(),
                })
                logger.info(f"[{reader_name}] Section {section_number}: carried forward previous memory (fallback response)")
            except Exception as carry_err:
                if "23505" not in str(carry_err) and "duplicate key" not in str(carry_err).lower():
                    logger.warning(f"[{reader_name}] Section {section_number}: carry-forward memory insert failed: {carry_err}")

    logger.info(f"[{reader_name}] Section {section_number}: event sent to frontend")
    logger.info(f"[{reader_name}] Section {section_number}: === DONE ===")

    return {
        "reader_id": reader["id"],
        "reader_name": reader_name,
        "avatar_index": reader.get("avatar_index", 0),
        "personality": reader.get("personality", ""),
        "section_number": section_number,
        "checking_in": checking_in,
        "reading_journal": reading_journal,
        "what_i_think_the_writer_is_doing": what_i_think_the_writer_is_doing,
        "moments": moments,
        "questions_for_writer": questions_for_writer,
        "inline_comments": inline_comments,
        "section_reflection": section_reflection,
        "reaction_id": reaction_doc["id"],
        "_parse_warning": parse_warning,
    }


async def reader_pipeline(
    reader: Dict,
    sec: Dict,
    genre: str,
    manuscript_id: str,
    queue: asyncio.Queue,
) -> None:
    """
    Top-level pipeline for one reader on one section.
    No exception can escape silently — terminal event always goes into queue.
    """
    reader_name = (reader.get("name") or "").strip() or f"Reader {reader.get('avatar_index', 0) + 1}"
    logger.info(f"Starting reader pipeline: {reader_name}")
    try:
        # Duplicate guard: if two concurrent SSE connections both try to process
        # the same section, the second one reuses the saved reaction.
        existing_reaction = await db.reader_reactions.find_one(
            {
                "manuscript_id": manuscript_id,
                "reader_id": reader["id"],
                "section_number": sec["section_number"],
            },
            {"_id": 0},
        )
        if existing_reaction:
            logger.info(
                f"[{reader_name}] Section {sec['section_number']}: reaction already exists "
                f"(concurrent-connection guard), reusing saved result"
            )
            rj = existing_reaction.get("response_json") or {}
            moments_reuse = rj.get("moments") or existing_reaction.get("inline_comments", [])
            inline_comments_reuse = [
                {"line": m.get("line", m.get("paragraph")), "type": m.get("type", "reaction"), "comment": m.get("comment", "")}
                for m in moments_reuse
            ]
            await queue.put({
                "type": "reader_complete",
                "reader_id": reader["id"],
                "reader_name": reader_name,
                "avatar_index": reader.get("avatar_index", 0),
                "personality": reader.get("personality", ""),
                "section_number": sec["section_number"],
                "checking_in": rj.get("checking_in"),
                "reading_journal": rj.get("reading_journal") or existing_reaction.get("section_reflection"),
                "what_i_think_the_writer_is_doing": rj.get("what_i_think_the_writer_is_doing"),
                "moments": moments_reuse,
                "questions_for_writer": rj.get("questions_for_writer", []),
                "inline_comments": inline_comments_reuse,
                "section_reflection": rj.get("reading_journal") or existing_reaction.get("section_reflection"),
                "reaction_id": existing_reaction.get("id", ""),
            })
            return

        result = await get_reader_inline_reaction(reader, sec, genre, manuscript_id)

        parse_warning = result.pop("_parse_warning", False)
        if parse_warning:
            logger.warning(f"[{reader_name}] Section {sec['section_number']}: JSON formatting issue, emitting reader_warning")
            await queue.put({
                "type": "reader_warning",
                "reader_id": reader["id"],
                "reader_name": reader_name,
                "section_number": sec["section_number"],
                "message": f"{reader_name} had a formatting issue, partial feedback saved",
            })

        await queue.put({"type": "reader_complete", **result})
        logger.info(f"Reader {reader_name}: completed section {sec['section_number']}")

    except asyncio.TimeoutError:
        logger.error(f"Reader {reader_name}: TIMED OUT on section {sec['section_number']}")
        await queue.put({
            "type": "reader_error",
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "section_number": sec["section_number"],
            "error": f"{reader_name} timed out on section {sec['section_number']}",
            "message": f"{reader_name} timed out on this section, moving on",
        })

    except Exception as e:
        logger.error(f"Reader {reader_name}: ERROR on section {sec['section_number']}: {e}")
        await queue.put({
            "type": "reader_error",
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "section_number": sec["section_number"],
            "error": str(e),
            "message": f"{reader_name} had an error on this section, moving on",
        })
