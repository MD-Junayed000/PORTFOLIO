from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from database import (
    get_db,
    AboutContent,
    Project,
    Skill,
    Research,
    Certificate,
    Experience,
    ContactMessage,
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
)

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/about", response_model=AboutContentResponse)
async def get_about(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AboutContent))
    about = result.scalar_one_or_none()
    if about is None:
        return AboutContentResponse(
            id=0,
            bio="Profile not yet configured.",
            title="Portfolio",
            photo_url=None,
        )
    return about


@router.get("/projects", response_model=List[ProjectResponse])
async def get_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.order))
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
    return result.scalars().all()


@router.get("/resume")
async def get_resume():
    return {
        "resume_url": "/uploads/Muhammad_Junayed_CV.pdf",
        "name": "Muhammad Junayed",
        "title": "AI Engineering Enthusiast | Computer Vision | Cloud-Native ML Systems",
    }


@router.get("/experiences", response_model=List[ExperienceResponse])
async def get_experiences(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Experience).order_by(Experience.id.desc()))
    return result.scalars().all()


@router.post("/contact", response_model=ContactMessageResponse)
async def create_contact_message(
    data: ContactMessageBase, db: AsyncSession = Depends(get_db)
):
    message = ContactMessage(
        name=data.name,
        email=data.email,
        message=data.message,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message
