"""Phase 3 deterministic workflow ledger and usage accounting."""
import hashlib
from typing import Any, Dict, Iterable, List, Optional

from config import db
from services.model_routing import route_for_reader
from utils import now_iso

TASK_STATES = {"pending", "running", "completed", "failed"}


def task_id(manuscript_id: str, reader_id: str, section_number: int) -> str:
    raw = f"{manuscript_id}:{reader_id}:{int(section_number)}".encode("utf-8")
    return "read-" + hashlib.sha256(raw).hexdigest()[:24]


def _reaction_pairs(reactions: Iterable[Dict]) -> set:
    return {
        (row.get("reader_id"), int(row.get("section_number") or 0))
        for row in reactions if row.get("reader_id") and row.get("section_number")
    }


async def ensure_task_ledger(manuscript: Dict, readers: List[Dict]) -> List[Dict]:
    """Create/reconcile one durable task per selected reader and section."""
    manuscript_id = manuscript["id"]
    sections = sorted(manuscript.get("sections") or [], key=lambda row: row.get("section_number") or 0)
    reactions = await db.reader_reactions.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(5000)
    completed_pairs = _reaction_pairs(reactions)
    existing = await db.workflow_tasks.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(5000)
    by_id = {row.get("id"): row for row in existing}

    for reader in readers:
        route = route_for_reader(reader)
        for section in sections:
            section_number = int(section.get("section_number") or 0)
            if not section_number:
                continue
            identifier = task_id(manuscript_id, reader["id"], section_number)
            completed = (reader["id"], section_number) in completed_pairs
            current = by_id.get(identifier)
            desired_state = "completed" if completed else (
                "pending" if not current or current.get("status") == "running" else current.get("status", "pending")
            )
            values = {
                "manuscript_id": manuscript_id,
                "reader_id": reader["id"],
                "reader_name": (reader.get("name") or "Reader").strip(),
                "section_number": section_number,
                "status": desired_state,
                "planned_provider": route.provider,
                "planned_model": route.model,
                "updated_at": now_iso(),
            }
            if current:
                await db.workflow_tasks.update_one({"id": identifier}, {"$set": values})
            else:
                row = {"id": identifier, **values, "attempts": 0, "last_error": None, "created_at": now_iso()}
                try:
                    await db.workflow_tasks.insert_one(row)
                except Exception as exc:
                    if "23505" not in str(exc) and "duplicate key" not in str(exc).lower():
                        raise

    selected_ids = {reader["id"] for reader in readers}
    rows = await db.workflow_tasks.find({"manuscript_id": manuscript_id}, {"_id": 0}).to_list(5000)
    return sorted(
        [row for row in rows if row.get("reader_id") in selected_ids],
        key=lambda row: (row.get("section_number") or 0, row.get("reader_name") or ""),
    )


async def update_task(
    manuscript_id: str,
    reader_id: str,
    section_number: int,
    status: str,
    *,
    error: Optional[str] = None,
    model: Optional[Dict] = None,
    increment_attempt: bool = False,
) -> None:
    if status not in TASK_STATES:
        raise ValueError(f"Invalid workflow task state: {status}")
    identifier = task_id(manuscript_id, reader_id, section_number)
    current = await db.workflow_tasks.find_one({"id": identifier}, {"_id": 0})
    values: Dict[str, Any] = {
        "status": status,
        "last_error": str(error or "")[:1000] or None,
        "updated_at": now_iso(),
    }
    if increment_attempt:
        values["attempts"] = int((current or {}).get("attempts") or 0) + 1
    if model:
        values["actual_provider"] = model.get("provider")
        values["actual_model"] = model.get("model")
    await db.workflow_tasks.update_one({"id": identifier}, {"$set": values})


def _usage_rows(reactions: List[Dict], report: Optional[Dict]) -> List[Dict]:
    rows = []
    seen = set()
    for reaction in reactions:
        key = (reaction.get("reader_id"), reaction.get("section_number"))
        if key in seen:
            continue
        seen.add(key)
        usage = (reaction.get("response_json") or {}).get("usage")
        if isinstance(usage, dict):
            rows.append(usage)
    report_json = (report or {}).get("report_json") or {}
    generation = report_json.get("_generation")
    if isinstance(generation, dict):
        usage = generation.get("usage") if isinstance(generation.get("usage"), dict) else generation
        rows.append({**usage, "role": usage.get("role", "editor")})
    copy_generation = (report_json.get("copy_edit_appendix") or {}).get("_generation")
    if isinstance(copy_generation, dict):
        usage = copy_generation.get("usage") if isinstance(copy_generation.get("usage"), dict) else copy_generation
        rows.append({**usage, "role": usage.get("role", "copyedit")})
    return rows


def summarize_usage(rows: List[Dict]) -> Dict:
    by_role: Dict[str, Dict] = {}
    unknown_cost = False
    for row in rows:
        role = str(row.get("role") or "unknown")
        bucket = by_role.setdefault(role, {"input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0, "calls": 0})
        bucket["calls"] += 1
        bucket["input_tokens"] += int(row.get("input_tokens") or 0)
        bucket["output_tokens"] += int(row.get("output_tokens") or 0)
        cost = row.get("estimated_cost_usd")
        if cost is None:
            unknown_cost = True
        else:
            bucket["estimated_cost_usd"] += float(cost)
    for bucket in by_role.values():
        bucket["estimated_cost_usd"] = round(bucket["estimated_cost_usd"], 6)
    return {
        "calls": sum(item["calls"] for item in by_role.values()),
        "input_tokens": sum(item["input_tokens"] for item in by_role.values()),
        "output_tokens": sum(item["output_tokens"] for item in by_role.values()),
        "estimated_cost_usd": round(sum(item["estimated_cost_usd"] for item in by_role.values()), 6),
        "has_unknown_cost": unknown_cost,
        "by_role": by_role,
    }


async def workflow_status(manuscript: Dict, readers: List[Dict]) -> Dict:
    tasks = await ensure_task_ledger(manuscript, readers)
    counts = {state: sum(1 for task in tasks if task.get("status") == state) for state in TASK_STATES}
    reactions = await db.reader_reactions.find({"manuscript_id": manuscript["id"]}, {"_id": 0}).to_list(5000)
    report = await db.editor_reports.find_one({"manuscript_id": manuscript["id"]}, {"_id": 0})
    return {
        "schema_version": 1,
        "manuscript_id": manuscript["id"],
        "total_tasks": len(tasks),
        "completed_tasks": counts["completed"],
        "pending_tasks": counts["pending"],
        "running_tasks": counts["running"],
        "failed_tasks": counts["failed"],
        "complete": bool(tasks) and counts["completed"] == len(tasks),
        "tasks": tasks,
        "usage": summarize_usage(_usage_rows(reactions, report)),
    }
