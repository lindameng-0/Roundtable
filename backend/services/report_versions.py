"""Append-only Editor V3 report history."""
import uuid
from typing import Dict, List

from config import db
from utils import now_iso


async def append_report_version(manuscript_id: str, report_json: Dict, reason: str = "generated") -> Dict:
    # Let the unique constraint arbitrate concurrent regenerations, then retry
    # using the new maximum version.
    for attempt in range(3):
        latest = await db.report_versions.find({"manuscript_id": manuscript_id}, {"_id": 0}).sort("version", -1).limit(1).to_list(1)
        version = int(latest[0].get("version") or 0) + 1 if latest else 1
        row = {
            "id": str(uuid.uuid4()), "manuscript_id": manuscript_id, "version": version,
            "report_json": report_json, "reason": reason, "created_at": now_iso(),
        }
        try:
            await db.report_versions.insert_one(row)
            return row
        except Exception as exc:
            duplicate = "23505" in str(exc) or "duplicate" in str(exc).lower()
            if not duplicate or attempt == 2:
                raise
    raise RuntimeError("Could not allocate report version")


async def list_report_versions(manuscript_id: str) -> List[Dict]:
    rows = await db.report_versions.find({"manuscript_id": manuscript_id}, {"_id": 0}).sort("version", -1).to_list(100)
    return [{
        "id": row.get("id"), "version": row.get("version"), "reason": row.get("reason"),
        "created_at": row.get("created_at"), "schema_version": (row.get("report_json") or {}).get("schema_version"),
    } for row in rows]
