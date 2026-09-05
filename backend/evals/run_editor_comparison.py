"""Generate comparable Editor V3 reports for curated literary edge cases."""
import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.editor import _editor_system_prompt, _ground_report_evidence, _normalize_editor_report, validate_editor_report
from services.editor_evidence import aggregate_editor_evidence, evidence_json, manuscript_for_editor
from services.llm_gateway import structured_completion
from services.model_routing import parse_route


def materialize(case):
    line = 1
    sections = []
    for section_number, paragraphs in enumerate(case["sections"], 1):
        rows = []
        for text in paragraphs:
            rows.append({"line": line, "paragraph_id": f"p-{line:06d}", "text": text})
            line += 1
        sections.append({"section_number": section_number, "title": f"Section {section_number}", "paragraph_lines": rows})
    reactions = []
    for index, item in enumerate(case["reactions"]):
        section = item["section"]
        pid = sections[section - 1]["paragraph_lines"][-1]["paragraph_id"]
        reactions.append({
            "id": str(uuid.uuid4()), "reader_id": f"reader-{index + 1}", "reader_name": item["reader"],
            "section_number": section, "created_at": "2026-01-01T00:00:00+00:00",
            "response_json": {"reading_journal": item["journal"], "moments": [{"paragraph_id": pid, "type": item["type"], "comment": item["moment"]}], "questions_for_writer": []},
        })
    return {"id": case["id"], "genre": case["genre"], "sections": sections}, reactions


async def run_case(case, route, output_dir):
    manuscript, reactions = materialize(case)
    aggregate = aggregate_editor_evidence(reactions)
    manuscript_text, _ = manuscript_for_editor(manuscript)
    evidence_text, _ = evidence_json(aggregate)
    completion = await structured_completion(
        route=route, role="editor", system_prompt=_editor_system_prompt(case["genre"]),
        user_prompt="MANUSCRIPT:\n" + manuscript_text + "\n\nREADER EVIDENCE:\n" + evidence_text + "\n\nGenerate the complete Editor V3 report.",
        temperature=0.2, max_tokens=10000,
    )
    report = _normalize_editor_report(completion.data, list(range(1, len(case["sections"]) + 1)))
    _ground_report_evidence(report, manuscript, aggregate)
    record = {"case_id": case["id"], "purpose": case["purpose"], "expectations": case["expectations"], "variant": route.key, "report": report, "validation_errors": validate_editor_report(report), "usage": completion.usage.to_dict()}
    path = output_dir / f"{case['id']}--{route.provider}--{route.model}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{case['id']}: {route.key} (${completion.usage.estimated_cost_usd or 0:.6f})")


async def main_async(args):
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    selected = set(args.case or [])
    output_dir = Path(args.out); output_dir.mkdir(parents=True, exist_ok=True)
    for route_text in args.route:
        for case in cases:
            if not selected or case["id"] in selected:
                await run_case(case, parse_route(route_text), output_dir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", action="append", required=True)
    parser.add_argument("--case", action="append")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("editor_cases.json")))
    parser.add_argument("--out", default=str(Path(__file__).with_name("editor_results")))
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__": main()
