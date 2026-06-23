"""Cloudinary upload, retrieval, and deletion helpers.

Centralizes all Cloudinary interactions so that the rest of the codebase
does not need to know about SDK details. Uses the credentials supplied via
the CLOUDINARY_* environment variables on Render.
"""
from __future__ import annotations

import logging
import secrets
from typing import Optional, Tuple

import cloudinary
import cloudinary.uploader
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
    """Generate a short, URL-safe public_id scoped to a folder."""
    token = secrets.token_hex(8)
    return f"portfolio/{prefix}/{token}"


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
    """Upload a PDF as a Cloudinary 'raw' resource.

    Returns (secure_url, public_id). For ``resource_type="raw"`` Cloudinary
    serves the file under the URL path as-is and serves ``Content-Type`` based
    on the extension embedded in ``public_id``. If the extension is missing
    the browser receives a generic ``application/octet-stream`` blob and the
    file is saved without a ``.pdf`` suffix — so we always append the original
    extension (defaulting to ``.pdf``) to the generated token.
    """
    configure_cloudinary()
    extension = "pdf"
    if original_filename and "." in original_filename:
        candidate = original_filename.rsplit(".", 1)[-1].strip().lower()
        if candidate.isalnum() and len(candidate) <= 5:
            extension = candidate
    public_id = f"{_generate_public_id('pdf')}.{extension}"
    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            public_id=public_id,
            folder=folder,
            resource_type="raw",
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
