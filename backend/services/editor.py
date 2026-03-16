import json
import re
import logging
from typing import Dict, List

from utils import make_chat, UserMessage
from config import db

logger = logging.getLogger(__name__)


def _reactions_to_editor_input(reactions: List[Dict]) -> str:
    """Build editor input from new reader schema: what_i_think_the_writer_is_doing, reading_journal, moments, questions_for_writer, memory impressions."""
    lines = []
    for r in reactions:
        sn = r.get("section_number", 0)
        reader_name = r.get("reader_name", "Reader")
        rj = r.get("response_json") or {}
        checking_in = rj.get("checking_in") or r.get("checking_in")
        reading_journal = rj.get("reading_journal") or r.get("section_reflection") or ""
        what_doing = rj.get("what_i_think_the_writer_is_doing") or r.get("what_i_think_the_writer_is_doing")
        moments = rj.get("moments") or r.get("inline_comments") or r.get("moments") or []
        questions = rj.get("questions_for_writer") or r.get("questions_for_writer") or []

        lines.append(f"\n[Section {sn}] {reader_name}:")
        if checking_in:
            lines.append(f"  Checking in: {checking_in}")
        if reading_journal:
            lines.append(f"  Reading journal: {reading_journal}")
        if what_doing:
            lines.append(f"  What they think the writer is doing: {what_doing}")
        for m in moments[:10]:
            mt = m.get("type", "reaction")
            mc = m.get("comment", "")
            if mc:
                lines.append(f"  [{mt}] {mc}")
        for q in questions:
            if q:
                lines.append(f"  Question for writer: {q}")
    return "\n".join(lines) if lines else "No reader feedback available."


async def generate_editor_report(manuscript: Dict, reactions: List[Dict]) -> Dict:
    """
    Build and call the editor LLM prompt using the new reader schema.
    Report focuses on: Did it land? Where did engagement drop? What do readers disagree about?
    Open questions. Strongest moments. No generic writing advice.
    """
    reactions_text = _reactions_to_editor_input(reactions)
    section_comment_counts: Dict[int, int] = {}
    for r in reactions:
        sn = r.get("section_number", 0)
        rj = r.get("response_json") or {}
        moments = rj.get("moments") or r.get("inline_comments") or []
        section_comment_counts[sn] = section_comment_counts.get(sn, 0) + len(moments)

    editor_system = f"""You are an editor synthesizing feedback from beta readers for a {manuscript.get('genre', 'fiction')} manuscript.
Your report must be grounded ONLY in what the readers actually experienced. No generic writing advice.

Read the reader feedback and produce a JSON report with this exact structure:

1. "did_it_land" — For each section (or overall), compare what readers said in "what they think the writer is doing". If readers agree, the intent is clear. If they diverge, list the different interpretations (one short paragraph per section or theme).

2. "engagement_drop" — Sections where reading_journal entries were short or moments were few = lower engagement. List section numbers and a one-line note per section where engagement seemed low.

3. "what_readers_disagree_about" — Genuine disagreements between readers about characters, intentions, or quality. Pull from reading_journal and impressions. Be specific; quote or paraphrase.

4. "open_questions" — Aggregate all "questions for writer" across readers and sections. Highlight questions that multiple readers asked independently. List each question once with a note if more than one reader asked it.

5. "strongest_moments" — Your curated selection of 5-8 strongest individual moments across all readers. These should be the moments with the most specificity and genuine reaction. Each entry: {{ "reader": "name", "section": N, "quote_or_summary": "..." }}.

Return ONLY valid JSON (no markdown fences). No "executive_summary", "recommendations", or generic advice. Only observations grounded in reader experience.

{{
  "did_it_land": "One or more paragraphs: where reader interpretations aligned vs. diverged.",
  "engagement_drop": [{{"section": 1, "note": "brief reason"}}],
  "what_readers_disagree_about": ["disagreement 1", "disagreement 2"],
  "open_questions": [{{"question": "...", "asked_by_multiple": true/false}}],
  "strongest_moments": [{{"reader": "name", "section": 1, "quote_or_summary": "..."}}]
}}"""

    chat = make_chat(editor_system).with_params(temperature=0.35, max_tokens=2000)
    response = await chat.send_message(UserMessage(
        text=f"Reader feedback:\n{reactions_text[:12000]}\n\nGenerate the editorial report."
    ))

    report_data: Dict = {}
    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        report_data = json.loads(clean)
    except Exception as e:
        logger.error(f"Failed to parse editor report: {e}")
        report_data = {
            "did_it_land": "The manuscript received reader feedback; synthesis could not be parsed.",
            "engagement_drop": [{"section": k, "note": ""} for k in sorted(section_comment_counts.keys())],
            "what_readers_disagree_about": [],
            "open_questions": [],
            "strongest_moments": [],
        }

    for key in ("did_it_land", "engagement_drop", "what_readers_disagree_about", "open_questions", "strongest_moments"):
        if key not in report_data:
            if key == "did_it_land":
                report_data[key] = ""
            elif key == "engagement_drop":
                report_data[key] = [{"section": k, "note": ""} for k in sorted(section_comment_counts.keys())]
            else:
                report_data[key] = [] if key != "did_it_land" else ""

    return report_data
