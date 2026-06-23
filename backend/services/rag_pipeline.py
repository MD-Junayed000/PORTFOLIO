"""In-memory RAG pipeline for the portfolio chatbot.

This module is the single source of truth for portfolio retrieval. It replaces
the previous pgvector-backed store in :mod:`services.vector_store` and is
loaded automatically at FastAPI startup from the local PDF in
``backend/pdf_rag/Muhammad_Junayed_RAG_Knowledge_Base.pdf``.

Public surface (kept stable so :mod:`services.chatbot` and the admin router
do not need to change):

- :func:`initialize_from_pdf` -- parse, chunk, embed, populate the store
- :func:`get_by_section_numbers` -- return every chunk for the given section numbers
- :func:`get_by_entity_type`    -- return every chunk for the given entity type
- :func:`query`                  -- cosine-similarity search (falls back to keyword)
- :func:`status`                 -- introspection for the admin UI
- :func:`clear`                  -- reset the in-memory store (test/utility)

Chunks are stored in a process-local list of records. The embedding dimension
is fixed at ``settings.EMBEDDING_DIM`` (384 for ``all-MiniLM-L6-v2``) and
embeddings are produced by the Hugging Face Inference API (no local model is
loaded, so the memory footprint stays low on Render).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - PyPDF2 fallback for legacy installs
    from PyPDF2 import PdfReader

from config import settings
from services.vector_store import (
    PARENT_HEADINGS,
    _clean_pdf_text,
    _embed_texts,
    _hard_split_text,
    _make_document_id,
    _parse_sections,
    extract_keywords,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Store representation
# ---------------------------------------------------------------------------


@dataclass
class _Chunk:
    """A single in-memory chunk with its embedding and metadata."""

    doc_id: str
    text: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _StoreState:
    """All mutable state for the in-memory RAG store."""

    chunks: List[_Chunk] = field(default_factory=list)
    source: Optional[str] = None
    document_id: Optional[str] = None
    loaded_at: Optional[float] = None
    last_error: Optional[str] = None


_state = _StoreState()
_lock = threading.RLock()
_init_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# PDF parsing + chunking (mirrors the previous pgvector pipeline)
# ---------------------------------------------------------------------------


def _parse_pdf_text(pdf_path: str) -> str:
    """Extract and clean text from the portfolio PDF."""
    reader = PdfReader(pdf_path)
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    return _clean_pdf_text(raw)


def _build_chunks(
    full_text: str,
    document_id: str,
    source_name: str,
) -> List[Dict[str, Any]]:
    """Chunk a PDF's text using the heading-aware splitter.

    The output mirrors the previous pgvector schema (text + metadata) so the
    downstream chatbot code can stay unchanged.
    """
    parsed = _parse_sections(full_text)
    chunks: List[Dict[str, Any]] = []
    for section in parsed:
        body = str(section.get("text") or "").strip()
        if not body:
            continue
        if len(body) <= 2500:
            pieces: List[Tuple[int, str]] = [(0, body)]
        else:
            pieces = list(
                enumerate(_hard_split_text(body, 2500, 240))
            )
        for split_index, part in pieces:
            chunks.append(
                {
                    "text": part,
                    "metadata": {
                        "section": str(section.get("heading") or "General"),
                        "section_number": str(
                            section.get("section_number") or "1"
                        ),
                        "document_id": document_id,
                        "entity_type": str(
                            section.get("entity_type") or "profile"
                        ),
                        "chunk_index": len(chunks),
                        "source": source_name,
                        "keywords": extract_keywords(part),
                        "subsection": section.get("subsection"),
                        "section_chunk_index": split_index,
                    },
                }
            )
    return chunks


def _embed_chunk_text(
    text: str,
    section: str,
    parent_heading: str,
) -> str:
    """Prefix a chunk with its heading context before embedding.

    This matches the previous pipeline so the embedding space stays aligned
    with what the chatbot expects to see at retrieval time.
    """
    if parent_heading and parent_heading != section:
        heading = f"{parent_heading} > {section}"
    else:
        heading = section
    return f"{heading}\n{text}".strip()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


async def initialize_from_pdf(
    pdf_path: Optional[str] = None,
    *,
    document_id: Optional[str] = None,
) -> int:
    """Parse the portfolio PDF, embed its chunks, and populate the store.

    The call is idempotent: re-running it replaces the previous store. It
    is safe to call from FastAPI's startup event on every deploy.
    """
    target_path = pdf_path or getattr(
        settings, "PDF_PATH", None
    ) or str(
        Path(__file__).resolve().parent.parent
        / "pdf_rag"
        / "Muhammad_Junayed_RAG_Knowledge_Base.pdf"
    )

    target = Path(target_path)
    if not target.is_file():
        message = f"Portfolio PDF not found at {target_path}"
        logger.warning(message)
        with _lock:
            _state.chunks = []
            _state.source = None
            _state.document_id = None
            _state.loaded_at = None
            _state.last_error = message
        return 0

    async with _init_lock:
        try:
            full_text = await asyncio.to_thread(_parse_pdf_text, str(target))
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to parse portfolio PDF: %s", exc)
            with _lock:
                _state.chunks = []
                _state.source = str(target)
                _state.document_id = None
                _state.loaded_at = None
                _state.last_error = str(exc)
            return 0

        if not full_text.strip():
            message = f"No extractable text in {target_path}"
            logger.warning(message)
            with _lock:
                _state.chunks = []
                _state.source = str(target)
                _state.document_id = None
                _state.loaded_at = None
                _state.last_error = message
            return 0

        final_document_id = document_id or _make_document_id(str(target))
        source_name = target.name
        parsed_chunks = _build_chunks(
            full_text, final_document_id, source_name
        )

        # Build (text, metadata) lists to embed. We prefix the heading
        # context so the embedding line up with retrieval expectations.
        texts_to_embed: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        for chunk in parsed_chunks:
            metadata = dict(chunk["metadata"])
            top_level = str(metadata.get("section_number", "1")).split(".")[0]
            parent_heading = PARENT_HEADINGS.get(top_level, "")
            texts_to_embed.append(
                _embed_chunk_text(
                    chunk["text"],
                    str(metadata.get("section") or "General"),
                    parent_heading,
                )
            )
            metadatas.append(metadata)

        embeddings = await _embed_texts(texts_to_embed) if texts_to_embed else []
        if len(embeddings) != len(texts_to_embed):
            logger.error(
                "Embedding count mismatch (expected %d, got %d); aborting RAG load.",
                len(texts_to_embed),
                len(embeddings),
            )
            with _lock:
                _state.chunks = []
                _state.source = str(target)
                _state.document_id = None
                _state.loaded_at = None
                _state.last_error = "Embedding call returned wrong count"
            return 0

        # Build the final in-memory store.
        new_chunks: List[_Chunk] = []
        for index, (embedding, metadata) in enumerate(
            zip(embeddings, metadatas)
        ):
            new_chunks.append(
                _Chunk(
                    doc_id=f"{final_document_id}_chunk_{index}",
                    text=parsed_chunks[index]["text"],
                    embedding=list(embedding),
                    metadata=metadata,
                )
            )

        with _lock:
            _state.chunks = new_chunks
            _state.source = source_name
            _state.document_id = final_document_id
            _state.loaded_at = os.path.getmtime(str(target))
            _state.last_error = None

        logger.info(
            "RAG pipeline loaded %d chunks from %s (document_id=%s)",
            len(new_chunks),
            source_name,
            final_document_id,
        )
        return len(new_chunks)


def clear() -> None:
    """Reset the in-memory store. Mainly used by tests."""
    with _lock:
        _state.chunks = []
        _state.source = None
        _state.document_id = None
        _state.loaded_at = None
        _state.last_error = None


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def _section_sort_key(section_number: str) -> Tuple[int, ...]:
    values: List[int] = []
    for part in str(section_number).split("."):
        try:
            values.append(int(part))
        except ValueError:
            values.append(999)
    return tuple(values)


def _chunk_to_record(chunk: _Chunk, distance: float = 0.0) -> Dict[str, Any]:
    return {
        "text": chunk.text,
        "metadata": dict(chunk.metadata),
        "distance": float(distance),
        "doc_id": chunk.doc_id,
    }


def _is_zero_vector(vec: List[float]) -> bool:
    return not any(abs(float(x)) > 1e-9 for x in vec)


def _cosine_similarity(
    a: List[float], b: List[float]
) -> float:
    """Pure-Python cosine similarity (vectors are dense 384-d)."""
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for index in range(size):
        av = float(a[index])
        bv = float(b[index])
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


async def _embed_question(question: str) -> List[float]:
    """Embed a single question, falling back to a zero vector on failure."""
    cleaned = (question or "").strip()
    if not cleaned:
        return [0.0] * settings.EMBEDDING_DIM
    try:
        vectors = await _embed_texts([cleaned])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Question embedding failed: %s", exc)
        return [0.0] * settings.EMBEDDING_DIM
    if not vectors:
        return [0.0] * settings.EMBEDDING_DIM
    return list(vectors[0])


def _keyword_scores(
    question: str, chunks: List[_Chunk]
) -> List[Tuple[int, _Chunk]]:
    """Score chunks by literal token overlap; used as a fallback."""
    tokens = [
        token
        for token in re.findall(r"\b\w+\b", question.lower())
        if len(token) > 2
    ]
    if not tokens:
        return []
    scored: List[Tuple[int, _Chunk]] = []
    for chunk in chunks:
        text_lower = chunk.text.lower()
        score = sum(text_lower.count(token) for token in tokens)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Public retrieval API (matches the shape used by services.chatbot)
# ---------------------------------------------------------------------------


def get_by_section_numbers(
    section_numbers: List[str],
) -> List[Dict[str, Any]]:
    with _lock:
        chunks = list(_state.chunks)

    if not section_numbers or not chunks:
        return []

    wanted = {str(value) for value in section_numbers}
    selected: List[_Chunk] = []
    for chunk in chunks:
        if str(chunk.metadata.get("section_number")) in wanted:
            selected.append(chunk)

    selected.sort(
        key=lambda chunk: (
            _section_sort_key(
                str(chunk.metadata.get("section_number", "999"))
            ),
            int(chunk.metadata.get("chunk_index", 0)),
        )
    )
    return [_chunk_to_record(chunk) for chunk in selected]


def get_by_entity_type(entity_type: str) -> List[Dict[str, Any]]:
    with _lock:
        chunks = list(_state.chunks)
    target = str(entity_type)
    selected = [
        chunk
        for chunk in chunks
        if str(chunk.metadata.get("entity_type")) == target
    ]
    selected.sort(
        key=lambda chunk: (
            _section_sort_key(
                str(chunk.metadata.get("section_number", "999"))
            ),
            int(chunk.metadata.get("chunk_index", 0)),
        )
    )
    return [_chunk_to_record(chunk) for chunk in selected]


async def _async_query(
    question: str, n_results: int
) -> List[Dict[str, Any]]:
    question = (question or "").strip()
    if not question or n_results <= 0:
        return []

    with _lock:
        chunks = list(_state.chunks)

    if not chunks:
        return []

    question_vec = await _embed_question(question)
    if not _is_zero_vector(question_vec):
        scored: List[Tuple[float, _Chunk]] = []
        for chunk in chunks:
            if _is_zero_vector(chunk.embedding):
                continue
            similarity = _cosine_similarity(question_vec, chunk.embedding)
            scored.append((similarity, chunk))
        if scored:
            scored.sort(key=lambda item: item[0], reverse=True)
            top = scored[:n_results]
            return [
                _chunk_to_record(
                    chunk,
                    distance=max(0.0, min(1.0, 1.0 - similarity)),
                )
                for similarity, chunk in top
            ]
        # All chunks have zero embeddings (e.g. HF offline) -- fall through
        # to keyword search so the chatbot still has something to ground on.
    else:
        logger.debug(
            "Falling back to keyword search (no question embedding available)."
        )

    keyword_scored = _keyword_scores(question, chunks)
    if not keyword_scored:
        return []
    top = keyword_scored[:n_results]
    return [
        _chunk_to_record(
            chunk,
            distance=1.0 / (score + 1.0),
        )
        for score, chunk in top
    ]


def query(question: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """Synchronous wrapper used by services.chatbot."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(_async_query(question, n_results))

    # Already inside an async context -- schedule a worker thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(
            asyncio.run, _async_query(question, n_results)
        )
        return future.result()


def status() -> Dict[str, Any]:
    """Return a small status dict (used by the admin UI / smoke test)."""
    with _lock:
        return {
            "loaded": bool(_state.chunks),
            "chunk_count": len(_state.chunks),
            "source": _state.source,
            "document_id": _state.document_id,
            "loaded_at": _state.loaded_at,
            "last_error": _state.last_error,
        }
