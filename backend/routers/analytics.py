"""Bounded, cookieless public counters and an authenticated owner dashboard."""
import asyncio
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from config import db
from routers.auth import _get_session_user
from services.owner import is_owner
from services.rate_limit import enforce_rate_limit

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Literal["/", "/pricing", "/beta-readers", "/ai-beta-reader", "/manuscript-feedback", "/use-cases", "/use-cases/opening-chapter-feedback", "/use-cases/pacing-feedback", "/use-cases/character-motivation", "/sample-reading", "/connect-assistant", "/terms", "/privacy", "/refunds", "/signup", "/login"]
    source: Literal["direct", "google", "bing", "other-search", "chatgpt", "perplexity", "claude", "gemini", "copilot", "social", "other"] = "direct"
    event: Literal["pageview", "signup_click"] = "pageview"


@analytics_router.post("/events", status_code=204)
async def record_event(body: Event, request: Request):
    defaults = "https://roundtable.works" if os.environ.get("ENVIRONMENT") == "production" else "http://localhost:3000,http://127.0.0.1:3000,https://roundtable.works"
    origins = {v.strip() for v in os.environ.get("CORS_ORIGINS", defaults).split(",")}
    if request.headers.get("origin") not in origins:
        raise HTTPException(403, "Origin not allowed")
    if request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1":
        return Response(status_code=204)
    await enforce_rate_limit(request, "site_analytics", 60, 60)
    try:
        await db.increment_site_analytics(body.path, body.source, body.event)
    except Exception:
        logging.getLogger(__name__).exception("Analytics counter unavailable")
        raise HTTPException(503, "Analytics temporarily unavailable")
    return Response(status_code=204)


@analytics_router.get("/summary")
async def summary(request: Request, response: Response, days: int = Query(30, ge=1, le=90)):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    user = await _get_session_user(request)
    if not is_owner(user):
        raise HTTPException(403, "Owner access required")
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=days - 1)
    rows, accounts, manuscripts, reports = await asyncio.gather(
        db.read_site_analytics(since.isoformat()),
        db.users.count_documents({"email_verified": True}),
        db.manuscripts.count_documents({}),
        db.editor_reports.count_documents({}),
    )
    sources, pages, daily = Counter(), Counter(), Counter()
    clicks = 0
    for row in rows:
        if row["event"] == "pageview":
            sources[row["source"]] += row["count"]
            pages[row["path"]] += row["count"]
            daily[str(row["day"])[:10]] += row["count"]
        elif row["event"] == "signup_click":
            clicks += row["count"]
    return {
        "days": days, "pageviews": sum(pages.values()), "signup_clicks": clicks,
        "sources": dict(sources.most_common()), "pages": dict(pages.most_common()),
        "daily": [{"day": (since + timedelta(days=i)).isoformat(), "views": daily[(since + timedelta(days=i)).isoformat()]} for i in range(days)],
        "totals": {"verified_accounts": accounts, "manuscripts": manuscripts, "reports": reports},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
