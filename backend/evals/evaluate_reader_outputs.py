"""Score saved reader-output JSON and create a human A/B review sheet.

Usage: python backend/evals/evaluate_reader_outputs.py results/*.json
Each result file should contain {case_id, variant, output, usage?}.
"""
import argparse
import json
import re
from pathlib import Path


GENERIC = re.compile(
    r"\b(the (writing|prose|narrative)|adds depth|creates tension|compelling|nuanced|"
    r"effectively|skillfully|i loved how|really hit me|consider tightening)\b",
    re.IGNORECASE,
)


def automated_metrics(record):
    output = record.get("output") or {}
    blob = json.dumps(output, ensure_ascii=False)
    moments = output.get("moments") if isinstance(output.get("moments"), list) else []
    grounded = sum(bool(m.get("paragraph_id") or m.get("paragraph")) for m in moments if isinstance(m, dict))
    return {
        "moment_count": len(moments),
        "grounded_moment_ratio": round(grounded / len(moments), 2) if moments else 1.0,
        "generic_phrase_hits": len(GENERIC.findall(blob)),
        "question_count": len(output.get("questions_for_writer") or []),
        "estimated_cost_usd": (record.get("usage") or {}).get("estimated_cost_usd"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--out", default="reader-eval-review.json")
    args = parser.parse_args()
    review = []
    for name in args.files:
        record = json.loads(Path(name).read_text(encoding="utf-8"))
        review.append({
            **record,
            "automated_metrics": automated_metrics(record),
            "human_scores_1_to_5": {
                "sounds_like_a_real_reader": None,
                "specific_to_the_text": None,
                "useful_without_workshop_performance": None,
                "memory_continuity": None,
                "personality_is_subtle": None,
                "does_not_invent_a_problem": None,
            },
            "human_notes": "",
        })
    Path(args.out).write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(review)} review records to {args.out}")


if __name__ == "__main__":
    main()
