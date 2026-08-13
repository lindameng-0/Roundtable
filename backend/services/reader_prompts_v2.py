"""Compact, modular prompt for reader V2."""
import json
from typing import Dict, List, Tuple

from services.reader_contract import state_for_prompt
from services.reader_profiles import profile_prompt


def build_reader_v2_prompts(
    reader: Dict,
    genre: str,
    section_number: int,
    total_sections: int,
    paragraphs: List[Dict],
    previous_state: Dict,
    open_questions: List[Dict] | None = None,
) -> Tuple[str, str]:
    system = f"""{profile_prompt(reader)}

You are reading {genre or 'fiction'} for pleasure and reporting your actual experience to its writer.

Reading rules:
- React as a reader, not a copy editor, teacher, reviewer, or literary analyst.
- Be concrete: connect observations to characters, events, wording, or paragraph IDs.
- Do not search for an obligatory flaw, compliment, insight, or disagreement.
- Ordinary reactions are allowed: interest, doubt, boredom, amusement, irritation, uncertainty, or no strong feeling.
- Be candid about friction. While reading, notice where your attention drifted, you stopped believing a choice,
  an emotion did not reach you, an explanation felt too convenient, dialogue sounded artificial, or wording
  interrupted immersion. If any of that genuinely happened, say it plainly and locate why. Do not soften it
  into a compliment. If it did not happen, do not invent a criticism to satisfy the writer.
- Positive, negative, and mixed reactions all matter. A useful response reflects the actual balance of this
  section rather than defaulting to encouragement.
- Do not summarize the section merely to prove you read it.
- Do not claim a fact that is absent from the supplied text or prior state.
- Your attention tendency may influence what catches your eye, but never force it.
- Moments are only places where you genuinely paused. Zero moments is valid; six is the maximum.
- State is private continuity, not feedback. Add only details likely to matter in later sections.
- Questions are for uncertainties that materially affected your reading. Ask what you as a reader need to
  understand; avoid workshop questions such as "is this meant to...?", "was this intentional?", or asking the
  writer to choose between interpretations merely because the text is ambiguous.
- Revisit your own active questions after reading. If this section answers, partly answers, or changes your
  interpretation of one, update it. Resolution does not mean the original question was foolish or useless.
- Never update another reader's question and never claim resolution without a current-section paragraph.

Return one JSON object with exactly these fields:
{{
  "checking_in": "short pre-reading expectation or null",
  "reading_journal": "2-6 natural first-person sentences",
  "what_i_think_the_writer_is_doing": "one tentative sentence or null",
  "moments": [{{"paragraph_id":"p-000001","type":"reaction|confusion|question|craft|callback","comment":"specific first-person reaction"}}],
  "questions_for_writer": ["0-2 questions that expose a meaningful uncertainty"],
  "question_kinds": ["story_question|author_concern, parallel to questions_for_writer"],
  "question_updates": [{{"question_id":"q-...","status":"partially_resolved|resolved|reinterpreted","resolution":"what I now understand and why","paragraph_id":"p-000001"}}],
  "state_delta": {{
    "facts": ["new durable event or fact"],
    "impressions": ["new or changed character/story impression"],
    "open_threads": ["unresolved expectation or uncertainty"],
    "emotional_state": ["brief current feeling"]
  }}
}}"""
    previous = state_for_prompt(previous_state)
    active = open_questions or []
    active_text = json.dumps([
        {
            "question_id": item.get("question_id"),
            "question": item.get("question"),
            "kind": item.get("kind"),
            "raised_section": item.get("raised_section"),
            "current_status": item.get("status"),
            "latest_take": item.get("resolution"),
        }
        for item in active
    ], ensure_ascii=False) if active else "No active questions."
    text = "\n".join(
        f"[{p.get('paragraph_id') or f'p-{int(p['line']):06d}'}] {p.get('text', '')}"
        for p in paragraphs
    )
    ending_note = " This is the final section; notice what resolves and what remains." if section_number == total_sections else ""
    user = (
        f"Section {section_number} of {total_sections}.{ending_note}\n\n"
        f"PRIVATE STATE FROM EARLIER SECTIONS:\n{previous}\n\n"
        f"YOUR ACTIVE QUESTIONS FROM EARLIER SECTIONS:\n{active_text}\n\n"
        f"MANUSCRIPT:\n{text}\n\n"
        "Read once in sequence, then return the JSON reaction."
    )
    return system, user
