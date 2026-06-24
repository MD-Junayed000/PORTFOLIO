from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pathlib import Path

# Static CV lives next to the backend package so it can be served by the
# app directly. The path is resolved relative to this file so it works
# both in local dev and on Render's deployment.
CV_DIR = Path(__file__).resolve().parent.parent / "cv"
CV_FILENAME = "Muhammad_Junayed_CV.pdf"

from database import (
    get_db,
    AboutContent,
    Project,
    Skill,
    Research,
    Certificate,
    Experience,
    ContactMessage,
    ContactInfo,
)
from models.schemas import (
    AboutContentResponse,
    ProjectResponse,
    SkillResponse,
    ResearchResponse,
    CertificateResponse,
    ExperienceResponse,
    ContactMessageBase,
    ContactMessageResponse,
    ContactInfoResponse,
)
from services.email import send_contact_notification

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/about", response_model=AboutContentResponse)
async def get_about(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AboutContent))
    about = result.scalar_one_or_none()
    # The CV is now served as a static file from the backend, not from
    # Cloudinary. We always report the canonical /api/cv URL so the
    # frontend Download CV link works regardless of what's in the DB.
    cv_url = f"/api/cv/{CV_FILENAME}" if (CV_DIR / CV_FILENAME).exists() else None
    if about is None:
        return AboutContentResponse(
            id=0,
            bio="Profile not yet configured.",
            title="Portfolio",
            photo_url=None,
            education=None,
            focus_area=None,
            subtitle=None,
            linkedin_url=None,
            github_url=None,
            scholar_url=None,
            extra_links=None,
            cv_file_path=cv_url,
            project_display_count=6,
        )
    if cv_url:
        about.cv_file_path = cv_url
    return about


@router.get("/cv/{filename}")
async def serve_cv(filename: str):
    """Serve the static CV PDF from the backend ``cv/`` folder.

    The filename is constrained to the known CV file so this route
    can't be used to read arbitrary files from disk.
    """
    if filename != CV_FILENAME:
        raise HTTPException(status_code=404, detail="CV not found")
    file_path = CV_DIR / CV_FILENAME
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="CV not found")
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=CV_FILENAME,
    )


@router.get("/projects", response_model=List[ProjectResponse])
async def get_projects(
    limit: Optional[int] = Query(None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    query = select(Project).order_by(Project.order)
    if limit is not None:
        query = query.limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/skills", response_model=List[SkillResponse])
async def get_skills(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Skill).order_by(Skill.category, Skill.name))
    return result.scalars().all()


@router.get("/research", response_model=List[ResearchResponse])
async def get_research(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Research).order_by(Research.year.desc()))
    return result.scalars().all()


@router.get("/certificates", response_model=List[CertificateResponse])
async def get_certificates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Certificate))
    certs = result.scalars().all()
    # Certificate ``file_path`` is now treated as an external URL/link
    # (e.g. https://www.credly.com/...). The browser navigates to it
    # directly, so no proxy rewrite is needed.
    return certs


@router.get("/resume")
async def get_resume():
    return {
        "resume_url": f"/api/cv/{CV_FILENAME}",
        "name": "Muhammad Junayed",
        "title": "AI Engineering Enthusiast | Computer Vision | Cloud-Native ML Systems",
    }


@router.get("/experiences", response_model=List[ExperienceResponse])
async def get_experiences(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Experience).order_by(Experience.id.desc()))
    return result.scalars().all()


@router.post("/contact", response_model=ContactMessageResponse)
async def create_contact_message(
    data: ContactMessageBase,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        message = ContactMessage(
            name=data.name,
            email=data.email,
            message=data.message,
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
    except Exception:
        # Make the failure loud in the Render logs so the difference between
        # CORS (browser-side, no server log) and a real DB error is obvious.
        import logging
        logging.getLogger(__name__).exception(
            "Contact-message insert failed for name=%r email=%r",
            data.name,
            data.email,
        )
        raise

    # Read notification emails from DB (if configured by admin)
    result = await db.execute(select(ContactInfo))
    contact_info = result.scalar_one_or_none()
    notification_emails_from_db = (
        contact_info.notification_emails if contact_info else None
    )

    # Send email notification in background (non-blocking, best-effort)
    background_tasks.add_task(
        send_contact_notification,
        sender_name=data.name,
        sender_email=data.email,
        message=data.message,
        notification_emails_from_db=notification_emails_from_db,
    )

    return message


@router.get("/contact-info", response_model=ContactInfoResponse)
async def get_contact_info(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContactInfo))
    info = result.scalar_one_or_none()
    if info is None:
        return ContactInfoResponse(
            id=0,
            email=None,
            phone=None,
            address=None,
            notification_emails=None,
        )
    return info
