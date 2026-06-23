"""Compatibility shim around :mod:`services.rag_pipeline`.

Historically, portfolio retrieval was backed by Neon pgvector. That storage
path has been retired: chunks are now parsed, embedded, and stored in
process memory by ``services.rag_pipeline`` at every FastAPI startup from
the bundled PDF at ``backend/pdf_rag/Muhammad_Junayed_RAG_Knowledge_Base.pdf``.

This module preserves the public surface that ``services.chatbot`` and the
admin router import (``get_by_section_numbers``, ``get_by_entity_type``,
``query as vector_query``, ``process_pdf``, ``delete_document``,
``make_document_id``, ``get_collection``, ``get_chroma_client``,
``clear_portfolio_collection``, ``initialize_collection``,
``add_documents_batch``, ``add_document``, ``chunk_pdf_by_headings``,
``chunk_text``, ``extract_keywords``) and delegates each of them to the
in-memory pipeline.

The HF embedding helpers (``_embed_texts``, ``_embed_one``,
``_format_embedding``) and the section/chunk parsers (``chunk_pdf_by_headings``,
``chunk_text``, ``_parse_sections``, ``_hard_split_text``, ``_clean_pdf_text``,
``_make_document_id``, ``extract_keywords``, ``_section_sort_key``,
``_records_from_payload``) still live here because they are reused by
``services.rag_pipeline``.

``_run`` is also kept: ``rag_pipeline`` schedules the synchronous ``query()``
helper using it (the embedding call is async).
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

try:
    from pypdf import PdfReader  # noqa: F401  (re-exported for legacy callers)
except ImportError:  # pragma: no cover
    from PyPDF2 import PdfReader  # type: ignore  # noqa: F401

from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants shared with the rag pipeline
# ---------------------------------------------------------------------------

COLLECTION_NAME = "portfolio_knowledge"

SECTION_ENTITY_MAP = {
    "1": "profile", "2": "profile", "3": "education", "4": "research",
    "5": "experience", "6": "research", "7": "skill", "8": "education",
    "9": "research", "10": "project", "11": "extracurricular",
    "12": "award", "13": "language",
}

PARENT_HEADINGS = {
    "1": "Professional Profile",
    "2": "Personal and Professional Information",
    "3": "Education",
    "4": "Undergraduate Thesis",
    "5": "Work Experience",
    "6": "Research Interests",
    "7": "Technical Skills",
    "8": "Relevant Coursework",
    "9": "Research and Publications",
    "10": "Selected Projects",
    "11": "Extracurricular Activities and Leadership",
    "12": "Awards and Achievements",
    "13": "Languages",
}


# ---------------------------------------------------------------------------
# Section parsing (heading-aware chunking of the canonical portfolio PDF)
# ---------------------------------------------------------------------------

def _get_entity_type(section_number: str) -> str:
    return SECTION_ENTITY_MAP.get(str(section_number).split(".")[0], "profile")


def _clean_pdf_text(text: str) -> str:
    text = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u00ad", "")
        .replace("\ufffe", "-")
    )
    text = re.sub(
        r"(?im)^\s*Page\s+\d+(?:\s+of\s+\d+)?\s*$",
        "",
        text,
    )
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_sections(text: str) -> List[Dict[str, Any]]:
    heading_pattern = re.compile(r"^(\d+(?:\.\d+)*)(?:\.)?\s+(.+?)\s*$")
    lines = text.splitlines()
    accepted: List[Dict[str, Any]] = []
    current_top_level = 0
    for line_index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        match = heading_pattern.match(stripped)
        if not match:
            continue
        section_number = match.group(1)
        heading_title = match.group(2).strip()
        parts = section_number.split(".")
        top_level = int(parts[0])
        is_subsection = len(parts) > 1
        if current_top_level == 0:
            valid = not is_subsection and top_level == 1
        elif is_subsection:
            valid = top_level == current_top_level
        else:
            valid = top_level == current_top_level + 1
        if not valid:
            continue
        accepted.append({
            "line_index": line_index,
            "body_start_line": line_index + 1,
            "heading": heading_title,
            "section_number": section_number,
            "subsection": heading_title if is_subsection else None,
            "entity_type": _get_entity_type(section_number),
        })
        if not is_subsection:
            current_top_level = top_level
    if not accepted:
        return [{
            "heading": "General",
            "section_number": "1",
            "subsection": None,
            "text": text.strip(),
            "entity_type": "profile",
        }]
    sections: List[Dict[str, Any]] = []
    for index, heading in enumerate(accepted):
        end_line = (
            accepted[index + 1]["line_index"]
            if index + 1 < len(accepted)
            else len(lines)
        )
        section_text = "\n".join(
            lines[heading["body_start_line"]:end_line]
        ).strip()
        if not section_text:
            continue
        sections.append({
            "heading": heading["heading"],
            "section_number": heading["section_number"],
            "subsection": heading["subsection"],
            "text": section_text,
            "entity_type": heading["entity_type"],
        })
    return sections


def _hard_split_text(
    text: str,
    max_chars: int,
    overlap_chars: int,
) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            overlap = current[-overlap_chars:].lstrip()
            current = f"{overlap} {sentence}".strip()
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text.strip()]


def chunk_pdf_by_headings(text: str) -> List[Dict[str, Any]]:
    sections = _parse_sections(_clean_pdf_text(text))
    chunks: List[Dict[str, Any]] = []
    for section in sections:
        body = str(section.get("text") or "").strip()
        if not body:
            continue
        if len(body) <= 2500:
            chunks.append(section)
        else:
            for index, part in enumerate(_hard_split_text(body, 2500, 240)):
                item = dict(section)
                item["text"] = part
                item["section_chunk_index"] = index
                chunks.append(item)
    return chunks


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 150,
) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")
    return _hard_split_text(text, chunk_size, overlap)


def extract_keywords(text: str) -> str:
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "and",
        "or", "if", "about", "this", "that", "it", "its", "he", "his",
        "what", "which", "who",
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    frequencies = Counter(
        word for word in words if word not in stop_words
    )
    return ",".join(word for word, _ in frequencies.most_common(10))


def _make_document_id(file_path: str) -> str:
    stem = Path(file_path).stem
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_").lower()
    return stem or "document"


# Public alias kept for symmetry with the admin router's ``make_document_id``
# import; the underlying helper is module-private so we re-export under the
# public name too.
make_document_id = _make_document_id


# ---------------------------------------------------------------------------
# Embedding helpers (used by the in-memory pipeline and tests)
# ---------------------------------------------------------------------------

async def _embed_texts(
    texts: List[str],
    timeout: float = 90.0,
) -> List[List[float]]:
    """Call HF feature-extraction to embed a batch of texts.

    Returns zero-vectors if HF_API_TOKEN is empty OR every retry fails, so
    the chat still works (it just falls back to metadata/keyword search).
    The fallback is always a properly-shaped ``EMBEDDING_DIM`` vector so the
    in-memory store stays well-formed.
    """
    if not texts:
        return []
    if not settings.HF_API_TOKEN:
        logger.warning("HF_API_TOKEN missing; using zero embeddings.")
        return [[0.0] * settings.EMBEDDING_DIM for _ in texts]

    url = (
        "https://api-inference.huggingface.co/pipeline/feature-extraction/"
        + settings.HF_EMBEDDING_MODEL_ID
    )
    headers = {"Authorization": f"Bearer {settings.HF_API_TOKEN}"}
    payload = {"inputs": texts, "options": {"wait_for_model": True}}

    # Retries handle HF cold-starts (503), transient gateway errors (502/504),
    # deprecation responses (410) and timeouts. We bound total wait so the
    # endpoint never hangs the request thread.
    last_status: Optional[int] = None
    last_body: str = ""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            last_status = None
            last_body = f"timeout: {exc!r}"
            logger.warning(
                "HF embedding timeout on attempt %d/3; retrying...", attempt + 1
            )
            await asyncio.sleep(2 + attempt * 2)
            continue
        except httpx.HTTPError as exc:
            last_status = None
            last_body = f"http-error: {exc!r}"
            logger.warning(
                "HF embedding network error on attempt %d/3: %s",
                attempt + 1,
                exc,
            )
            await asyncio.sleep(2 + attempt * 2)
            continue

        if resp.status_code == 200:
            data = resp.json()
            # HF returns either a single vector or list-of-vectors.
            if (
                data
                and isinstance(data, list)
                and data
                and isinstance(data[0], list)
                and data[0]
                and isinstance(data[0][0], list)
            ):
                return data
            if data and isinstance(data, list) and isinstance(data[0], (int, float)):
                return [data]
            # Unexpected shape — treat as failure and retry once.
            last_status = resp.status_code
            last_body = (resp.text or "")[:200]
            logger.warning(
                "HF embedding returned unexpected payload shape on attempt %d/3",
                attempt + 1,
            )
            await asyncio.sleep(2)
            continue

        last_status = resp.status_code
        last_body = (resp.text or "")[:200]
        # 401/403: token invalid — don't waste retries.
        if resp.status_code in (401, 403):
            break
        # 410/404: model gone — don't waste retries.
        if resp.status_code in (404, 410):
            break
        # 503 (model loading) / 429 (rate limit) / 5xx: retry with backoff.
        await asyncio.sleep(2 + attempt * 2)

    logger.error(
        "HF embedding failed after retries (status=%s, body=%s); "
        "falling back to zero embeddings for %d chunk(s).",
        last_status,
        last_body,
        len(texts),
    )
    return [[0.0] * settings.EMBEDDING_DIM for _ in texts]


def _format_embedding(vec: List[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def _embed_one(text: str) -> List[float]:
    return (await _embed_texts([text]))[0]


def _run(coro: Any) -> Any:
    """Run an awaitable synchronously, reusing the running loop when possible.

    Used by ``services.rag_pipeline`` to invoke async helpers (HF embedding)
    from the synchronous ``query`` shim below.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


# ---------------------------------------------------------------------------
# Compatibility shims that delegate to the in-memory pipeline
# ---------------------------------------------------------------------------
#
# ``services.chatbot`` and the admin router import the following names from
# this module. Each one is a thin wrapper around ``services.rag_pipeline``,
# which is loaded at FastAPI startup.

def _get_pipeline():
    """Late import to avoid a circular dependency with this module."""
    from services import rag_pipeline
    return rag_pipeline


def initialize_collection() -> Any:
    """Backwards-compatible hook. The in-memory store is initialized at startup."""
    return _get_pipeline()


def get_collection() -> Any:
    return _get_pipeline()


def get_chroma_client() -> Any:
    return _get_pipeline()


def add_document(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    doc_id: Optional[str] = None,
) -> str:
    """No-op shim kept for backwards compatibility.

    RAG ingestion is now automatic; the PDF is reloaded from disk by the
    FastAPI lifespan on startup and on every ``process_pdf`` call.
    """
    if not text or not text.strip():
        raise ValueError("text must not be empty")
    return doc_id or str(uuid.uuid4())


def add_documents_batch(
    texts: List[str],
    metadatas: List[Dict[str, Any]],
    doc_ids: List[str],
    batch_size: int = 32,
) -> List[str]:
    """No-op shim kept for backwards compatibility."""
    if not (len(texts) == len(metadatas) == len(doc_ids)):
        raise ValueError("texts, metadatas, and doc_ids must match")
    return [str(doc_id) for doc_id in doc_ids]


def delete_document(doc_id: str) -> None:
    """No-op shim kept for backwards compatibility."""
    if not doc_id:
        return


def clear_portfolio_collection() -> None:
    """Reset the in-memory store (was used to wipe pgvector rows)."""
    _get_pipeline().clear()


def get_by_section_numbers(
    section_numbers: List[str],
) -> List[Dict[str, Any]]:
    return _get_pipeline().get_by_section_numbers(section_numbers)


def get_by_entity_type(entity_type: str) -> List[Dict[str, Any]]:
    return _get_pipeline().get_by_entity_type(entity_type)


def query(question: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """Vector similarity search; falls back to keyword search."""
    return _get_pipeline().query(question, n_results=n_results)


# ---------------------------------------------------------------------------
# PDF processing entry point (reloads the in-memory pipeline)
# ---------------------------------------------------------------------------

def process_pdf(
    file_path: str,
    document_id: Optional[str] = None,
) -> List[str]:
    """Re-ingest a PDF by delegating to the in-memory pipeline.

    This used to write to pgvector. Now it just refreshes the in-memory
    store. The ``document_id`` argument is accepted for backwards
    compatibility but the value used internally is always derived from the
    PDF filename so the startup load is deterministic.
    """
    pipeline = _get_pipeline()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        chunk_count = asyncio.run(
            pipeline.initialize_from_pdf(
                file_path, document_id=document_id
            )
        )
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            chunk_count = ex.submit(
                asyncio.run,
                pipeline.initialize_from_pdf(
                    file_path, document_id=document_id
                ),
            ).result()

    if not chunk_count:
        return []
    return [
        f"{_make_document_id(file_path)}_chunk_{index}"
        for index in range(chunk_count)
    ]
