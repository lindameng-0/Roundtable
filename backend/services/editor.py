import json
import re
import uuid
import logging
from typing import Dict, List

from utils import make_chat, now_iso, UserMessage
from config import db

logger = logging.getLogger(__name__)


async def generate_editor_report(manuscript: Dict, reactions: List[Dict]) -> Dict:
    """
    Build and call the editor LLM prompt, returning parsed report_json.
    Also handles fallback if the LLM response cannot be parsed.
    """
    section_comment_counts: Dict[int, int] = {}
    reactions_text = ""

    for r in reactions:
        sn = r.get("section_number", 0)
        reader_name = r.get("reader_name", "Reader")
        comments = r.get("inline_comments", [])
        reflection = r.get("section_reflection", "")
        section_comment_counts[sn] = section_comment_counts.get(sn, 0) + len(comments)

        if comments or reflection:
            reactions_text += f"\n[Section {sn}] {reader_name}:\n"
            for c in comments[:8]:
                reactions_text += f"  [{c.get('type', 'reaction')}] {c.get('comment', '')}\n"
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

    report_data: Dict = {}
    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        report_data = json.loads(clean)
    except Exception as e:
        logger.error(f"Failed to parse editor report: {e}")
        report_data = {
            "executive_summary": [
                "The manuscript received reactions from the panel.",
                "Further development is recommended.",
            ],
            "consensus_findings": [],
            "character_impressions": [],
            "prediction_accuracy": [],
            "engagement_by_section": [
                {"section": k, "engagement_score": min(100, v * 8), "note": ""}
                for k, v in sorted(section_comment_counts.items())
            ],
            "recommendations": [
                {"priority": "medium", "title": "Continue revision", "detail": "Address reader concerns and iterate."}
            ],
        }

    if not report_data.get("engagement_by_section"):
        report_data["engagement_by_section"] = [
            {"section": k, "engagement_score": min(100, v * 8), "note": ""}
            for k, v in sorted(section_comment_counts.items())
        ]

    return report_data
