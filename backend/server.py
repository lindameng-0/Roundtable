import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from config import db
from routers.api import api_router
from routers.auth import auth_router
from routers.jobs import jobs_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize = getattr(db, "initialize", None)
    if initialize:
        await initialize()
    cleanup_costs = getattr(db, "cleanup_stale_cost_reservations", None)
    if cleanup_costs:
        released = await cleanup_costs()
        if released:
            logging.getLogger(__name__).warning("Released %s stale AI cost reservation(s)", released)
    yield
    close = getattr(db, "close", None)
    if close:
        await close()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
app.include_router(auth_router)
app.include_router(jobs_router)
default_origins = (
    "https://roundtable.works"
    if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production"
    else "http://localhost:3000,http://127.0.0.1:3000,https://roundtable.works"
)
origins_raw = os.environ.get("CORS_ORIGINS", default_origins)
allow_origins = [o.strip() for o in origins_raw.split(",") if o.strip()]


@app.middleware("http")
async def reject_cross_site_cookie_requests(request: Request, call_next):
    """Prevent cross-site use of the session cookie, including costly GET streams."""
    protected_prefixes = ("/api/manuscripts", "/api/jobs", "/api/user", "/api/config/model", "/api/auth/logout")
    if (
        os.environ.get("ENVIRONMENT", "development").strip().lower() == "production"
        and request.cookies.get("session_token")
        and request.url.path.startswith(protected_prefixes)
        and request.headers.get("origin") not in allow_origins
    ):
        return JSONResponse({"detail": "Cross-site request rejected"}, status_code=403)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
