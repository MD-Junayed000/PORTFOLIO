import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings, validate_settings_at_startup
from database import _is_postgres
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
    created automatically. The ``preDeployCommand`` in render.yaml is not
    always honored (e.g. when the service was created manually in the
    dashboard). Running migrations in the app lifespan guarantees the
    schema is in sync with the code on every deploy, regardless of how
    the Render service is configured.
    """
    if not _is_postgres:
        # Local sqlite fallback (dev / tests) skips alembic; the test suite
        # already creates its own schema via Base.metadata.create_all.
        logger.info("Skipping alembic upgrade: non-postgres DATABASE_URL.")
        return
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    command.upgrade(cfg, "head")
    logger.info("Alembic migrations applied (head).")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    configure_cloudinary()
    # Apply database migrations before anything else touches the schema.
    # Idempotent: alembic upgrade head is a no-op when the DB is already
    # at the latest revision.
    _run_alembic_upgrade()
    initialize_collection()
    # NOTE: RAG (pgvector) is intentionally MANUAL ONLY.
    # The `document_chunks` table starts empty on every fresh database. An admin
    # MUST upload PDFs through the admin panel (POST /api/admin/upload-pdf) for
    # the chatbot to have any knowledge to retrieve. Nothing is auto-seeded.
    await seed_database()
    yield
    # Shutdown


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
