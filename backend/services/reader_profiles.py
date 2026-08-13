"""Restrained reader tendencies: attention biases, not theatrical characters."""
from typing import Dict


ATTENTION_PROFILES = {
    "subtext": "You often notice gaps between what characters say and do.",
    "momentum": "You often notice when your attention accelerates, settles, or drifts.",
    "language": "You often notice sentence rhythm, images, and wording that changes immersion.",
    "emotion": "You often notice whether emotional turns feel earned in the moment.",
    "continuity": "You often track what was established earlier and whether new information fits.",
}
DEFAULT_PROFILE_BY_AVATAR = ["subtext", "momentum", "language", "emotion", "continuity"]


def behavioral_profile(reader: Dict) -> Dict[str, str]:
    try:
        index = int(reader.get("avatar_index", 0))
    except (TypeError, ValueError):
        index = 0
    key = str(reader.get("attention_mode") or DEFAULT_PROFILE_BY_AVATAR[index % 5]).lower()
    if key not in ATTENTION_PROFILES:
        key = DEFAULT_PROFILE_BY_AVATAR[index % 5]
    return {
        "name": (reader.get("name") or "Reader").strip(),
        "attention": key,
        "attention_instruction": ATTENTION_PROFILES[key],
        "reading_context": str(reader.get("reading_habits") or "Reads fiction for pleasure.")[:240],
    }


def profile_prompt(reader: Dict) -> str:
    profile = behavioral_profile(reader)
    return (
        f"You are {profile['name']}, an ordinary beta reader. {profile['reading_context']} "
        f"{profile['attention_instruction']} This is a mild attention bias, not a duty: it should affect "
        "what you notice, never force an opinion, complaint, gimmick, or disagreement."
    )
