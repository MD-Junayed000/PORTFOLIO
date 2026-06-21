import os
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import Optional

from database import (
    get_db,
    AboutContent,
    Project,
    Skill,
    Research,
    Certificate,
    Experience,
    ContactMessage,
    Document,
)
from models.schemas import (
    AboutContentBase,
    AboutContentResponse,
    ProjectBase,
    ProjectResponse,
    SkillBase,
    SkillResponse,
    ResearchBase,
    ResearchResponse,
    CertificateBase,
    CertificateResponse,
    ExperienceBase,
    ExperienceResponse,
    ContactMessageResponse,
    DocumentBase,
    DocumentResponse,
    AdminSettings,
)
from routers.auth import get_current_admin
from services.vector_store import process_pdf, delete_document
from config import settings

router = APIRouter(prefix="/api/admin", tags=["admin"])

UPLOAD_DIR = "./uploads"

# Allowed image MIME types for photo uploads
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


# About
@router.put("/about", response_model=AboutContentResponse)
async def update_about(
    data: AboutContentBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(AboutContent))
    about = result.scalar_one_or_none()
    if about is None:
        about = AboutContent(**data.model_dump())
        db.add(about)
    else:
        for key, value in data.model_dump().items():
            setattr(about, key, value)
    await db.commit()
    await db.refresh(about)
    return about


# Projects
@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    data: ProjectBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    project = Project(**data.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    for key, value in data.model_dump().items():
        setattr(project, key, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()
    return {"detail": "Project deleted"}


# Skills
@router.post("/skills", response_model=SkillResponse)
async def create_skill(
    data: SkillBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    skill = Skill(**data.model_dump())
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.put("/skills/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: int,
    data: SkillBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    for key, value in data.model_dump().items():
        setattr(skill, key, value)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()
    return {"detail": "Skill deleted"}


# Research
@router.post("/research", response_model=ResearchResponse)
async def create_research(
    data: ResearchBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    research = Research(**data.model_dump())
    db.add(research)
    await db.commit()
    await db.refresh(research)
    return research


@router.put("/research/{research_id}", response_model=ResearchResponse)
async def update_research(
    research_id: int,
    data: ResearchBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Research).where(Research.id == research_id))
    research = result.scalar_one_or_none()
    if research is None:
        raise HTTPException(status_code=404, detail="Research not found")
    for key, value in data.model_dump().items():
        setattr(research, key, value)
    await db.commit()
    await db.refresh(research)
    return research


@router.delete("/research/{research_id}")
async def delete_research(
    research_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Research).where(Research.id == research_id))
    research = result.scalar_one_or_none()
    if research is None:
        raise HTTPException(status_code=404, detail="Research not found")
    await db.delete(research)
    await db.commit()
    return {"detail": "Research deleted"}


# Certificates
@router.post("/certificates", response_model=CertificateResponse)
async def create_certificate(
    data: CertificateBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    certificate = Certificate(**data.model_dump())
    db.add(certificate)
    await db.commit()
    await db.refresh(certificate)
    return certificate


@router.put("/certificates/{cert_id}", response_model=CertificateResponse)
async def update_certificate(
    cert_id: int,
    data: CertificateBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
    certificate = result.scalar_one_or_none()
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    for key, value in data.model_dump().items():
        setattr(certificate, key, value)
    await db.commit()
    await db.refresh(certificate)
    return certificate


@router.delete("/certificates/{cert_id}")
async def delete_certificate(
    cert_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
    certificate = result.scalar_one_or_none()
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    await db.delete(certificate)
    await db.commit()
    return {"detail": "Certificate deleted"}


# File uploads
@router.post("/upload-photo")
async def upload_photo(
    file: UploadFile = File(...),
    admin: dict = Depends(get_current_admin),
):
    # Validate content type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Read file content with size limit
    content = await file.read()
    if len(content) > settings.MAX_PHOTO_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_PHOTO_SIZE // (1024 * 1024)} MB",
        )

    # Generate a safe UUID-based filename to prevent path traversal
    ext = os.path.splitext(file.filename or "photo.jpg")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    safe_filename = f"photo_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(file_path, "wb") as f:
        f.write(content)
    return {"photo_url": f"/uploads/{safe_filename}"}


@router.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    topic_name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Read file content with size limit
    content = await file.read()
    if len(content) > settings.MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_PDF_SIZE // (1024 * 1024)} MB",
        )

    # Generate a safe UUID-based filename to prevent path traversal
    safe_filename = f"doc_{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(file_path, "wb") as f:
        f.write(content)

    # Process PDF for vector store
    doc_ids = process_pdf(file_path)

    # Save document metadata to DB
    document = Document(
        filename=safe_filename,
        topic=topic_name,
        original_name=file.filename,
        chunk_count=len(doc_ids),
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    return {
        "filename": safe_filename,
        "chunks_added": len(doc_ids),
        "doc_ids": doc_ids,
        "topic": topic_name,
        "document_id": document.id,
    }


@router.delete("/documents/{doc_id}")
async def remove_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    # Look up document in DB
    result = await db.execute(select(Document).where(Document.id == doc_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete vector chunks associated with this document
    try:
        for i in range(document.chunk_count):
            chunk_id = f"{document.filename}_{i}"
            delete_document(chunk_id)
    except Exception:
        pass  # Best effort deletion of vector chunks

    # Delete the file from disk
    file_path = os.path.join(UPLOAD_DIR, document.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    # Delete DB record
    await db.delete(document)
    await db.commit()
    return {"detail": "Document deleted"}


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Document).order_by(Document.uploaded_at.desc()))
    return result.scalars().all()


@router.put("/documents/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: int,
    data: DocumentBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document.topic = data.topic
    await db.commit()
    await db.refresh(document)
    return document


# Experiences
@router.post("/experiences", response_model=ExperienceResponse)
async def create_experience(
    data: ExperienceBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    experience = Experience(**data.model_dump())
    db.add(experience)
    await db.commit()
    await db.refresh(experience)
    return experience


@router.put("/experiences/{exp_id}", response_model=ExperienceResponse)
async def update_experience(
    exp_id: int,
    data: ExperienceBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Experience).where(Experience.id == exp_id))
    experience = result.scalar_one_or_none()
    if experience is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    for key, value in data.model_dump().items():
        setattr(experience, key, value)
    await db.commit()
    await db.refresh(experience)
    return experience


@router.delete("/experiences/{exp_id}")
async def delete_experience(
    exp_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Experience).where(Experience.id == exp_id))
    experience = result.scalar_one_or_none()
    if experience is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    await db.delete(experience)
    await db.commit()
    return {"detail": "Experience deleted"}


# Messages
@router.get("/messages", response_model=list[ContactMessageResponse])
async def list_messages(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(
        select(ContactMessage).order_by(ContactMessage.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/messages/{msg_id}")
async def delete_message(
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(
        select(ContactMessage).where(ContactMessage.id == msg_id)
    )
    message = result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    await db.delete(message)
    await db.commit()
    return {"detail": "Message deleted"}


# Settings
@router.get("/settings")
async def get_settings(
    admin: dict = Depends(get_current_admin),
):
    return {
        "hf_model_id": settings.HF_MODEL_ID,
        "has_token": bool(settings.HF_API_TOKEN),
    }


@router.put("/settings")
async def update_settings(
    data: AdminSettings,
    admin: dict = Depends(get_current_admin),
):
    if data.hf_model_id:
        settings.HF_MODEL_ID = data.hf_model_id
    if data.hf_api_token:
        settings.HF_API_TOKEN = data.hf_api_token
    return {"detail": "Settings updated", "model": settings.HF_MODEL_ID}


@router.delete("/settings/token")
async def clear_token(
    admin: dict = Depends(get_current_admin),
):
    settings.HF_API_TOKEN = ""
    return {"detail": "HuggingFace token cleared"}


@router.post("/settings/verify-token")
async def verify_hf_token(
    admin: dict = Depends(get_current_admin),
):
    if not settings.HF_API_TOKEN:
        raise HTTPException(status_code=400, detail="No HuggingFace token configured")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://huggingface.co/api/whoami",
                headers={"Authorization": f"Bearer {settings.HF_API_TOKEN}"},
                timeout=10.0,
            )
        if response.status_code == 200:
            return {"valid": True, "user": response.json().get("name", "unknown")}
        else:
            return {"valid": False, "detail": "Token is invalid or expired"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to verify token: {str(e)}")


# Database viewer
@router.get("/database")
async def database_viewer(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    )
    tables = result.scalars().all()

    table_info = []
    for table_name in tables:
        count_result = await db.execute(text(f"SELECT COUNT(*) FROM \"{table_name}\""))
        row_count = count_result.scalar()
        table_info.append({"name": table_name, "row_count": row_count})

    return {"tables": table_info}
