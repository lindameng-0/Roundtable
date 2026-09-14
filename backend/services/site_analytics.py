"""Privacy-limited site analytics helpers shared by public and auth routes."""
from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import Request

from services.rate_limit import client_ip


logger = logging.getLogger(__name__)


def measurement_disabled(request: Request) -> bool:
    return request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1"


def visitor_hash(request: Request) -> str | None:
    """Return a non-reversible, keyed network identifier; never persist the IP."""
    from config import ANALYTICS_HASH_SECRET

    if not ANALYTICS_HASH_SECRET or measurement_disabled(request):
        return None
    return hmac.new(
        ANALYTICS_HASH_SECRET.encode("utf-8"),
        f"readerfold-analytics-v1:{client_ip(request)}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def record_site_event(request: Request, path: str, source: str, event: str) -> None:
    """Record an aggregate event plus an optional deduplication identifier."""
    if measurement_disabled(request):
        return
    from config import db

    await db.increment_site_analytics(path, source, event, visitor_hash(request))
