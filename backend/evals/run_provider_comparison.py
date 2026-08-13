"""Run Reader V2 evaluation cases against one or more provider:model routes."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.llm_gateway import structured_completion
from services.model_routing import parse_route
from services.reader_contract import validate_reader_output
from services.reader_prompts_v2 import build_reader_v2_prompts


async def run_case(case, route, output_dir):
    paragraphs = [
        {"line": index, "paragraph_id": f"p-{index:06d}", "text": text}
        for index, text in enumerate(case["text"], 1)
    ]
    reader = {
        "id": "eval-reader",
        "name": "Alex",
        "avatar_index": 0,
        "reading_habits": "Reads several novels a month and responds candidly.",
    }
    system, user = build_reader_v2_prompts(
        reader, case.get("genre", "fiction"), 2 if case.get("prior_state") else 1, 2,
        paragraphs, case.get("prior_state") or {},
    )
    result = await structured_completion(
        route=route, role="reader", system_prompt=system, user_prompt=user, max_tokens=2200
    )
    output, warnings = validate_reader_output(result.data, paragraphs)
    record = {
        "case_id": case["id"],
        "purpose": case["purpose"],
        "variant": f"v2-{route.key}",
        "output": output,
        "warnings": warnings,
        "usage": result.usage.to_dict(),
    }
    path = output_dir / f"{case['id']}--{route.provider}--{route.model}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{case['id']}: {route.key} (${result.usage.estimated_cost_usd or 0:.6f})")


async def main_async(args):
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    selected = set(args.case) if args.case else None
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    for route_text in args.route:
        route = parse_route(route_text)
        for case in cases:
            if selected and case["id"] not in selected:
                continue
            await run_case(case, route, output_dir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", action="append", required=True, help="provider:model; repeat to compare")
    parser.add_argument("--case", action="append", help="case id; omit for all eight")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("reader_cases.json")))
    parser.add_argument("--out", default=str(Path(__file__).with_name("results")))
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
