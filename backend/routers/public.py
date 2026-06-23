from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

import httpx

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
from services.cloudinary_service import (
    extract_public_id_from_url,
    sign_raw_download_url,
)

router = APIRouter(prefix="/api", tags=["public"])


def _proxy_url(public_id: str) -> str:
    """Build an internal proxy URL the browser can hit without auth.

    The public_id passed here is the *exact* value stored on the DB row
    (e.g. ``portfolio/pdf/<token>.pdf``) — Cloudinary's
    ``private_download_url`` understands that format directly without us
    having to re-parse the secure_url.
    """
    from urllib.parse import quote

    return f"/api/files/raw?public_id={quote(public_id, safe='/')}"


def _rewrite_to_proxy(url: Optional[str], public_id: Optional[str]) -> Optional[str]:
    """Swap a stored Cloudinary URL for our internal proxy URL.

    We prefer the DB-stored ``public_id`` over regex-extracting one from
    the URL — it is the *exact* value Cloudinary expects to sign and
    avoids the path-segment ambiguity between ``folder`` and
    ``public_id``. For legacy rows whose ``public_id`` column is NULL,
    we fall back to parsing the secure_url.
    """
    if public_id:
        return _proxy_url(public_id)
    if url:
        fallback_id = extract_public_id_from_url(url, resource_type="raw")
        if fallback_id:
            return _proxy_url(fallback_id)
    return url


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
    # Rewrite the CV URL to the proxy so the browser gets a real PDF
    # (Cloudinary's "raw" delivery is authenticated by default).
    if about.cv_file_path:
        about.cv_file_path = _rewrite_to_proxy(about.cv_file_path, about.cv_public_id)
    return about


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
    # Rewrite each certificate's file_path so the browser can actually open
    # the PDF. The raw Cloudinary URL returns 401 to anonymous visitors.
    for cert in certs:
        if cert.file_path:
            cert.file_path = _rewrite_to_proxy(cert.file_path, cert.file_public_id)
    return certs


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


@router.get("/files/raw")
async def proxy_raw_file(public_id: str = Query(..., min_length=1)):
    """Stream a Cloudinary ``raw`` asset through this backend.

    The original Cloudinary URL is not directly accessible to anonymous
    browsers (it returns HTTP 401) because the account's default delivery
    type is ``authenticated``. We solve that by signing a short-lived
    download URL with ``cloudinary.utils.private_download_url`` and
    streaming the bytes back to the client.

    The response is marked ``inline`` with the correct ``Content-Type``
    so the browser's built-in PDF viewer can render the certificate /
    resume without a download dialog.

    We also strip the upstream ``Content-Encoding`` header (Cloudinary
    raw resources are sometimes served with ``Content-Encoding: gzip``
    while httpx has already decoded the body) and pass through the
    upstream ``Content-Length`` so Chrome's PDF viewer knows the file
    size up-front and can render the progress bar.
    """
    signed_url = sign_raw_download_url(public_id, ttl_seconds=300)
    if not signed_url:
        raise HTTPException(
            status_code=502,
            detail="Failed to sign Cloudinary download URL",
        )

    # Sniff the content type from the public_id's extension so we can set
    # the right Content-Type header. PDFs default to application/pdf.
    extension = public_id.rsplit(".", 1)[-1].lower() if "." in public_id else "pdf"
    media_type_map = {
        "pdf": "application/pdf",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    media_type = media_type_map.get(extension, "application/octet-stream")
    is_pdf = media_type == "application/pdf"

    filename = public_id.rsplit("/", 1)[-1] or "file"

    async def _stream():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("GET", signed_url) as upstream:
                upstream.raise_for_status()
                async for chunk in upstream.aiter_bytes(chunk_size=64 * 1024):
                    yield chunk

    response_headers = {
        "Content-Disposition": (
            f'inline; filename="{filename}"' if is_pdf
            else f'attachment; filename="{filename}"'
        ),
        "Cache-Control": "private, max-age=60",
        "Accept-Ranges": "bytes",
    }
    return StreamingResponse(
        _stream(),
        media_type=media_type,
        headers=response_headers,
    )
