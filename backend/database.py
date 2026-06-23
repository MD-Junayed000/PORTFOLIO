import logging
from typing import Tuple

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from datetime import datetime, timezone
from config import settings


logger = logging.getLogger(__name__)


# asyncpg (the driver SQLAlchemy uses for postgresql+asyncpg://) does NOT
# accept libpq-style kwargs like `sslmode` or `channel_binding`. When the URL
# contains `?sslmode=require` (the default Neon pooled string), SQLAlchemy
# forwards every query-string parameter to asyncpg.connect() and crashes with:
#     TypeError: connect() got an unexpected keyword argument 'sslmode'
# We must strip those keys from the URL ourselves and enable SSL via
# `connect_args={"ssl": True}` instead.
#
# This helper also:
#   - rewrites `postgres://` -> `postgresql+asyncpg://` (Render/Heroku-style
#     legacy strings),
#   - drops `channel_binding=require` (asyncpg rejects it),
#   - falls back to a local sqlite file when DATABASE_URL is empty so dev
#     and the existing pytest suite (test_api.py) keep working,
#   - never raises at import time; bad URLs are logged and we fall back to
#     sqlite so the app still starts in environments without a DB.
_ASYNCPG_INCOMPATIBLE_QUERY_KEYS = {"sslmode", "ssl", "channel_binding"}
_DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./portfolio.db"


def _normalize_database_url(url: str) -> Tuple[str, dict]:
    """Return ``(clean_url, engine_kwargs)`` safe to feed to ``create_async_engine``."""
    if not url:
        return _DEFAULT_SQLITE_URL, {"echo": False}

    try:
        parsed = make_url(url)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Invalid DATABASE_URL %r (%s); falling back to sqlite.", url, exc)
        return _DEFAULT_SQLITE_URL, {"echo": False}

    # Force the asyncpg driver for postgresql URLs.
    drivername = parsed.drivername or ""
    if drivername in ("postgres", "postgresql"):
        parsed = parsed.set(drivername="postgresql+asyncpg")
    elif drivername.startswith("postgresql+") and "asyncpg" not in drivername:
        # e.g. postgresql+psycopg2 — rewrite to asyncpg for parity with the rest
        # of the stack (we only use async features elsewhere).
        parsed = parsed.set(drivername="postgresql+asyncpg")

    # Drop libpq-style keys that asyncpg cannot consume.
    query = dict(parsed.query or {})
    had_ssl = False
    for key in _ASYNCPG_INCOMPATIBLE_QUERY_KEYS:
        if key in query:
            if key in ("sslmode", "ssl"):
                had_ssl = True
            query.pop(key, None)
    parsed = parsed.set(query=query)

    engine_kwargs: dict = {"echo": False}
    if had_ssl and (parsed.drivername or "").startswith("postgresql+asyncpg"):
        engine_kwargs["connect_args"] = {"ssl": True}

    return parsed.render_as_string(hide_password=False), engine_kwargs


def build_clean_database_url(url: str) -> str:
    """Return only the URL string (without engine kwargs), safe to feed to alembic.

    Alembic reads ``sqlalchemy.url`` from alembic.ini at the time it constructs
    its own engine. If we hand it the raw Neon connection string, asyncpg will
    fail with ``TypeError: connect() got an unexpected keyword argument
    'sslmode'`` exactly as it did in the app engine. We strip the same
    libpq-style query keys here so alembic uses the same clean URL the app uses.
    """
    return _normalize_database_url(url)[0]


_db_url, _engine_kwargs = _normalize_database_url(settings.DATABASE_URL)

engine = create_async_engine(_db_url, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Exposed for main.py to decide whether to run ``alembic upgrade head`` on
# startup. The local sqlite fallback (used by tests and by developers who
# have not set DATABASE_URL) skips alembic because the test suite already
# creates its own schema via ``Base.metadata.create_all``.
_is_postgres = (_db_url.split("+", 1)[0] if _db_url else "").startswith("postgres")


class Base(DeclarativeBase):
    pass


class AboutContent(Base):
    __tablename__ = "about_content"

    id = Column(Integer, primary_key=True, index=True)
    bio = Column(Text, nullable=False)
    title = Column(String(255), nullable=False)
    photo_url = Column(String(500), nullable=True)
    photo_public_id = Column(String(500), nullable=True)
    education = Column(Text, nullable=True)
    focus_area = Column(Text, nullable=True)
    subtitle = Column(String(500), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    github_url = Column(String(500), nullable=True)
    scholar_url = Column(String(500), nullable=True)
    extra_links = Column(Text, nullable=True)  # JSON string of [{name, url, icon}]
    cv_file_path = Column(String(500), nullable=True)
    cv_public_id = Column(String(500), nullable=True)
    project_display_count = Column(Integer, nullable=True, default=6)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    tech_stack = Column(String(500), nullable=False)
    repo_url = Column(String(500), nullable=True)
    demo_url = Column(String(500), nullable=True)
    image_url = Column(String(500), nullable=True)
    image_public_id = Column(String(500), nullable=True)
    order = Column(Integer, default=0)


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    proficiency = Column(Float, default=0.0)


class Research(Base):
    __tablename__ = "research"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    venue = Column(String(255), nullable=True)
    year = Column(Integer, nullable=True)
    status = Column(String(50), nullable=True)
    link = Column(String(500), nullable=True)


class Experience(Base):
    __tablename__ = "experiences"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    organization = Column(String(255), nullable=False)
    period = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    logo_url = Column(String(500), nullable=True)
    logo_public_id = Column(String(500), nullable=True)


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    issuer = Column(String(255), nullable=True)
    date = Column(String(50), nullable=True)
    file_path = Column(String(500), nullable=True)
    file_public_id = Column(String(500), nullable=True)


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ContactInfo(Base):
    __tablename__ = "contact_info"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(100), nullable=True)
    address = Column(String(500), nullable=True)
    notification_emails = Column(Text, nullable=True)  # Comma-separated emails


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(500), nullable=False)
    topic = Column(String(255), nullable=True)
    original_name = Column(String(500), nullable=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    chunk_count = Column(Integer, default=0)
    cloudinary_public_id = Column(String(500), nullable=True)


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
