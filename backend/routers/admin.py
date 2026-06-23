import os
import time
import uuid
import base64
import logging
import tempfile
import traceback
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
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
    Document,
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
    DocumentBase,
    DocumentResponse,
    AdminSettings,
    ContactInfoBase,
    ContactInfoResponse,
)
from routers.auth import get_current_admin
from services.vector_store import (
    process_pdf,
    delete_document,
    make_document_id,
    get_collection,
    clear_portfolio_collection,
)
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


async def _delete_all_chunks_for_document(document) -> int:
    """Delete every vector chunk that belongs to a Document row.

    `process_pdf` builds chunk ids as ``{document_id}_chunk_{i}`` where
    `document_id` is the slug of the ORIGINAL filename, not the Cloudinary
    URL stored on `Document.filename`. We compute the same slug here and use
    the public `get_collection().delete_async(where={"document_id": ...})`
    path so we never miss orphans.
    """
    slug_source = document.original_name or document.filename or ""
    document_id = make_document_id(slug_source) if slug_source else None
    collection = get_collection()
    if document_id:
        await collection.delete_async(where={"document_id": document_id})
    # If slug could not be derived, fall back to the count range using the
    # recorded chunk_count. We add a small safety margin for reindex drift.
    if not document_id:
        upper = max(0, int(document.chunk_count or 0)) + 16
        for index in range(upper):
            chunk_id = f"unknown_doc_{document.id}_{index}"
            delete_document(chunk_id)
    return int(document.chunk_count or 0)


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
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
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

    # Persist URL + public_id to the AboutContent row, deleting the old
    # Cloudinary asset if one exists for this slot.
    result = await db.execute(select(AboutContent))
    about = result.scalar_one_or_none()
    if about is not None:
        if about.photo_public_id and about.photo_public_id != public_id:
            delete_asset(about.photo_public_id, resource_type="image")
        about.photo_url = secure_url
        about.photo_public_id = public_id
    await db.commit()

    return {"photo_url": secure_url, "public_id": public_id}


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


@router.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    topic_name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read file content with size limit. ``UploadFile.read()`` streams the
    # multipart body into a SpooledTemporaryFile that spills to disk on
    # Render's ephemeral volume. Surface read failures as a 400 instead of
    # letting the underlying OSError bubble up as a bare 500 (which the
    # browser would mis-report as a CORS failure).
    try:
        content = await file.read()
    except Exception:
        logger.exception(
            "Failed to read uploaded PDF body for filename=%r",
            file.filename,
        )
        raise HTTPException(
            status_code=400,
            detail="Could not read the uploaded file. It may be too large or corrupt.",
        )
    if len(content) > settings.MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_PDF_SIZE // (1024 * 1024)} MB",
        )

    # Upload the PDF to Cloudinary as a raw resource for permanent storage
    try:
        secure_url, public_id = upload_pdf(content, original_filename=file.filename)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Process PDF for vector store using a temporary local copy (transient only)
    import tempfile

    # Use a stable document_id derived from the original filename so the
    # admin can later delete / reindex chunks reliably. Without this, chunks
    # would be keyed on the random tempfile name and become unreachable.
    document_id = make_document_id(file.filename or "")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        doc_ids = process_pdf(tmp_path, document_id=document_id)
    except Exception:
        # Render logs are the only visibility we have here. Emit a full
        # traceback so the next deploy run shows the real cause of the
        # 500 the browser sees (HF embedding timeout, pgvector reject, etc.).
        logger.exception(
            "PDF processing failed for filename=%r document_id=%r size=%d",
            file.filename,
            document_id,
            len(content),
        )
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=500,
            detail="Failed to process PDF for the knowledge base. See server logs.",
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # Save document metadata to DB
    try:
        document = Document(
            filename=secure_url,
            topic=topic_name,
            original_name=file.filename,
            # `uploaded_at` maps to Postgres TIMESTAMP WITHOUT TIME ZONE; strip
            # tzinfo so asyncpg can bind it (see database.py ContactMessage note).
            uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            chunk_count=len(doc_ids),
        )
        # Persist Cloudinary public_id alongside the URL via a transient attribute
        setattr(document, "cloudinary_public_id", public_id)
        db.add(document)
        await db.commit()
        await db.refresh(document)
    except Exception:
        # Same reasoning as the process_pdf branch: surface the real error in
        # the Render log so the cause of any future 500 is obvious.
        logger.exception(
            "Document metadata insert failed for filename=%r document_id=%r",
            file.filename,
            document_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to save document metadata. See server logs.",
        )

    return {
        "filename": secure_url,
        "chunks_added": len(doc_ids),
        "doc_ids": doc_ids,
        "topic": topic_name,
        "document_id": document.id,
        "cloudinary_public_id": public_id,
    }


@router.post("/debug/process-pdf")
async def debug_process_pdf(
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """Diagnose process_pdf failures without going through Cloudinary.

    Accepts raw application/pdf bytes OR {"filename": "...", "pdf_base64": "..."}
    JSON. Writes the PDF to a temp file, runs process_pdf, and returns:

    * ``checkpoint`` — the last ``process_pdf[...]`` log line reached before the
      exception (or "ok" on success)
    * ``exception_type`` / ``exception_message`` — what process_pdf raised
    * ``traceback_tail`` — the last few lines of the traceback
    * ``parsed_chunks`` — number of chunks that chunk_pdf_by_headings produced
      (0 if the failure was earlier)

    Use this to iterate on the upload bug without redeploying or attaching
    Cloudinary.
    """
    # Accept either raw bytes (Content-Type: application/pdf) or JSON.
    filename = "debug.pdf"
    raw: bytes
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        payload = await request.json()
        filename = str(payload.get("filename") or filename)
        b64 = payload.get("pdf_base64")
        if not b64:
            raise HTTPException(
                status_code=400,
                detail="JSON body must include 'pdf_base64'",
            )
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"pdf_base64 is not valid base64: {exc}",
            )
    else:
        raw = await request.body()
        cd_header = request.headers.get("content-disposition") or ""
        if "filename=" in cd_header:
            try:
                filename = cd_header.split("filename=", 1)[1].strip('"; ')
            except Exception:
                pass

    if not raw:
        raise HTTPException(status_code=400, detail="Empty PDF body")

    # Capture process_pdf's logger output so we can report the last checkpoint.
    import io
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter("%(message)s"))

    process_pdf_logger = logging.getLogger("services.vector_store.process_pdf")
    process_pdf_logger.addHandler(log_handler)
    previous_level = process_pdf_logger.level
    process_pdf_logger.setLevel(logging.INFO)

    # Also capture the route logger used by admin.py (HTTPException(500) path).
    route_logger = logging.getLogger("routers.admin")
    route_logger.addHandler(log_handler)

    tmp_path: Optional[str] = None
    result: Dict[str, Any] = {
        "filename": filename,
        "size_bytes": len(raw),
        "checkpoint": "not_started",
        "exception_type": None,
        "exception_message": None,
        "traceback_tail": None,
        "parsed_chunks": None,
        "doc_ids": None,
    }
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        from services.vector_store import process_pdf as _process_pdf
        from services.vector_store import chunk_pdf_by_headings
        from pypdf import PdfReader

        # Manual checkpoints so we always know how far we got, even if the
        # logger handler misses something.
        checkpoints: List[str] = []
        try:
            reader = PdfReader(tmp_path)
            full_text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()
            checkpoints.append(
                f"pdf_parsed chars={len(full_text)} pages={len(reader.pages)}"
            )

            if not full_text:
                result.update({
                    "checkpoint": "pdf_parsed_no_text",
                    "exception_type": "EmptyPDF",
                    "exception_message": "No extractable text in PDF",
                })
                return result

            parsed = chunk_pdf_by_headings(full_text)
            checkpoints.append(f"chunked count={len(parsed)}")
            result["parsed_chunks"] = len(parsed)

            doc_ids = _process_pdf(tmp_path)
            result["checkpoint"] = "ok"
            result["doc_ids"] = doc_ids
            return result
        except Exception as exc:
            tb = traceback.format_exc().splitlines()
            result.update({
                "checkpoint": (
                    checkpoints[-1] if checkpoints else "before_pdf_parsed"
                ),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback_tail": tb[-12:],
            })
            # Also persist to the real logger so Render's normal log stream
            # shows the traceback for cross-referencing.
            logger.exception(
                "debug_process_pdf failed checkpoint=%s",
                result["checkpoint"],
            )
            return result
    finally:
        process_pdf_logger.removeHandler(log_handler)
        process_pdf_logger.setLevel(previous_level)
        route_logger.removeHandler(log_handler)
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


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

    # Delete ALL vector chunks for this document (the actual document_id used
    # by process_pdf is the slug of the original filename, not the Cloudinary
    # URL stored in `document.filename`). Falls back to a best-effort count
    # range if the slug can't be derived.
    try:
        await _delete_all_chunks_for_document(document)
    except Exception:
        pass  # Best effort deletion of vector chunks

    # Delete from Cloudinary (best effort, only if a public id is stored)
    public_id = getattr(document, "cloudinary_public_id", None)
    if public_id:
        delete_asset(public_id, resource_type="raw")

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


# ---------------------------------------------------------------------------
# RAG management endpoints (manual-only pipeline)
#
# - GET    /api/admin/rag/status      -> aggregate stats (chunk count, doc count)
# - DELETE /api/admin/rag/documents   -> wipe every chunk in document_chunks
#                                        (leaves the uploaded Document rows and
#                                        Cloudinary PDFs intact; use this for a
#                                        full reindex after model change).
# - POST   /api/admin/rag/reindex-all -> re-embed every Cloudinary-stored PDF
#                                        using the current embedding model.
# ---------------------------------------------------------------------------

@router.get("/rag/status")
async def rag_status(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    """Aggregate stats about the RAG knowledge base."""
    docs = (
        await db.execute(select(Document).order_by(Document.uploaded_at.desc()))
    ).scalars().all()
    total_chunks = sum(max(0, int(d.chunk_count or 0)) for d in docs)
    return {
        "document_count": len(docs),
        "total_chunks_recorded": total_chunks,
        "embedding_model": settings.HF_EMBEDDING_MODEL_ID,
        "embedding_dim": settings.EMBEDDING_DIM,
        "documents": [
            {
                "id": d.id,
                "topic": d.topic,
                "original_name": d.original_name,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
                "chunk_count": int(d.chunk_count or 0),
                "cloudinary_public_id": getattr(d, "cloudinary_public_id", None),
                "filename": d.filename,
            }
            for d in docs
        ],
    }


@router.delete("/rag/documents")
async def rag_clear_all(
    admin: dict = Depends(get_current_admin),
):
    """Wipe every vector chunk. Document rows and Cloudinary PDFs are kept."""
    clear_portfolio_collection()
    return {"detail": "All RAG chunks deleted. Upload PDFs again to repopulate."}


@router.post("/rag/reindex-all")
async def rag_reindex_all(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    """Re-download every persisted Cloudinary PDF and re-embed it.

    Use this after changing the embedding model or chunking settings. The
    Document row's `chunk_count` and `uploaded_at` are refreshed.
    """
    import httpx as _httpx  # local import keeps top-level imports tidy
    import tempfile as _tempfile

    docs = (
        await db.execute(select(Document).order_by(Document.uploaded_at.asc()))
    ).scalars().all()
    if not docs:
        return {"detail": "No documents to reindex.", "reindexed": 0}

    reindexed: List[Dict[str, Any]] = []
    async with _httpx.AsyncClient(timeout=120.0) as client:
        for document in docs:
            if not document.filename:
                continue
            try:
                resp = await client.get(document.filename)
                if resp.status_code != 200:
                    reindexed.append(
                        {
                            "document_id": document.id,
                            "status": "failed",
                            "error": f"Cloudinary returned {resp.status_code}",
                        }
                    )
                    continue
                content = resp.content
                with _tempfile.NamedTemporaryFile(
                    suffix=".pdf", delete=False
                ) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    doc_ids = process_pdf(
                        tmp_path,
                        document_id=make_document_id(
                            document.original_name or document.filename
                        ),
                    )
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

                document.chunk_count = len(doc_ids)
                # Same tz-naive UTC rule as the initial insert above.
                document.uploaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
                reindexed.append(
                    {
                        "document_id": document.id,
                        "status": "ok",
                        "chunks": len(doc_ids),
                    }
                )
            except Exception as exc:  # pragma: no cover
                logger.exception("Reindex failed for document %s", document.id)
                reindexed.append(
                    {
                        "document_id": document.id,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
    await db.commit()
    return {"detail": "Reindex complete.", "reindexed": reindexed}


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
