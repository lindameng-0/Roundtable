"""Create a provider-blind Editor V3 review sheet with automated checks."""
import argparse
import hashlib
import json
import re
from pathlib import Path

GENERIC = re.compile(r"\b(compelling|adds depth|consider tightening|show,? don't tell|well[- ]developed|engaging narrative)\b", re.I)


def metrics(record):
    report = record.get("report") or {}; expectations = record.get("expectations") or {}
    blob = json.dumps(report, ensure_ascii=False).lower()
    classes = {item.get("classification") for item in report.get("story_integrity") or []}
    refs = [ref for group in (report.get("reader_response") or {}).values() for item in (group or []) for ref in item.get("evidence") or []]
    required_classes = set(expectations.get("required_integrity_classes") or [])
    forbidden_classes = set(expectations.get("forbidden_integrity_classes") or [])
    return {
        "structurally_complete": not record.get("validation_errors"),
        "grounded_reference_count": len(refs),
        "generic_phrase_hits": len(GENERIC.findall(blob)),
        "required_topic_hits": {topic: topic.lower() in blob for topic in expectations.get("required_topics") or []},
        "required_integrity_class_hit": not required_classes or bool(classes & required_classes),
        "forbidden_integrity_class_avoided": not bool(classes & forbidden_classes),
        "disagreement_present": bool((report.get("reader_response") or {}).get("meaningful_disagreements")),
        "estimated_cost_usd": (record.get("usage") or {}).get("estimated_cost_usd"),
    }


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("files", nargs="+"); parser.add_argument("--out", default="editor-eval-review.json"); parser.add_argument("--key-out", default="editor-eval-key.json")
    args = parser.parse_args(); review = []; key = {}
    for name in args.files:
        record = json.loads(Path(name).read_text(encoding="utf-8"))
        blind_id = hashlib.sha256(record["variant"].encode()).hexdigest()[:8]
        key[blind_id] = record["variant"]
        review.append({"case_id": record["case_id"], "purpose": record["purpose"], "blind_variant": blind_id, "report": record["report"], "automated_metrics": metrics(record), "human_scores_1_to_5": {"accurate_story_understanding":None,"distinguishes_fact_from_reader_taste":None,"specific_and_evidence_grounded":None,"prioritizes_high_leverage_revisions":None,"balanced_without_empty_praise":None,"useful_to_the_writer":None}, "human_notes":""})
    review.sort(key=lambda row: (row["case_id"], row["blind_variant"]))
    Path(args.out).write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.key_out).write_text(json.dumps(key, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(review)} blinded records to {args.out}; key to {args.key_out}")


if __name__ == "__main__": main()
