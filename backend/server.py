import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from config import db
from routers.api import api_router
from routers.auth import auth_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize = getattr(db, "initialize", None)
    if initialize:
        await initialize()
    yield
    close = getattr(db, "close", None)
    if close:
        await close()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
app.include_router(auth_router)
default_origins = (
    "https://roundtable.works"
    if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production"
    else "http://localhost:3000,http://127.0.0.1:3000,https://roundtable.works"
)
origins_raw = os.environ.get("CORS_ORIGINS", default_origins)
allow_origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
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
