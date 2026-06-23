import time
import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import Any, Dict, List, Optional

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
    AboutContentBase,
    AboutContentResponse,
    ProjectBase,
    ProjectResponse,
    ProjectReorderRequest,
    SkillBase,
    SkillResponse,
    ResearchBase,
    ResearchResponse,
    CertificateBase,
    CertificateResponse,
    ExperienceBase,
    ExperienceResponse,
    ContactMessageResponse,
    AdminSettings,
    ContactInfoBase,
    ContactInfoResponse,
)
from routers.auth import get_current_admin
from services import rag_pipeline
from services.cloudinary_service import (
    configure_cloudinary,
    upload_image,
    upload_pdf,
    delete_asset,
)
from config import settings

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Make sure Cloudinary is configured before any upload is attempted
configure_cloudinary()

# Allowed image MIME types for photo uploads
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# Allowed MIME types for certificate file uploads
ALLOWED_CERT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}

logger = logging.getLogger(__name__)


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
    if project.image_public_id:
        delete_asset(project.image_public_id, resource_type="image")
    await db.delete(project)
    await db.commit()
    return {"detail": "Project deleted"}


@router.post("/projects/reorder")
async def reorder_projects(
    data: ProjectReorderRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    # Fetch all relevant projects in a single query to avoid N+1
    project_ids = [item.id for item in data.projects]
    result = await db.execute(select(Project).where(Project.id.in_(project_ids)))
    projects_map = {p.id: p for p in result.scalars().all()}

    for item in data.projects:
        project = projects_map.get(item.id)
        if project:
            project.order = item.order

    await db.commit()
    return {"detail": "Projects reordered"}


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
@router.get("/certificates", response_model=List[CertificateResponse])
async def admin_list_certificates(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    """Return the raw Cloudinary URLs (no proxy rewrite) for the admin UI.

    The public ``GET /api/certificates`` rewrites each ``file_path`` to a
    proxy URL so the public site can render the PDF inline. The admin
    form, however, needs the *original* Cloudinary URL — otherwise editing
    a certificate would overwrite the stored public_id with the proxy
    path and break future uploads.
    """
    result = await db.execute(select(Certificate))
    return result.scalars().all()


@router.get("/about", response_model=AboutContentResponse)
async def admin_get_about(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    """Return the raw ``cv_file_path`` (no proxy rewrite) for the admin UI."""
    result = await db.execute(select(AboutContent))
    about = result.scalar_one_or_none()
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
            cv_file_path=None,
            project_display_count=6,
        )
    return about


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

    # Best-effort delete of the Cloudinary asset. The DB row is the source
    # of truth, so a Cloudinary failure must not block the DB delete.
    if certificate.file_public_id:
        resource_type = "raw" if (certificate.file_path or "").lower().endswith(".pdf") else "image"
        delete_asset(certificate.file_public_id, resource_type=resource_type)

    await db.delete(certificate)
    await db.commit()
    return {"detail": "Certificate deleted"}


# File uploads (Cloudinary)
@router.post("/upload-photo")
async def upload_photo(
    file: UploadFile = File(...),
    target: Optional[str] = None,
    target_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    """Upload an image to Cloudinary and return the URL.

    ``target`` controls which row in the database is updated so that uploading
    a project image, a certificate logo, or an experience logo never clobbers
    the profile photo on the About row. Supported values:

    - ``"about"``   (default) — writes to ``AboutContent.photo_url``.
    - ``"project"``  — requires ``target_id``; writes to ``Project.image_url``.
    - ``"experience"`` — requires ``target_id``; writes to ``Experience.logo_url``.
    - ``"certificate"`` — requires ``target_id``; writes to ``Certificate.logo_url``.
    - ``"none"``    — only uploads to Cloudinary; the caller stores the URL
      itself (e.g. inside ``extra_metadata`` of a draft entry).

    Old Cloudinary assets referenced by the row being updated are deleted
    automatically.
    """
    if target is None:
        target = "about"
    target = target.lower().strip()
    if target not in {"about", "project", "experience", "certificate", "none"}:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid target. Use one of: about, project, experience, "
                "certificate, none."
            ),
        )

    # Validate content type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    # Read file content with size limit
    content = await file.read()
    if len(content) > settings.MAX_PHOTO_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_PHOTO_SIZE // (1024 * 1024)} MB",
        )

    # Upload to Cloudinary
    try:
        secure_url, public_id = upload_image(content, original_filename=file.filename)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Persist the URL to the right row, deleting the old Cloudinary asset
    # only if it actually belonged to that row (so a project image upload
    # never deletes the profile photo's Cloudinary asset).
    if target == "about":
        result = await db.execute(select(AboutContent))
        about = result.scalar_one_or_none()
        if about is None:
            about = AboutContent(bio="", title="Portfolio")
            db.add(about)
        if about.photo_public_id and about.photo_public_id != public_id:
            delete_asset(about.photo_public_id, resource_type="image")
        about.photo_url = secure_url
        about.photo_public_id = public_id
    elif target == "project":
        if target_id is None:
            raise HTTPException(
                status_code=400,
                detail="target_id is required when target=project",
            )
        result = await db.execute(select(Project).where(Project.id == target_id))
        project = result.scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.image_public_id and project.image_public_id != public_id:
            delete_asset(project.image_public_id, resource_type="image")
        project.image_url = secure_url
        project.image_public_id = public_id
    elif target == "experience":
        if target_id is None:
            raise HTTPException(
                status_code=400,
                detail="target_id is required when target=experience",
            )
        result = await db.execute(select(Experience).where(Experience.id == target_id))
        exp = result.scalar_one_or_none()
        if exp is None:
            raise HTTPException(status_code=404, detail="Experience not found")
        if exp.logo_public_id and exp.logo_public_id != public_id:
            delete_asset(exp.logo_public_id, resource_type="image")
        exp.logo_url = secure_url
        exp.logo_public_id = public_id
    elif target == "certificate":
        if target_id is None:
            raise HTTPException(
                status_code=400,
                detail="target_id is required when target=certificate",
            )
        result = await db.execute(
            select(Certificate).where(Certificate.id == target_id)
        )
        cert = result.scalar_one_or_none()
        if cert is None:
            raise HTTPException(status_code=404, detail="Certificate not found")
        if cert.image_public_id and cert.image_public_id != public_id:
            delete_asset(cert.image_public_id, resource_type="image")
        cert.image_url = secure_url
        cert.image_public_id = public_id
    # target == "none" → just upload; caller stores the URL itself.

    await db.commit()

    return {
        "photo_url": secure_url,
        "public_id": public_id,
        "target": target,
        "target_id": target_id,
    }


@router.post("/upload-cv")
async def upload_cv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read file content with size limit
    content = await file.read()
    if len(content) > settings.MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_PDF_SIZE // (1024 * 1024)} MB",
        )

    # Upload to Cloudinary as a raw resource (PDF)
    try:
        secure_url, public_id = upload_pdf(content, original_filename=file.filename)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Persist URL + public_id to the AboutContent row, deleting the old CV
    # from Cloudinary if it existed.
    result = await db.execute(select(AboutContent))
    about = result.scalar_one_or_none()
    if about is None:
        about = AboutContent(bio="", title="Portfolio")
        db.add(about)
    if about.cv_public_id and about.cv_public_id != public_id:
        delete_asset(about.cv_public_id, resource_type="raw")
    about.cv_file_path = secure_url
    about.cv_public_id = public_id
    await db.commit()
    await db.refresh(about)

    return {"cv_url": secure_url, "public_id": public_id, "filename": file.filename}


@router.delete("/cv")
async def delete_cv(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(AboutContent))
    about = result.scalar_one_or_none()
    if about is None or not about.cv_file_path:
        raise HTTPException(status_code=404, detail="No CV file found")

    # Delete from Cloudinary (best effort)
    if about.cv_public_id:
        delete_asset(about.cv_public_id, resource_type="raw")

    about.cv_file_path = None
    about.cv_public_id = None
    await db.commit()
    return {"detail": "CV deleted"}


@router.post("/upload-certificate")
async def upload_certificate(
    file: UploadFile = File(...),
    admin: dict = Depends(get_current_admin),
):
    # Validate content type
    if file.content_type not in ALLOWED_CERT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: images and PDF",
        )

    # Read file content with size limit
    content = await file.read()
    if len(content) > settings.MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_PDF_SIZE // (1024 * 1024)} MB",
        )

    # Choose resource type based on content
    if file.content_type == "application/pdf":
        try:
            secure_url, public_id = upload_pdf(content, original_filename=file.filename)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
    else:
        try:
            secure_url, public_id = upload_image(content, original_filename=file.filename)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    return {"file_url": secure_url, "public_id": public_id}


# NOTE: The legacy `/upload-pdf`, `/debug/process-pdf`, `/documents/*`, and
# `/rag/documents` + `/rag/reindex-all` endpoints have been removed.
# The RAG knowledge base is loaded automatically at every FastAPI startup
# from `settings.PDF_PATH`; the admin panel no longer manages per-PDF
# ingestion. The single read-only `/rag/status` endpoint below surfaces the
# in-memory pipeline state for diagnostics.


# NOTE: The legacy `/debug/process-pdf` endpoint has been removed; the new
# in-memory RAG pipeline surfaces its state through `/rag/status` below.
# The `/documents` CRUD and `/upload-pdf` are also gone — the chatbot reads
# exclusively from the PDF auto-loaded at startup.


# NOTE: The legacy `/documents` CRUD endpoints (`GET`, `PUT`, `DELETE`) have
# been removed. The in-memory RAG pipeline is auto-loaded at startup from
# `settings.PDF_PATH`; there is no per-document metadata to manage from the
# admin panel any more.


# ---------------------------------------------------------------------------
# RAG management endpoints (read-only introspection over the in-memory store)
# ---------------------------------------------------------------------------
# The RAG knowledge base is auto-loaded at every FastAPI startup from the
# local PDF at `settings.PDF_PATH`. There is no per-PDF upload or per-doc
# chunking to manage from the admin panel; this endpoint only surfaces the
# current state for diagnostics.

@router.get("/rag/status")
async def rag_status(
    admin: dict = Depends(get_current_admin),
):
    """Aggregate stats about the in-memory RAG knowledge base."""
    state = rag_pipeline.status()
    return {
        "chunk_count": state.get("chunk_count", 0),
        "loaded": state.get("loaded", False),
        "source": state.get("source"),
        "document_id": state.get("document_id"),
        "loaded_at": state.get("loaded_at"),
        "last_error": state.get("last_error"),
        "embedding_model": settings.HF_EMBEDDING_MODEL_ID,
        "embedding_dim": settings.EMBEDDING_DIM,
    }


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
    if experience.logo_public_id:
        delete_asset(experience.logo_public_id, resource_type="image")
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


# Contact Info
@router.get("/contact-info", response_model=ContactInfoResponse)
async def get_admin_contact_info(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
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


@router.put("/contact-info", response_model=ContactInfoResponse)
async def update_contact_info(
    data: ContactInfoBase,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(select(ContactInfo))
    info = result.scalar_one_or_none()
    if info is None:
        info = ContactInfo(**data.model_dump())
        db.add(info)
    else:
        for key, value in data.model_dump().items():
            setattr(info, key, value)
    await db.commit()
    await db.refresh(info)
    return info


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


@router.post("/settings/smoke-test")
async def smoke_test(
    admin: dict = Depends(get_current_admin),
):
    """Run an end-to-end smoke test of the chatbot pipeline."""
    from services.chatbot import generate_response

    test_message = "Who is Muhammad Junayed?"
    used_hf_api = bool(settings.HF_API_TOKEN)
    model_used = settings.HF_MODEL_ID if used_hf_api else "fallback (no API)"

    start_time = time.time()
    try:
        result = await generate_response(test_message)
        elapsed_ms = round((time.time() - start_time) * 1000)
        return {
            "status": "success",
            "response": result.get("response", ""),
            "sources": result.get("sources", []),
            "used_hf_api": used_hf_api,
            "model": model_used,
            "response_time_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000)
        return {
            "status": "failed",
            "error": str(e),
            "used_hf_api": used_hf_api,
            "model": model_used,
            "response_time_ms": elapsed_ms,
        }


# Database viewer (PostgreSQL)
@router.get("/database")
async def database_viewer(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    result = await db.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = current_schema() "
            "AND tablename NOT LIKE 'pg_%' "
            "AND tablename NOT LIKE 'alembic_%'"
        )
    )
    tables = result.scalars().all()

    table_info = []
    for table_name in tables:
        # Identifier is not user input, so formatting into the query is safe.
        count_result = await db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        row_count = count_result.scalar()
        table_info.append({"name": table_name, "row_count": row_count})

    return {"tables": table_info}
