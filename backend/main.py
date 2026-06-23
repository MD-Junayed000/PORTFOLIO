from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from config import settings, validate_settings_at_startup
from services.vector_store import initialize_collection
from services.seed_data import seed_database, seed_vector_store
from services.cloudinary_service import configure_cloudinary
from routers import auth, admin, public, chat

# Validate critical settings before the app starts accepting requests
validate_settings_at_startup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    configure_cloudinary()
    # Schema is owned by Alembic; run `alembic upgrade head` on deploy.
    initialize_collection()
    await seed_database()
    seed_vector_store()
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

# Permanent image storage lives in Cloudinary. We do NOT mount a local
# uploads directory on Render because the disk is ephemeral.

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(public.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "Muhammad Junayed Portfolio API is running"}
