from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from datetime import datetime, timezone
from config import settings


engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class AboutContent(Base):
    __tablename__ = "about_content"

    id = Column(Integer, primary_key=True, index=True)
    bio = Column(Text, nullable=False)
    title = Column(String(255), nullable=False)
    photo_url = Column(String(500), nullable=True)
    education = Column(Text, nullable=True)
    focus_area = Column(Text, nullable=True)
    subtitle = Column(String(500), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    github_url = Column(String(500), nullable=True)
    scholar_url = Column(String(500), nullable=True)
    extra_links = Column(Text, nullable=True)  # JSON string of [{name, url, icon}]
    cv_file_path = Column(String(500), nullable=True)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    tech_stack = Column(String(500), nullable=False)
    repo_url = Column(String(500), nullable=True)
    demo_url = Column(String(500), nullable=True)
    image_url = Column(String(500), nullable=True)
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


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    issuer = Column(String(255), nullable=True)
    date = Column(String(50), nullable=True)
    file_path = Column(String(500), nullable=True)


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


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
