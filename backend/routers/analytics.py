"""Bounded anonymous counters, excluding authenticated owner traffic."""
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
from services.site_analytics import MEASUREMENT_PREFIX, record_site_event

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Account emails are normalized by both password and Google sign-in.
# These exclusions affect dashboard totals only, never account access or data.
EXCLUDED_ACCOUNT_EMAILS = (
    "itsyuko0o1@gmail.com",
    "lndmeng@gmail.com",
    "lndmeng@g.ucla.edu",
)


async def excluded_account_totals():
    users = await asyncio.gather(*(
        db.users.find_one({"email": email}) for email in EXCLUDED_ACCOUNT_EMAILS
    ))
    excluded_users = {user["user_id"]: user for user in users if user and user.get("user_id")}
    manuscript_counts = await asyncio.gather(*(
        db.manuscripts.count_documents({"user_id": user_id}) for user_id in excluded_users
    ))
    return (
        sum(user.get("email_verified") is True for user in excluded_users.values()),
        sum(manuscript_counts),
    )


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Literal["/", "/pricing", "/beta-readers", "/ai-beta-reader", "/manuscript-feedback", "/use-cases", "/use-cases/opening-chapter-feedback", "/use-cases/pacing-feedback", "/use-cases/character-motivation", "/sample-reading", "/connect-assistant", "/terms", "/privacy", "/refunds", "/signup", "/login", "/guides", "/guides/llm-manuscript-feedback", "/guides/beta-reader-questionnaire", "/guides/conflicting-beta-reader-feedback", "/guides/beta-reader-questionnaire/fantasy", "/guides/beta-reader-questionnaire/romance", "/guides/beta-reader-questionnaire/mystery", "/guides/beta-reader-questionnaire/thriller", "/blog", "/blog/finished-first-draft", "/blog/earned-plot-twist", "/blog/ai-feedback-your-voice", "/sample-reading/fantasy-magic-cost", "/sample-reading/romance-earned-trust"]
    source: Literal["direct", "google", "bing", "other-search", "chatgpt", "perplexity", "claude", "gemini", "copilot", "social", "other"] = "direct"
    event: Literal["pageview", "signup_click", "signup_submit", "google_continue_click"] = "pageview"


@analytics_router.post("/events", status_code=204)
async def record_event(body: Event, request: Request):
    defaults = "https://roundtable.works" if os.environ.get("ENVIRONMENT") == "production" else "http://localhost:3000,http://127.0.0.1:3000,https://roundtable.works"
    origins = {v.strip() for v in os.environ.get("CORS_ORIGINS", defaults).split(",")}
    if request.headers.get("origin") not in origins:
        raise HTTPException(403, "Origin not allowed")
    await enforce_rate_limit(request, "site_analytics", 60, 60)
    if request.cookies.get("session_token"):
        try:
            user = await _get_session_user(request)
        except HTTPException as error:
            if error.status_code != 401:
                raise
        else:
            if is_owner(user):
                return Response(status_code=204)
    try:
        await record_site_event(request, body.path, body.source, body.event)
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
    rows, visitors, accounts, manuscripts, reports, excluded = await asyncio.gather(
        db.read_site_analytics(since.isoformat()),
        db.read_site_analytics_visitors(since.isoformat()),
        db.users.count_documents({"email_verified": True}),
        db.manuscripts.count_documents({}),
        db.editor_reports.count_documents({}),
        excluded_account_totals(),
    )
    # A new measurement series hides legacy traffic without deleting records.
    rows = [{**row, "event": row["event"][len(MEASUREMENT_PREFIX):]} for row in rows if row["event"].startswith(MEASUREMENT_PREFIX)]
    visitors = [{**row, "event": row["event"][len(MEASUREMENT_PREFIX):]} for row in visitors if row["event"].startswith(MEASUREMENT_PREFIX)]
    sources, pages, daily, events = Counter(), Counter(), Counter(), Counter()
    for row in rows:
        if row["event"] == "pageview":
            sources[row["source"]] += row["count"]
            pages[row["path"]] += row["count"]
            daily[str(row["day"])[:10]] += row["count"]
        else:
            events[row["event"]] += row["count"]
    unique_by_event = {
        event: len({row["visitor_hash"] for row in visitors if row["event"] == event})
        for event in {row["event"] for row in visitors}
    }
    unique_clicks_by_path = {
        path: len({row["visitor_hash"] for row in visitors if row["event"] == "signup_click" and row["path"] == path})
        for path in {row["path"] for row in visitors if row["event"] == "signup_click"}
    }
    funnel = {
        "signup_pageviews": pages["/signup"],
        "signup_clicks": events["signup_click"],
        "unique_signup_click_visitors": unique_by_event.get("signup_click", 0),
        "signup_submissions": events["signup_submit"],
        "unique_signup_submit_visitors": unique_by_event.get("signup_submit", 0),
        "signup_accepted": events["signup_accepted"],
        "signup_email_failed": events["signup_email_failed"],
        "email_verified": events["email_verified"],
        "google_auth_started": events["google_auth_started"],
        "google_signup_completed": events["google_signup_completed"],
    }
    viewed = {row["visitor_hash"] for row in visitors if row["event"] == "pageview"}
    interested = {row["visitor_hash"] for row in visitors if row["event"] in {"signup_click", "signup_submit"} or (row["event"] == "google_continue_click" and row["path"] == "/signup")}
    def breakdown(field):
        return sorted([
            {"name": name,
             "visitors": len({row["visitor_hash"] for row in visitors if row[field] == name and row["event"] == "pageview"}),
             "signup_click_visitors": len({row["visitor_hash"] for row in visitors if row[field] == name and row["event"] == "signup_click"})}
            for name in {row[field] for row in visitors if row["event"] in {"pageview", "signup_click"}}
        ], key=lambda row: (-row["signup_click_visitors"], -row["visitors"], row["name"]))
    from config import ANALYTICS_HASH_SECRET
    return {
        "measurement_series": "interest_v2", "distinct_available": bool(ANALYTICS_HASH_SECRET),
        "unique_visitors": len(viewed), "interested_visitors": len(interested),
        "interest_rate": round(100 * len(viewed & interested) / len(viewed), 1) if viewed else None,
        "visitor_pages": breakdown("path"), "visitor_sources": breakdown("source"),
        "daily_visitors": [{"day": (since + timedelta(days=i)).isoformat(), "visitors": len({row["visitor_hash"] for row in visitors if row["event"] == "pageview" and str(row["day"])[:10] == (since + timedelta(days=i)).isoformat()})} for i in range(days)],
        "days": days, "pageviews": sum(pages.values()), "signup_clicks": events["signup_click"],
        "unique_signup_click_visitors": unique_by_event.get("signup_click", 0),
        "unique_signup_clicks_by_path": unique_clicks_by_path, "funnel": funnel,
        "sources": dict(sources.most_common()), "pages": dict(pages.most_common()),
        "daily": [{"day": (since + timedelta(days=i)).isoformat(), "views": daily[(since + timedelta(days=i)).isoformat()]} for i in range(days)],
        "totals": {"verified_accounts": max(0, accounts - excluded[0]),
                   "manuscripts": max(0, manuscripts - excluded[1]), "reports": reports},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
