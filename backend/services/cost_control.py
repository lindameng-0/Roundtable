"""Per-manuscript AI budgets, reservations, and preflight estimates."""
from __future__ import annotations

import uuid
from typing import Dict, Iterable, Optional

import config as _cfg
from config import db
from services.model_routing import ModelRoute, route_for_reader, route_for_role, usage_record
from services.reader_memory import count_tokens


class CostLimitExceeded(RuntimeError):
    def __init__(self, details: Dict):
        self.details = details
        super().__init__(
            f"AI budget exceeded: ${float(details.get('requested_usd') or 0):.4f} requested, "
            f"${float(details.get('remaining_usd') or 0):.4f} remaining"
        )


def estimate_cost(route: ModelRoute, input_tokens: int, output_tokens: int) -> Optional[float]:
    return usage_record(route, "estimate", input_tokens, output_tokens).estimated_cost_usd


async def budget_status(manuscript: Dict) -> Dict:
    limit = float(manuscript.get("cost_limit_usd", _cfg.MAX_WORKFLOW_COST_USD) or 0)
    spent = float(manuscript.get("cost_spent_usd") or 0)
    reserved = float(manuscript.get("cost_reserved_usd") or 0)
    remaining = max(0.0, limit - spent - reserved) if limit > 0 else None
    return {
        "limit_usd": round(limit, 6),
        "spent_usd": round(spent, 6),
        "reserved_usd": round(reserved, 6),
        "remaining_usd": round(remaining, 6) if remaining is not None else None,
        "unlimited": limit <= 0,
    }


async def reserve(manuscript_id: str, role: str, operation_key: str, estimated_cost_usd: Optional[float]) -> Optional[str]:
    if estimated_cost_usd is None or estimated_cost_usd <= 0:
        return None
    reservation_id = str(uuid.uuid4())
    result = await db.reserve_cost(reservation_id, manuscript_id, role, operation_key, estimated_cost_usd)
    if not result.get("reserved"):
        remaining = max(0.0, float(result.get("limit_usd") or 0) - float(result.get("spent_usd") or 0) - float(result.get("reserved_usd") or 0))
        raise CostLimitExceeded({**result, "remaining_usd": remaining})
    return reservation_id


async def settle(reservation_id: Optional[str], actual_cost_usd: Optional[float]) -> None:
    if reservation_id:
        await db.settle_cost(reservation_id, float(actual_cost_usd or 0))


async def release(reservation_id: Optional[str]) -> None:
    if reservation_id:
        await db.release_cost(reservation_id)


def _bucket_add(buckets: Dict, role: str, route: ModelRoute, input_tokens: int, output_tokens: int, calls: int = 1) -> None:
    cost = estimate_cost(route, input_tokens, output_tokens)
    bucket = buckets.setdefault(role, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0, "models": set()})
    bucket["calls"] += calls
    bucket["input_tokens"] += input_tokens
    bucket["output_tokens"] += output_tokens
    bucket["models"].add(route.key)
    if cost is not None:
        bucket["estimated_cost_usd"] += cost
    else:
        bucket["has_unknown_pricing"] = True


async def preflight_estimate(manuscript: Dict, readers: Iterable[Dict], operation: str = "remaining") -> Dict:
    readers = list(readers)
    sections = manuscript.get("sections") or []
    manuscript_id = manuscript["id"]
    reactions = await db.reader_reactions.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(10000)
    completed = {(row.get("reader_id"), int(row.get("section_number") or 0)) for row in reactions}
    buckets: Dict = {}

    if operation in {"remaining", "readers"}:
        for reader in readers:
            route = route_for_reader(reader)
            for section in sections:
                section_number = int(section.get("section_number") or 0)
                if (reader.get("id"), section_number) in completed:
                    continue
                section_text = "\n".join(str(p.get("text") or "") for p in section.get("paragraph_lines") or [])
                # Prompt, reader state, and question-ledger overhead grows as the book progresses.
                input_tokens = count_tokens(section_text) + 1400
                _bucket_add(buckets, "reader", route, input_tokens, 1700)

    if operation in {"remaining", "editor", "editor_regeneration"}:
        chars = len(manuscript.get("raw_text") or "")
        if chars > _cfg.EDITOR_DIRECT_MAX_CHARS:
            chunk_count = min(_cfg.EDITOR_MAX_CHUNKS, max(1, (chars + _cfg.EDITOR_CHUNK_MAX_CHARS - 1) // _cfg.EDITOR_CHUNK_MAX_CHARS))
            map_route = route_for_role("editor_map")
            for _ in range(chunk_count):
                _bucket_add(buckets, "editor_map", map_route, count_tokens((manuscript.get("raw_text") or "")[:_cfg.EDITOR_CHUNK_MAX_CHARS]) + 500, 2200)
            final_input = min(90000, chunk_count * 2600 + len(reactions) * 500)
        else:
            final_input = count_tokens(manuscript.get("raw_text") or "") + len(reactions) * 500 + 1500
        _bucket_add(buckets, "editor", route_for_role("editor"), final_input, 6000)

    if operation == "copyedit":
        _bucket_add(buckets, "copyedit", route_for_role("copyedit"), count_tokens((manuscript.get("raw_text") or "")[:160000]) + 500, 3000)

    serializable = {}
    for role, bucket in buckets.items():
        serializable[role] = {**bucket, "models": sorted(bucket["models"]), "estimated_cost_usd": round(bucket["estimated_cost_usd"], 6)}
    expected = round(sum(row["estimated_cost_usd"] for row in serializable.values()), 6)
    budget = await budget_status(manuscript)
    remaining = budget["remaining_usd"]
    unknown_pricing = any(row.get("has_unknown_pricing") for row in serializable.values())
    return {
        "operation": operation,
        "estimated_cost_usd": expected,
        "by_role": serializable,
        "budget": budget,
        "can_start": not unknown_pricing and (remaining is None or expected <= remaining),
        "has_unknown_pricing": unknown_pricing,
        "note": "Estimates use configured model prices and expected output lengths; provider billing may vary.",
    }
