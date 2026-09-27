"""App entrypoint.

Serves the JSON API and the single-page frontend from the same origin, so
there is no CORS configuration anywhere in this project.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import router
from app.seed_data import build_seed
from app.store import get_store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("fitfest")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(
    title="OpportunityHub -- Student Opportunity Discovery",
    description=(
        "Aggregates internships, hackathons, scholarships, courses, "
        "certifications, competitions and workshops behind a single "
        "skill-aware search, with explainable recommendations."
    ),
    version="1.0.0",
)
app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    store = get_store()
    log.info("store=%s", type(store).__name__)

    # The in-memory store is per-process. Multiple workers would each hold
    # their own copy, so a bookmark saved via one worker would be invisible
    # to the next. Fail loudly rather than silently losing user data.
    workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
    if type(store).__name__ == "MemoryStore" and workers > 1:
        raise RuntimeError(
            f"MemoryStore is per-process but WEB_CONCURRENCY={workers}. "
            "Use --workers 1 locally, or deploy to Cloud Run (Firestore) to scale out."
        )

    if config.SEED_ON_START:
        added = store.seed(build_seed())
        log.info("seeded %s listings (total %s)", added, store.count_opportunities())


@app.get("/healthz")
def healthz():
    store = get_store()
    return {"status": "ok", "store": type(store).__name__, "listings": store.count_opportunities()}


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
