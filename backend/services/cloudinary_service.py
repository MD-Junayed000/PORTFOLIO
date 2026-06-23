"""Cloudinary upload, retrieval, and deletion helpers.

Centralizes all Cloudinary interactions so that the rest of the codebase
does not need to know about SDK details. Uses the credentials supplied via
the CLOUDINARY_* environment variables on Render.
"""
from __future__ import annotations

import logging
import re
import secrets
from typing import Optional, Tuple

import cloudinary
import cloudinary.uploader
import cloudinary.utils
from cloudinary.exceptions import Error as CloudinaryError

from config import settings

logger = logging.getLogger(__name__)


def configure_cloudinary() -> None:
    """Initialize the global Cloudinary client from settings.

    Called once at application startup and on demand. Safe to call multiple
    times: cloudinary.config() is idempotent.
    """
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def _generate_public_id(prefix: str) -> str:
    """Generate a short, URL-safe public_id scoped to a folder.

    NOTE: The returned value MUST be just the leaf segment (e.g.
    ``pdf/<token>``). The caller is responsible for prepending any
    ``folder=`` argument, because Cloudinary's SDK concatenates
    ``folder + public_id`` verbatim. If we returned ``portfolio/pdf/<token>``
    here *and* passed ``folder="portfolio/pdfs"``, the resulting
    public_id would be the malformed ``portfolio/pdfs/portfolio/pdf/<token>``
    that the live account currently has.
    """
    token = secrets.token_hex(8)
    return f"{prefix}/{token}"


def upload_image(
    file_bytes: bytes,
    *,
    folder: str = "portfolio/images",
    original_filename: Optional[str] = None,
) -> Tuple[str, str]:
    """Upload an image to Cloudinary and return (secure_url, public_id).

    The upload uses resource_type="image". The public_id is generated server
    side so it is unique even if the same filename is uploaded twice.
    """
    configure_cloudinary()
    public_id = _generate_public_id("img")
    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            public_id=public_id,
            folder=folder,
            resource_type="image",
            overwrite=True,
            unique_filename=False,
            use_filename=False,
        )
    except CloudinaryError as exc:
        logger.exception("Cloudinary image upload failed")
        raise RuntimeError(f"Cloudinary upload failed: {exc}") from exc

    secure_url = result.get("secure_url")
    returned_public_id = result.get("public_id", public_id)
    if not secure_url:
        raise RuntimeError("Cloudinary did not return a secure_url")
    return secure_url, returned_public_id


def upload_pdf(
    file_bytes: bytes,
    *,
    folder: str = "portfolio/pdfs",
    original_filename: Optional[str] = None,
) -> Tuple[str, str]:
    """Upload a PDF as a publicly readable Cloudinary ``image`` resource.

    Returns (secure_url, public_id).

    Why ``resource_type="image"`` and not ``raw``? Three reasons:

    1. **Delivery is public by default.** ``image/upload`` URLs are served
       anonymously; ``raw/upload`` is gated behind the account's default
       delivery type (authenticated in this account) and an additional
       access-control rule, which is why the live screenshots show
       "Customer is marked as untrusted" / 401 responses.
    2. **No signed-URL gymnastics.** The browser can fetch
       ``https://res.cloudinary.com/<cloud>/image/upload/<public_id>.pdf``
       directly without our backend proxying or signing anything.
    3. **Doubled-path bug goes away.** ``raw`` doesn't auto-add the file
       extension, so we had to embed ``.pdf`` in ``public_id``. With
       ``image`` + ``format="pdf"``, Cloudinary handles the extension
       server-side and we can use a clean ``public_id`` without an
       extension.

    The leaf ``public_id`` is just ``pdf/<token>`` (no extension) so
    Cloudinary doesn't double-prefix us when combined with the
    ``portfolio/pdfs`` folder.
    """
    configure_cloudinary()
    public_id = _generate_public_id("pdf")
    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            public_id=public_id,
            folder=folder,
            resource_type="image",
            format="pdf",  # tells Cloudinary to serve the asset as application/pdf
            overwrite=True,
            unique_filename=False,
            use_filename=False,
        )
    except CloudinaryError as exc:
        logger.exception("Cloudinary PDF upload failed")
        raise RuntimeError(f"Cloudinary upload failed: {exc}") from exc

    secure_url = result.get("secure_url")
    returned_public_id = result.get("public_id", public_id)
    if not secure_url:
        raise RuntimeError("Cloudinary did not return a secure_url")
    return secure_url, returned_public_id


def delete_asset(public_id: str, resource_type: str = "image") -> bool:
    """Delete a Cloudinary asset by public_id.

    Returns True if the asset was found and deleted, False if it was already
    gone or could not be deleted. Errors are logged but never raised so that
    deletion failures do not block the main DB transaction.
    """
    if not public_id:
        return False
    configure_cloudinary()
    try:
        result = cloudinary.uploader.destroy(
            public_id,
            resource_type=resource_type,
            invalidate=True,
        )
        return result.get("result") in ("ok", "not_found")
    except CloudinaryError as exc:
        logger.warning("Cloudinary delete failed for %s: %s", public_id, exc)
        return False
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unexpected error deleting Cloudinary asset %s: %s", public_id, exc)
        return False


def extract_public_id_from_url(
    url: Optional[str], resource_type: str = "image"
) -> Optional[str]:
    """Recover the Cloudinary ``public_id`` from a stored ``secure_url``.

    We strip the version segment (``v1234567890/``) and the file extension
    so the result is exactly what the Cloudinary SDK needs to fetch the
    asset again.

    For PDFs uploaded as ``resource_type="image"`` with ``format="pdf"``,
    the secure_url looks like::

        https://res.cloudinary.com/<cloud>/image/upload/v123/portfolio/pdfs/pdf/<token>.pdf
        -> portfolio/pdfs/pdf/<token>

    For legacy ``raw`` PDFs::

        https://res.cloudinary.com/<cloud>/raw/upload/v123/portfolio/pdfs/<token>.pdf
        -> portfolio/pdfs/<token>
    """
    if not url:
        return None
    match = re.match(
        r"^https?://res\.cloudinary\.com/[^/]+/"
        r"(?P<rtype>image|video|raw|file)/"
        r"(?P<dtype>upload|authenticated|private)/"
        r"(?:v\d+/)?"
        r"(?P<pid>.+?)(?:\.[A-Za-z0-9]{1,5})?$",
        url.strip(),
    )
    if not match:
        return None
    if match.group("rtype") != resource_type:
        return None
    return match.group("pid")


def build_image_url(public_id: str, *, ext: str = "pdf") -> Optional[str]:
    """Build the public, unsigned Cloudinary ``image/upload`` URL.

    PDFs in this app are uploaded with ``resource_type="image"`` and
    ``format="pdf"``. That delivery type is **public by default**, so we
    don't need to sign the URL — the browser can fetch it directly (and
    our backend proxy fetches it server-side as a passthrough).

    The returned URL is of the form::

        https://res.cloudinary.com/<cloud>/image/upload/<public_id>.<ext>
    """
    if not public_id:
        return None
    configure_cloudinary()
    cloud_name = settings.CLOUDINARY_CLOUD_NAME
    if not cloud_name:
        logger.warning("CLOUDINARY_CLOUD_NAME is not set; cannot build image URL")
        return None
    # Strip any extension the caller may have passed in — we re-apply
    # the canonical ``.<ext>`` suffix so the URL always serves as the
    # right Content-Type.
    pid = public_id.split(".", 1)[0]
    return f"https://res.cloudinary.com/{cloud_name}/image/upload/{pid}.{ext}"


def build_signed_image_url(public_id: str, *, ext: str = "pdf") -> Optional[str]:
    """Build a Cloudinary ``image/upload`` delivery URL with a signature.

    Used as the **fallback** when the public, unsigned URL is blocked by
    account-level access control. The SDK computes an HMAC over the
    public_id + transformation params using ``CLOUDINARY_API_SECRET`` and
    adds a ``signature=`` query param + ``timestamp=``; Cloudinary then
    accepts the fetch from this trusted server-side caller.

    Notes
    -----
    - We do **not** use ``type="authenticated"`` here. That delivery
      variant returns a different URL shape
      (``/image/authenticated/...``) which is gated behind its own
      access-control rule, and the live account doesn't enable it for
      ``portfolio/pdfs``. Signing the standard ``/image/upload/`` URL
      with a short-lived signature works for the same access rule that
      blocks the unsigned URL.
    - We keep ``format=ext`` so Cloudinary serves the bytes as
      ``application/pdf`` regardless of how the asset was uploaded.
    """
    if not public_id:
        return None
    if not (settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET):
        logger.warning(
            "CLOUDINARY_API_KEY/SECRET are not set; cannot sign delivery URL"
        )
        return None
    configure_cloudinary()
    pid = public_id.split(".", 1)[0]
    try:
        url, _options = cloudinary.utils.cloudinary_url(
            pid,
            resource_type="image",
            type="upload",
            format=ext,
            sign_url=True,
            secure=True,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("cloudinary_url(sign_url=True) failed for %s: %s", pid, exc)
        return None
    return url
