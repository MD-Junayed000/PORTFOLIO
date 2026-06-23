import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings, validate_settings_at_startup
from database import _is_postgres, _db_url
from services.vector_store import initialize_collection
from services.seed_data import seed_database
from services.cloudinary_service import configure_cloudinary
from routers import auth, admin, public, chat

logger = logging.getLogger(__name__)

# Validate critical settings BEFORE FastAPI starts accepting requests.
# Runs at import time, so a misconfigured env var fails the deploy with a
# clear error instead of an opaque "Exited with status 3".
validate_settings_at_startup()


def _run_alembic_upgrade() -> None:
    """Run ``alembic upgrade head`` programmatically against the live engine.

    Render-managed Postgres (Neon) is external to Render, so tables are NOT
    created automatically. Running migrations in the app lifespan guarantees
    the schema is in sync with the code on every deploy, regardless of how
    the Render service is configured (manual dashboard service or
    render.yaml-managed).

    Any failure is re-raised with the full traceback logged first, so the
    deploy log shows the root cause instead of a silent
    ``Exited with status 3``.
    """
    if not _is_postgres:
        # Local sqlite fallback (dev / tests) skips alembic; the test suite
        # already creates its own schema via Base.metadata.create_all.
        logger.info("Skipping alembic upgrade: non-postgres DATABASE_URL.")
        return

    logger.info("Running alembic upgrade head against %s ...", _db_url.split("@")[-1])
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("script_location", "migrations")

    try:
        command.upgrade(cfg, "head")
    except Exception:
        # Log the full traceback ourselves so the cause is visible in the
        # Render deploy log even if uvicorn's handler is not yet wired up
        # (it is the lifespan exception that triggers the silent exit-3).
        logger.exception("Alembic upgrade head FAILED")
        raise
    logger.info("Alembic migrations applied (head).")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Lifespan: configuring Cloudinary ...")
    configure_cloudinary()
    # Apply database migrations before anything else touches the schema.
    # Idempotent: alembic upgrade head is a no-op when the DB is already
    # at the latest revision. Any failure is re-raised (and logged via
    # ``logger.exception``) so the deploy log shows the cause instead of
    # the silent ``Exited with status 3`` we were seeing before.
    _run_alembic_upgrade()
    logger.info("Lifespan: initializing vector collection ...")
    initialize_collection()
    # NOTE: RAG (pgvector) is intentionally MANUAL ONLY.
    # The `document_chunks` table starts empty on every fresh database. An admin
    # MUST upload PDFs through the admin panel (POST /api/admin/upload-pdf) for
    # the chatbot to have any knowledge to retrieve. Nothing is auto-seeded.
    logger.info("Lifespan: seeding database ...")
    await seed_database()
    logger.info("Lifespan: startup complete.")
    yield
    # Shutdown
    logger.info("Lifespan: shutdown.")


app = FastAPI(
    title="Muhammad Junayed Portfolio API",
    description="Backend API for Muhammad Junayed's portfolio website with RAG chatbot",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
# In production, set CORS_ORIGINS to your specific frontend URL(s).
# Optionally set CORS_ORIGIN_REGEX for Vercel preview deployment patterns.
# Example: CORS_ORIGIN_REGEX=r"https://portfolio-junayed(-[a-z0-9]+)?\.vercel\.app"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------
# FastAPI's CORSMiddleware only adds the ``Access-Control-Allow-Origin`` header
# to responses that flow back through the middleware stack. When an unhandled
# exception escapes a route handler (e.g. an asyncpg / pgvector / HF embedding
# error inside ``/api/admin/upload-pdf``), Starlette's ``ServerErrorMiddleware``
# builds a plain ``text/plain`` 500 response that *bypasses* CORSMiddleware.
# The browser then reports the failure as a CORS error, even though the real
# problem is on the server.
#
# The handler below intercepts every uncaught exception, logs the traceback,
# and returns a JSON 500 with CORS headers manually re-attached. The Origin
# header is echoed back (when present) so credentialed XHR stays valid.
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception for %s %s", request.method, request.url.path
    )
    origin = request.headers.get("origin")
    headers = {}
    if origin and _is_origin_allowed(origin):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. See server logs."},
        headers=headers,
    )


def _is_origin_allowed(origin: str) -> bool:
    """Mirror CORSMiddleware's allow_origins + allow_origin_regex for 500s."""
    if not origin:
        return False
    if origin in settings.CORS_ORIGINS:
        return True
    pattern = settings.CORS_ORIGIN_REGEX
    if pattern and re.match(pattern, origin):
        return True
    return False

# All user-uploaded files (photos, CVs, certificates, RAG source PDFs) are
# stored permanently in Cloudinary. We do not keep a local uploads/ directory
# because the Render disk is ephemeral.

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(public.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "Muhammad Junayed Portfolio API is running"}
