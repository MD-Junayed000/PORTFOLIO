from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

import httpx
import re

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
from config import settings
from services.cloudinary_service import (
    build_image_url,
    extract_public_id_from_url,
)

router = APIRouter(prefix="/api", tags=["public"])


def _proxy_url(public_id: str) -> str:
    """Build an internal proxy URL the browser can hit.

    The public_id passed here is the *exact* value stored on the DB row
    (e.g. ``portfolio/pdfs/pdf/<token>``) — the backend proxy appends
    ``.pdf`` and serves the asset through ``/image/upload/...``.
    """
    from urllib.parse import quote

    return f"/api/files/raw?public_id={quote(public_id, safe='/')}"


def _rewrite_to_proxy(url: Optional[str], public_id: Optional[str]) -> Optional[str]:
    """Swap a stored Cloudinary URL for our internal proxy URL.

    We prefer the DB-stored ``public_id`` over regex-extracting one from
    the URL — it is the *exact* value Cloudinary expects to fetch and
    avoids the path-segment ambiguity between ``folder`` and
    ``public_id``. For legacy rows whose ``public_id`` column is NULL,
    we fall back to parsing the secure_url.

    PDFs are now stored under ``resource_type="image"`` with
    ``format="pdf"``, so we ask the parser to extract from an ``image``
    URL. Legacy ``raw`` URLs are normalised to the new ``pdf/<token>``
    shape so the proxy can still serve them.
    """
    if public_id:
        return _proxy_url(_normalise_public_id(public_id))
    if url:
        fallback_id = extract_public_id_from_url(url, resource_type="image")
        if fallback_id:
            return _proxy_url(_normalise_public_id(fallback_id))
        # Last-ditch: the URL may still be a legacy ``raw`` upload.
        fallback_raw = extract_public_id_from_url(url, resource_type="raw")
        if fallback_raw:
            return _proxy_url(_normalise_public_id(fallback_raw))
    return url


def _normalise_public_id(public_id: str) -> str:
    """Coerce any stored public_id into the canonical ``pdf/<token>`` shape.

    Real-time uploads (after the image-format migration) produce
    ``portfolio/pdfs/pdf/<token>``. Legacy rows uploaded with the old
    ``raw`` flow have malformed ``portfolio/pdfs/portfolio/pdf/<token>``
    IDs because ``folder=portfolio/pdfs`` and ``public_id=portfolio/pdf/<token>``
    were both passed in. We strip the duplicated ``portfolio/pdf`` segment
    so the proxy resolves to a real Cloudinary asset.
    """
    if not public_id:
        return public_id
    # Collapse "portfolio/pdfs/portfolio/pdf/<token>" -> "portfolio/pdfs/pdf/<token>"
    return re.sub(
        r"^portfolio/pdfs/portfolio/pdf/",
        "portfolio/pdfs/pdf/",
        public_id,
    )


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
    """Stream a Cloudinary asset through this backend.

    PDFs uploaded after the image-format migration live under
    ``resource_type="image"`` with ``format="pdf"``, so their delivery
    URL is **public** — Cloudinary serves ``image/upload`` assets without
    an authenticated session. We proxy them through this backend (rather
    than pointing the browser at Cloudinary directly) so we can:

    1. Keep the Cloudinary ``cloud_name`` out of the public response.
    2. Set ``Content-Disposition`` / ``Content-Length`` consistently.
    3. Strip any upstream ``Content-Encoding`` (Cloudinary occasionally
       tags raw responses as gzip after httpx has already decoded them).
    4. Fall back to the legacy ``raw`` URL if the image variant returns
       404 — this lets already-uploaded CV / certificate PDFs keep
       working as long as the account's default delivery type is public.

    No signing is involved: we just build the URL from
    ``settings.CLOUDINARY_CLOUD_NAME`` + the public_id + ``.pdf``.
    """
    public_id = _normalise_public_id(public_id)
    image_url = build_image_url(public_id, ext="pdf")
    if not image_url:
        raise HTTPException(
            status_code=502,
            detail="Failed to build Cloudinary image URL",
        )

    # Build a parallel ``raw`` URL for the legacy-upload fallback. If the
    # asset was uploaded before the image-format migration it lives under
    # ``resource_type="raw"`` and we want to still serve it (so the user
    # doesn't see broken links while they're re-uploading their files).
    raw_url = image_url.replace("/image/upload/", "/raw/upload/", 1)

    filename = public_id.rsplit("/", 1)[-1] or "file"

    response_headers: dict[str, str] = {
        "Content-Disposition": f'inline; filename="{filename}"',
        "Cache-Control": "private, max-age=60",
        "Accept-Ranges": "bytes",
    }

    def _build_authed_url(url: str) -> str:
        """Append Cloudinary ``api_key`` / ``api_secret`` so a server-side
        fetch can read assets behind account-level access control.

        The browser hits this proxy anonymously; Cloudinary's account has
        strict access control on ``raw/upload`` (the live screenshots show
        401 for legacy PDFs). The backend, however, *is* allowed to access
        the asset — Cloudinary accepts the ``api_key`` / ``api_secret``
        query params on delivery URLs as a back-channel authentication
        mechanism for server-to-server fetches.
        """
        if not (settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET):
            return url
        sep = "&" if "?" in url else "?"
        return (
            f"{url}{sep}api_key={settings.CLOUDINARY_API_KEY}"
            f"&api_secret={settings.CLOUDINARY_API_SECRET}"
        )

    async def _stream():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Prefer the public image variant; if it 404s, the asset is a
            # legacy raw upload — try that path instead. The raw fallback
            # may be gated by account access control (401/403), in which
            # case we retry it with api_key/api_secret as a server-side
            # authenticated fetch — the backend is a trusted caller.
            last_status: Optional[int] = None
            for url in (image_url, raw_url):
                # First pass: anonymous fetch (matches the old behaviour).
                # Second pass (raw only): server-side authenticated fetch
                # for accounts that gate raw/upload behind an access rule.
                candidate_urls: list[tuple[str, dict]] = [(url, {})]
                if url is raw_url and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
                    candidate_urls.append((_build_authed_url(url), {}))

                for fetch_url, _extra_headers in candidate_urls:
                    async with client.stream("GET", fetch_url) as upstream:
                        last_status = upstream.status_code
                        if upstream.status_code == 200:
                            content_length = upstream.headers.get("Content-Length")
                            if content_length:
                                response_headers["Content-Length"] = content_length
                            async for chunk in upstream.aiter_bytes(chunk_size=64 * 1024):
                                yield chunk
                            return
                        # Drain & close the failed attempt before trying
                        # the next URL — httpx requires the response to
                        # be fully consumed (or the stream closed) inside
                        # the ``with``.
                        await upstream.aclose()
            # Neither variant (anonymous *or* authenticated) had the file.
            # Surface a clear, actionable error so the browser doesn't
            # just spin forever.
            if last_status in (401, 403):
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Cloudinary rejected the PDF (HTTP "
                        f"{last_status}). The Cloudinary account has "
                        "strict access control enabled and the configured "
                        "api_key/api_secret could not authenticate the "
                        "raw fallback either. Open "
                        "https://console.cloudinary.com/console/dbbgpd3h3/"
                        "settings/access-control and either disable the "
                        "rule, or whitelist the 'portfolio/pdfs' folder "
                        "for public delivery, then re-upload the PDF "
                        "from the admin panel."
                    ),
                )
            raise HTTPException(
                status_code=404,
                detail=(
                    "PDF not found on Cloudinary. Re-upload it from the "
                    "admin panel so it lands under the public image delivery."
                ),
            )

    return StreamingResponse(
        _stream(),
        media_type="application/pdf",
        headers=response_headers,
    )
