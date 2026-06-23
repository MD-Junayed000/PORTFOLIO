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
    """Build an internal proxy URL the browser can hit without auth."""
    # The frontend prepends the API base when the path starts with "/api/"
    # (it does for /uploads/... fallback paths), but in this case we want
    # the absolute URL because the proxy may live on a different origin
    # in the future. Keep it relative for now -- the React layer resolves
    # it via the same axios baseURL.
    return f"/api/files/raw?public_id={public_id}"


def _rewrite_raw_url_to_proxy(url: Optional[str]) -> Optional[str]:
    """Rewrite a Cloudinary ``raw`` secure_url to use our public proxy.

    We cannot just hand the original URL to the browser: assets uploaded
    under the default ``authenticated`` delivery return HTTP 401 to
    anonymous users (this is exactly the symptom on the public site:
    "This site can't be reached" / "HTTP ERROR 401").

    Instead, we strip the public_id out of the stored URL, ask Cloudinary
    to sign a short-lived download URL, and proxy it through this backend
    with the correct ``Content-Type``/``Content-Disposition`` so Chrome's
    PDF viewer can render the file inline.
    """
    if not url:
        return url
    public_id = extract_public_id_from_url(url, resource_type="raw")
    if not public_id:
        return url
    return _proxy_url(public_id)


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
        about.cv_file_path = _rewrite_raw_url_to_proxy(about.cv_file_path)
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
            cert.file_path = _rewrite_raw_url_to_proxy(cert.file_path)
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

    headers = {
        "Content-Disposition": (
            f'inline; filename="{filename}"' if is_pdf
            else f'attachment; filename="{filename}"'
        ),
        "Cache-Control": "private, max-age=60",
    }
    return StreamingResponse(_stream(), media_type=media_type, headers=headers)
