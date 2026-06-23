"""Portfolio retrieval backed by Neon pgvector.

Public API (kept stable for backwards compatibility):
- get_collection() / get_chroma_client() / initialize_collection()
- add_document(), add_documents_batch()
- delete_document(), clear_portfolio_collection()
- get_by_section_numbers(), get_by_entity_type()
- query(question, n_results)
- process_pdf(file_path, document_id)
- chunk_pdf_by_headings(text), chunk_text(text, ...)

Internally chunks live in a Postgres table `document_chunks` with a
`vector(384)` column. Embeddings are produced by the Hugging Face Inference
API (sentence-transformers/all-MiniLM-L6-v2) so no local model is loaded.
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import re
import threading
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader

from config import settings
from database import async_session

logger = logging.getLogger(__name__)


COLLECTION_NAME = "portfolio_knowledge"

# --- PDF section parsing (same hierarchy as the canonical portfolio PDF) ---
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
# Embedding helpers
# ---------------------------------------------------------------------------

async def _embed_texts(
    texts: List[str],
    timeout: float = 30.0,
) -> List[List[float]]:
    """Call HF feature-extraction to embed a batch of texts.

    Returns zero-vectors if HF_API_TOKEN is empty so the chat still works
    (it just falls back to metadata/keyword search).
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

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 503:
            await asyncio.sleep(3)
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error(
                "HF embedding failed (%s): %s",
                resp.status_code,
                resp.text[:300],
            )
            return [[0.0] * settings.EMBEDDING_DIM for _ in texts]

    data = resp.json()
    # HF returns either a single vector or list-of-vectors.
    if data and isinstance(data[0], list) and data and isinstance(data[0][0], list):
        return data
    return [data] if data else [[0.0] * settings.EMBEDDING_DIM for _ in texts]


def _format_embedding(vec: List[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def _embed_one(text: str) -> List[float]:
    return (await _embed_texts([text]))[0]


# ---------------------------------------------------------------------------
# Compatibility "collection" facade
# ---------------------------------------------------------------------------

class _PgCollection:
    """Thin async wrapper around the document_chunks table."""

    def __init__(self) -> None:
        self.name = COLLECTION_NAME

    # ---- write paths ----------------------------------------------------

    async def upsert_async(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ) -> None:
        if not (len(documents) == len(metadatas) == len(ids)):
            raise ValueError("documents, metadatas, and ids must match")

        # Compute embeddings for any new chunks only.
        texts_to_embed: List[str] = []
        embed_indices: List[int] = []
        for index, (text_value, chunk_id) in enumerate(zip(documents, ids)):
            existing = await self._has_embedding(chunk_id)
            if not existing:
                texts_to_embed.append(text_value)
                embed_indices.append(index)

        embeddings: Dict[int, List[float]] = {}
        if texts_to_embed:
            # Embed in chunks of 16 to respect HF payload limits.
            batch_size = 16
            for start in range(0, len(texts_to_embed), batch_size):
                end = start + batch_size
                batch_vecs = await _embed_texts(texts_to_embed[start:end])
                for offset, vec in enumerate(batch_vecs):
                    embeddings[embed_indices[start + offset]] = vec

        async with async_session() as session:
            for index, (doc_id, text_value, metadata) in enumerate(
                zip(ids, documents, metadatas)
            ):
                payload = {
                    "chunk_id": str(doc_id),
                    "document_id": str(
                        metadata.get("document_id") or _doc_id_from_chunk(doc_id)
                    ),
                    "chunk_index": int(metadata.get("chunk_index") or index),
                    "section_number": _as_str(metadata.get("section_number")),
                    "entity_type": _as_str(metadata.get("entity_type")),
                    "section": _as_str(metadata.get("section")),
                    "subsection": _as_str(metadata.get("subsection")),
                    "source": _as_str(metadata.get("source")),
                    "text": text_value,
                    "keywords": _as_str(metadata.get("keywords")),
                    "extra_metadata": json.dumps(_extra_metadata(metadata)),
                }
                if index in embeddings:
                    payload["embedding"] = embeddings[index]

                await session.execute(
                    text(
                        """
                        INSERT INTO document_chunks (
                            chunk_id, document_id, chunk_index,
                            section_number, entity_type, section, subsection,
                            source, text, keywords, extra_metadata, created_at,
                            embedding
                        ) VALUES (
                            :chunk_id, :document_id, :chunk_index,
                            :section_number, :entity_type, :section, :subsection,
                            :source, :text, :keywords, :extra_metadata, NOW(),
                            :embedding_vec
                        )
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            document_id = EXCLUDED.document_id,
                            chunk_index = EXCLUDED.chunk_index,
                            section_number = EXCLUDED.section_number,
                            entity_type = EXCLUDED.entity_type,
                            section = EXCLUDED.section,
                            subsection = EXCLUDED.subsection,
                            source = EXCLUDED.source,
                            text = EXCLUDED.text,
                            keywords = EXCLUDED.keywords,
                            extra_metadata = EXCLUDED.extra_metadata,
                            embedding = COALESCE(
                                EXCLUDED.embedding, document_chunks.embedding
                            )
                        """
                    ),
                    {
                        **payload,
                        "embedding_vec": _format_embedding(embeddings[index])
                        if index in embeddings
                        else None,
                    },
                )
            await session.commit()

    async def _has_embedding(self, chunk_id: str) -> bool:
        async with async_session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT embedding IS NOT NULL FROM document_chunks "
                        "WHERE chunk_id = :cid"
                    ),
                    {"cid": str(chunk_id)},
                )
            ).first()
            return bool(row and row[0])

    async def delete_async(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with async_session() as session:
            if ids:
                await session.execute(
                    text("DELETE FROM document_chunks WHERE chunk_id = ANY(:ids)"),
                    {"ids": [str(i) for i in ids]},
                )
            elif where:
                clauses = []
                params: Dict[str, Any] = {}
                for key, value in where.items():
                    col = _metadata_column(key)
                    if not col:
                        continue
                    placeholder = f"w_{key}"
                    clauses.append(f"{col} = :{placeholder}")
                    params[placeholder] = value
                if clauses:
                    await session.execute(
                        text("DELETE FROM document_chunks WHERE " + " AND ".join(clauses)),
                        params,
                    )
            await session.commit()

    async def get_async(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        clauses: List[str] = []
        params: Dict[str, Any] = {}
        if ids:
            clauses.append("chunk_id = ANY(:ids)")
            params["ids"] = [str(i) for i in ids]
        if where:
            for key, value in where.items():
                col = _metadata_column(key)
                if not col:
                    continue
                placeholder = f"w_{key}"
                clauses.append(f"{col} = :{placeholder}")
                params[placeholder] = value
        sql = (
            "SELECT chunk_id, text, document_id, chunk_index, section_number, "
            "entity_type, section, subsection, source, keywords, extra_metadata "
            "FROM document_chunks"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY section_number NULLS LAST, chunk_index"
        if offset:
            sql += f" OFFSET {int(offset)}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        async with async_session() as session:
            rows = (await session.execute(text(sql), params)).all()

        return {
            "ids": [r[0] for r in rows],
            "documents": [r[1] for r in rows],
            "metadatas": [
                _build_metadata(
                    document_id=r[2],
                    chunk_index=r[3],
                    section_number=r[4],
                    entity_type=r[5],
                    section=r[6],
                    subsection=r[7],
                    source=r[8],
                    keywords=r[9],
                    extra=r[10],
                )
                for r in rows
            ],
        }

    async def count_async(self) -> int:
        async with async_session() as session:
            row = (
                await session.execute(text("SELECT COUNT(*) FROM document_chunks"))
            ).first()
            return int(row[0]) if row else 0

    # ---- sync shims for backwards compatibility ------------------------
    # (chatbot.py uses asyncio.to_thread; admin router may still call sync)

    def upsert(self, *args: Any, **kwargs: Any) -> None:
        asyncio.run(self.upsert_async(*args, **kwargs))

    def add(self, *args: Any, **kwargs: Any) -> None:
        self.upsert(*args, **kwargs)

    def get(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return asyncio.run(self.get_async(*args, **kwargs))

    def delete(self, *args: Any, **kwargs: Any) -> None:
        asyncio.run(self.delete_async(*args, **kwargs))

    def count(self) -> int:
        return asyncio.run(self.count_async())


def _doc_id_from_chunk(chunk_id: str) -> str:
    return str(chunk_id).rsplit("_chunk_", 1)[0] if "_chunk_" in str(chunk_id) else str(chunk_id)


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _metadata_column(key: str) -> Optional[str]:
    mapping = {
        "document_id": "document_id",
        "section_number": "section_number",
        "entity_type": "entity_type",
        "section": "section",
        "subsection": "subsection",
        "source": "source",
    }
    return mapping.get(key)


def _extra_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    skip = {
        "document_id", "chunk_index", "section_number", "entity_type",
        "section", "subsection", "source", "keywords",
    }
    return {k: v for k, v in (metadata or {}).items() if k not in skip}


def _build_metadata(
    document_id: Any,
    chunk_index: Any,
    section_number: Any,
    entity_type: Any,
    section: Any,
    subsection: Any,
    source: Any,
    keywords: Any,
    extra: Any,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "document_id": document_id,
        "chunk_index": int(chunk_index or 0),
    }
    if section_number is not None:
        metadata["section_number"] = str(section_number)
    if entity_type is not None:
        metadata["entity_type"] = str(entity_type)
    if section is not None:
        metadata["section"] = str(section)
    if subsection is not None:
        metadata["subsection"] = str(subsection)
    if source is not None:
        metadata["source"] = str(source)
    if keywords:
        metadata["keywords"] = str(keywords)
    if extra:
        try:
            parsed = json.loads(extra) if isinstance(extra, str) else extra
            if isinstance(parsed, dict):
                metadata.update(parsed)
        except (TypeError, ValueError):
            pass
    return metadata


# ---------------------------------------------------------------------------
# Module-level singleton + sync facade
# ---------------------------------------------------------------------------

_collection: Optional[_PgCollection] = None
_global_lock = threading.RLock()


def initialize_collection() -> _PgCollection:
    global _collection
    with _global_lock:
        if _collection is None:
            _collection = _PgCollection()
    return _collection


def get_collection() -> _PgCollection:
    return initialize_collection()


def get_chroma_client() -> _PgCollection:
    return initialize_collection()


# ---------------------------------------------------------------------------
# Sync helpers used by chatbot.py and the admin router
# ---------------------------------------------------------------------------

def _run(coro: Any) -> Any:
    """Run an awaitable synchronously, reusing the running loop when possible."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    # If we're already inside an async context, fall back to running in a
    # background thread to avoid "loop is already running" errors.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


def add_document(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    doc_id: Optional[str] = None,
) -> str:
    if not text or not text.strip():
        raise ValueError("text must not be empty")
    final_id = doc_id or str(uuid.uuid4())
    final_metadata = dict(metadata or {})
    final_metadata.setdefault("keywords", extract_keywords(text))
    _run(
        get_collection().upsert_async(
            documents=[text.strip()],
            metadatas=[final_metadata],
            ids=[final_id],
        )
    )
    return final_id


def add_documents_batch(
    texts: List[str],
    metadatas: List[Dict[str, Any]],
    doc_ids: List[str],
    batch_size: int = 32,
) -> List[str]:
    if not (len(texts) == len(metadatas) == len(doc_ids)):
        raise ValueError("texts, metadatas, and doc_ids must match")
    clean: List[Tuple[str, Dict[str, Any], str]] = []
    for text_value, metadata, doc_id in zip(texts, metadatas, doc_ids):
        text_value = (text_value or "").strip()
        if not text_value:
            continue
        clean_metadata = dict(metadata or {})
        clean_metadata.setdefault("keywords", extract_keywords(text_value))
        clean.append((text_value, clean_metadata, str(doc_id)))
    if not clean:
        return []
    _run(
        get_collection().upsert_async(
            documents=[c[0] for c in clean],
            metadatas=[c[1] for c in clean],
            ids=[c[2] for c in clean],
        )
    )
    return [c[2] for c in clean]


def delete_document(doc_id: str) -> None:
    if not doc_id:
        return
    _run(get_collection().delete_async(ids=[doc_id]))


def clear_portfolio_collection() -> None:
    _run(
        get_collection().delete_async(where={"document_id": "__portfolio_clear__"})
        if False
        else _clear_all()
    )


async def _clear_all() -> None:
    async with async_session() as session:
        await session.execute(text("DELETE FROM document_chunks"))
        await session.commit()


def get_by_section_numbers(section_numbers: List[str]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for section in section_numbers:
        payload = get_collection().get(where={"section_number": str(section)})
        for record in _records_from_payload(payload):
            doc_id = str(record.get("doc_id") or "")
            if doc_id in seen:
                continue
            seen.add(doc_id)
            records.append(record)
    records.sort(key=lambda r: _section_sort_key(
        str((r.get("metadata") or {}).get("section_number", "999"))
    ))
    return records


def get_by_entity_type(entity_type: str) -> List[Dict[str, Any]]:
    payload = get_collection().get(where={"entity_type": str(entity_type)})
    return _records_from_payload(payload)


def query(question: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """Vector similarity search via pgvector; falls back to keyword search."""
    question = (question or "").strip()
    if not question or n_results <= 0:
        return []

    try:
        return _run(_vector_query(question, n_results))
    except Exception as exc:  # pragma: no cover
        logger.exception("pgvector query failed: %s", exc)
        return _keyword_fallback(question, n_results)


async def _vector_query(question: str, n_results: int) -> List[Dict[str, Any]]:
    question_vec = await _embed_one(question)
    vec_str = _format_embedding(question_vec)
    sql = text(
        """
        SELECT chunk_id, text, document_id, chunk_index, section_number,
               entity_type, section, subsection, source, keywords,
               extra_metadata,
               1 - (embedding <=> :qvec) AS similarity
        FROM document_chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> :qvec
        LIMIT :k
        """
    )
    async with async_session() as session:
        rows = (
            await session.execute(sql, {"qvec": vec_str, "k": int(n_results)})
        ).all()
    results: List[Dict[str, Any]] = []
    for r in rows:
        results.append(
            {
                "doc_id": r[0],
                "text": r[1],
                "metadata": _build_metadata(
                    document_id=r[2],
                    chunk_index=r[3],
                    section_number=r[4],
                    entity_type=r[5],
                    section=r[6],
                    subsection=r[7],
                    source=r[8],
                    keywords=r[9],
                    extra=r[10],
                ),
                "distance": float(1.0 - (r[11] or 0.0)),
            }
        )
    if not results:
        return _keyword_fallback(question, n_results)
    return results


def _keyword_fallback(question: str, n_results: int) -> List[Dict[str, Any]]:
    payload = get_collection().get(limit=200)
    docs = payload.get("documents") or []
    ids = payload.get("ids") or []
    metas = payload.get("metadatas") or []
    tokens = re.findall(r"\b\w+\b", question.lower())
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for index, document in enumerate(docs):
        text_lower = document.lower()
        score = sum(text_lower.count(token) for token in tokens if len(token) > 2)
        if score <= 0:
            continue
        metadata = metas[index] if index < len(metas) else {}
        scored.append(
            (
                score,
                {
                    "doc_id": ids[index],
                    "text": document,
                    "metadata": metadata,
                    "distance": 1.0 / (score + 1.0),
                },
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:n_results]]


# ---------------------------------------------------------------------------
# PDF chunking (unchanged algorithm)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Sort + record conversion helpers (same shape chatbot.py expects)
# ---------------------------------------------------------------------------

def _section_sort_key(section_number: str) -> Tuple[int, ...]:
    values: List[int] = []
    for part in str(section_number).split("."):
        try:
            values.append(int(part))
        except ValueError:
            values.append(999)
    return tuple(values)


def _records_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = payload.get("ids") or []
    documents = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []
    records: List[Dict[str, Any]] = []
    for index, doc_id in enumerate(ids):
        document = documents[index] if index < len(documents) else None
        metadata = metadatas[index] if index < len(metadatas) else {}
        if not document:
            continue
        records.append({
            "text": document,
            "metadata": metadata or {},
            "distance": 0.0,
            "doc_id": doc_id,
        })
    records.sort(
        key=lambda item: (
            _section_sort_key(
                str((item.get("metadata") or {}).get("section_number", "999"))
            ),
            int((item.get("metadata") or {}).get("chunk_index", 0)),
        )
    )
    return records


# ---------------------------------------------------------------------------
# PDF processing entry point
# ---------------------------------------------------------------------------

def _make_document_id(file_path: str) -> str:
    stem = Path(file_path).stem
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_").lower()
    return stem or "document"


# Public alias used by the admin router to compute the chunk-id prefix that
# `process_pdf` would generate for a given file. Keeping both names in sync
# guarantees that DELETE / reindex can locate every chunk for a document.
make_document_id = _make_document_id


def process_pdf(
    file_path: str,
    document_id: Optional[str] = None,
) -> List[str]:
    """Parse the PDF, embed the chunks, and persist them in Neon pgvector."""
    reader = PdfReader(file_path)
    full_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    ).strip()

    if not full_text:
        logger.warning("No extractable text found in %s", file_path)
        return []

    parsed_chunks = chunk_pdf_by_headings(full_text)
    final_document_id = document_id or _make_document_id(file_path)
    source_name = os.path.basename(file_path)

    # Drop any previous chunks for this document before re-inserting.
    _run(_delete_document_rows(final_document_id))

    texts: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    doc_ids: List[str] = []
    for index, chunk in enumerate(parsed_chunks):
        chunk_text_value = str(chunk.get("text") or "").strip()
        if not chunk_text_value:
            continue
        section_heading = str(chunk.get("heading") or "General")
        section_number = str(chunk.get("section_number") or "1")
        top_level = section_number.split(".")[0]
        parent_heading = PARENT_HEADINGS.get(top_level, "")
        heading_context = (
            f"{parent_heading} > {section_heading}"
            if parent_heading and parent_heading != section_heading
            else section_heading
        )
        indexed_text = f"{heading_context}\n{chunk_text_value}".strip()
        metadata: Dict[str, Any] = {
            "section": section_heading,
            "section_number": section_number,
            "document_id": final_document_id,
            "entity_type": str(chunk.get("entity_type") or "profile"),
            "chunk_index": index,
            "source": source_name,
        }
        if chunk.get("subsection"):
            metadata["subsection"] = str(chunk["subsection"])
        texts.append(indexed_text)
        metadatas.append(metadata)
        doc_ids.append(f"{final_document_id}_chunk_{index}")

    added_ids = add_documents_batch(texts, metadatas, doc_ids)
    gc.collect()
    logger.info(
        "Processed PDF '%s': created %d pgvector chunks",
        source_name,
        len(added_ids),
    )
    return added_ids


async def _delete_document_rows(document_id: str) -> None:
    async with async_session() as session:
        await session.execute(
            text("DELETE FROM document_chunks WHERE document_id = :did"),
            {"did": str(document_id)},
        )
        await session.commit()
