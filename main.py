"""App entrypoint.

Serves the JSON API and the single-page frontend from the same origin, so
there is no CORS configuration anywhere in this project.
"""

import logging
import os

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import router
from app.seed_data import build_seed
from app.store import degraded_reason, get_store_resilient

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
    # Resilient: a broken or unreachable database must not stop the site from
    # serving, or a bad MONGODB_URI means a judge sees nothing at all.
    store = get_store_resilient()
    log.info("store=%s", type(store).__name__)

    degraded = degraded_reason()
    if degraded:
        log.error("RUNNING DEGRADED: the configured database failed -> %s", degraded)

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
    store = get_store_resilient()
    degraded = degraded_reason()
    return {
        "status": "degraded" if degraded else "ok",
        "store": type(store).__name__,
        "listings": store.count_opportunities(),
        "dbBackend": config.DB_BACKEND,
        # Present so a broken database is visible rather than silent.
        "degradedReason": degraded,
    }


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/index.html", include_in_schema=False)
    def index_html():
        # People share ".../index.html" URLs, and a 404 there looks like a dead
        # link rather than a routing detail. Serve the same file.
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        # The inline SVG favicon in index.html is enough; without this route the
        # browser still requests /favicon.ico and gets a 404 in the console.
        return Response(status_code=204)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        """Serve the SPA for unknown, non-API paths.

        Without this, /login or /dashboard return 404, so a hand-typed or
        shared clean URL looks like a broken site. Unknown /api/* paths are
        deliberately left to FastAPI so real API 404s stay JSON.
        """
        if full_path.startswith(("api/", "static/", "docs", "openapi.json")):
            raise HTTPException(404, "Not Found")
        candidate = os.path.normpath(os.path.join(STATIC_DIR, full_path))
        # Never let a crafted path escape the static directory.
        if os.path.isfile(candidate) and os.path.abspath(candidate).startswith(
            os.path.abspath(STATIC_DIR)
        ):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
