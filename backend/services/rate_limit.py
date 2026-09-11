"""Small process-local sliding-window limiter for a single-instance deployment."""
from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class SlidingWindowRateLimiter:
    def __init__(self):
        self._events = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def enforce(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, math.ceil(events[0] + window_seconds - now))
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)

    def clear(self) -> None:
        self._events.clear()


limiter = SlidingWindowRateLimiter()


def client_ip(request: Request) -> str:
    # Let the ASGI server resolve forwarding headers from explicitly trusted
    # proxies. Arbitrary caller-controlled X-Forwarded-For must not bypass limits.
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    request: Request,
    scope: str,
    limit: int,
    window_seconds: int,
    identity: str | None = None,
) -> None:
    subject = identity or f"ip:{client_ip(request)}"
    key = f"{scope}:{subject}"
    # PostgreSQL provides an atomic shared bucket across workers and instances.
    # Memory/Supabase development backends retain the process-local fallback.
    from config import db
    consume = getattr(db, "consume_rate_limit", None)
    if consume:
        result = await consume(key, limit, window_seconds)
        if not result["allowed"]:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(result["retry_after"])},
            )
        return
    await limiter.enforce(key, limit, window_seconds)
