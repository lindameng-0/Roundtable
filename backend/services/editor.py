import json
import re
import logging
from typing import Dict, List, Any

import google.generativeai as genai
import config as _cfg

logger = logging.getLogger(__name__)

EDITOR_MODEL = "gemini-2.5-pro"
EDITOR_TEMPERATURE = 0.3
# Cap total editor input to stay within context; Editor needs to see all sections but not unbounded
MAX_EDITOR_INPUT_CHARS = 120000


def _reactions_to_editor_input(reactions: List[Dict]) -> str:
    """
    Build editor input: ALL reader responses per section as full JSON.
    Structure: Section 1:\\n  ReaderName: {json}\\n  ...\\nSection 2:\\n  ...
    """
    by_section: Dict[int, List[Dict]] = {}
    for r in reactions:
        sn = r.get("section_number", 0)
        if sn not in by_section:
            by_section[sn] = []
        by_section[sn].append(r)

    lines = []
    for sn in sorted(by_section.keys()):
        lines.append(f"Section {sn}:")
        for r in by_section[sn]:
            reader_name = r.get("reader_name", "Reader")
            # Full reader response: response_json preferred, else build from legacy fields
            rj = r.get("response_json") or {}
            if not rj:
                rj = {
                    "checking_in": r.get("checking_in"),
                    "reading_journal": r.get("reading_journal") or r.get("section_reflection"),
                    "what_i_think_the_writer_is_doing": r.get("what_i_think_the_writer_is_doing"),
                    "moments": r.get("moments") or r.get("inline_comments") or [],
                    "questions_for_writer": r.get("questions_for_writer") or [],
                }
            try:
                blob = json.dumps(rj, ensure_ascii=False)
            except (TypeError, ValueError):
                blob = "{}"
            lines.append(f"  {reader_name}: {blob}")
        lines.append("")

    out = "\n".join(lines).strip()
    if len(out) > MAX_EDITOR_INPUT_CHARS:
        out = out[:MAX_EDITOR_INPUT_CHARS] + "\n[... input truncated ...]"
        logger.warning(f"Editor input truncated to {MAX_EDITOR_INPUT_CHARS} chars")
    return out or "No reader feedback available."


def _editor_system_prompt(genre: str) -> str:
    return f"""You are a professional editor synthesizing feedback from multiple independent beta readers. You did not read the manuscript yourself. Your job is to find patterns, disagreements, and insights across the readers' responses.

RULES:
- Never invent observations the readers didn't make. Only synthesize what's in their data.
- Surface disagreements — they're the most valuable part. When readers see the same scene differently, that reveals ambiguity the writer needs to know about.
- For "did_it_land": compare each reader's "what_i_think_the_writer_is_doing" per section. If they agree, the intent is clear. If they diverge, flag it.
- For "character_perception_map": pull from reader impressions across ALL sections, not just the section where the character appeared most.
- For "engagement_map": use journal length and moment count as engagement proxies. Short journals + few moments = cold spot.
- For "unresolved_questions": track which questions_for_writer were never answered by a callback in later sections.
- For "prediction_tracker": use readers' "watching_for" and "impressions" fields across sections.
- For "moments_of_consensus": find paragraphs/scenes where ALL readers independently reacted.
- For "heart_of_story": synthesize each reader's intent reads across the whole manuscript into their overall thematic read.
- For "strongest_moments": curate 8-10 moments that are most specific and most strongly felt. Not "best" — strongest.

Do NOT produce generic writing advice. No "consider tightening the pacing." Only observations grounded in what readers actually experienced.

Respond with valid JSON only. No markdown fences. Use this exact structure:

{
  "story_overview": { "genre": "...", "tone": "...", "premise": "1-2 sentences" },
  "did_it_land": [
    { "section": 1, "reader_intents": { "ReaderName": "..." }, "alignment": "aligned | divergent | mixed", "summary": "1-2 sentences" }
  ],
  "character_perception_map": [
    { "character": "Name", "reader_impressions": { "ReaderName": "1 sentence" }, "consensus_or_split": "1 sentence" }
  ],
  "engagement_map": [
    { "section": 1, "engagement_level": "high | medium | low", "notes": "1 sentence" }
  ],
  "disagreements": [
    { "topic": "...", "positions": { "reader_name": "their take" }, "significance": "1 sentence" }
  ],
  "unresolved_questions": [
    { "question": "...", "asked_by": ["names"], "section_first_asked": 1, "resolved": false }
  ],
  "prediction_tracker": [
    { "reader": "Name", "prediction": "...", "section_predicted": 1, "outcome": "confirmed | denied | still open", "section_resolved": 2 }
  ],
  "strongest_moments": [
    { "reader": "Name", "section": 1, "paragraph": 12, "comment": "...", "why_selected": "1 sentence" }
  ],
  "heart_of_story": { "reader_themes": { "ReaderName": "1 sentence" }, "synthesis": "2-3 sentences" },
  "moments_of_consensus": [
    { "section": 1, "paragraph": 14, "what_happened": "1 sentence", "who_reacted": ["all readers"], "significance": "1 sentence" }
  ]
}"""


def _default_editor_report(section_numbers: List[int]) -> Dict[str, Any]:
    """Default 10-section report when parsing fails or fields are missing."""
    return {
        "story_overview": {"genre": "", "tone": "", "premise": ""},
        "did_it_land": [{"section": s, "reader_intents": {}, "alignment": "mixed", "summary": ""} for s in section_numbers],
        "character_perception_map": [],
        "engagement_map": [{"section": s, "engagement_level": "medium", "notes": ""} for s in section_numbers],
        "disagreements": [],
        "unresolved_questions": [],
        "prediction_tracker": [],
        "strongest_moments": [],
        "heart_of_story": {"reader_themes": {}, "synthesis": ""},
        "moments_of_consensus": [],
    }


def _normalize_editor_report(parsed: Dict, section_numbers: List[int]) -> Dict[str, Any]:
    """Ensure all 10 sections exist with correct shape."""
    default = _default_editor_report(section_numbers)
    out = {}
    for key in default:
        val = parsed.get(key)
        if val is None:
            out[key] = default[key]
        elif key == "story_overview" and isinstance(val, dict):
            out[key] = {
                "genre": val.get("genre", ""),
                "tone": val.get("tone", ""),
                "premise": val.get("premise", ""),
            }
        elif key == "did_it_land" and isinstance(val, list):
            out[key] = val
        elif key == "character_perception_map" and isinstance(val, list):
            out[key] = val
        elif key == "engagement_map" and isinstance(val, list):
            out[key] = val
        elif key == "disagreements" and isinstance(val, list):
            out[key] = val
        elif key == "unresolved_questions" and isinstance(val, list):
            out[key] = val
        elif key == "prediction_tracker" and isinstance(val, list):
            out[key] = val
        elif key == "strongest_moments" and isinstance(val, list):
            out[key] = val
        elif key == "heart_of_story" and isinstance(val, dict):
            out[key] = {
                "reader_themes": val.get("reader_themes") if isinstance(val.get("reader_themes"), dict) else {},
                "synthesis": val.get("synthesis", ""),
            }
        elif key == "moments_of_consensus" and isinstance(val, list):
            out[key] = val
        else:
            out[key] = default[key]
    return out


async def generate_editor_report(manuscript: Dict, reactions: List[Dict]) -> Dict:
    """
    Build and call the Editor (Gemini 2.5 Pro) with ALL reader data across ALL sections.
    Returns the 10-section report: story_overview, did_it_land, character_perception_map,
    engagement_map, disagreements, unresolved_questions, prediction_tracker,
    strongest_moments, heart_of_story, moments_of_consensus.
    """
    reactions_text = _reactions_to_editor_input(reactions)
    section_numbers = sorted(set(r.get("section_number", 0) for r in reactions if r.get("section_number")))

    api_key = _cfg.GOOGLE_API_KEY or _cfg.GEMINI_API_KEY
    if not api_key:
        logger.error("No Gemini API key configured for Editor")
        return _normalize_editor_report({}, section_numbers)

    genai.configure(api_key=api_key)
    genre = manuscript.get("genre", "fiction")
    model = genai.GenerativeModel(
        model_name=EDITOR_MODEL,
        generation_config={
            "temperature": EDITOR_TEMPERATURE,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        },
        system_instruction=_editor_system_prompt(genre),
    )

    user_message = f"Reader feedback (each section lists readers with their full response JSON):\n\n{reactions_text}\n\nGenerate the editorial report as JSON."

    report_data: Dict = {}
    try:
        response = await model.generate_content_async(user_message)
        if not response or not response.candidates:
            logger.warning("Editor: Gemini returned no candidates")
            return _normalize_editor_report({}, section_numbers)
        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            logger.warning("Editor: Gemini candidate has no content")
            return _normalize_editor_report({}, section_numbers)
        raw = candidate.content.parts[0].text or ""
        if not raw.strip():
            return _normalize_editor_report({}, section_numbers)

        clean = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
        clean = re.sub(r"\n?```\s*$", "", clean.strip())
        report_data = json.loads(clean)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse editor report JSON: {e}")
        report_data = {}
    except Exception as e:
        logger.exception("Editor Gemini call failed: %s", e)
        return _normalize_editor_report({}, section_numbers)

    return _normalize_editor_report(report_data, section_numbers)
