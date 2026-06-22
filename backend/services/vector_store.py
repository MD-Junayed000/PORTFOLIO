"""Lightweight portfolio retrieval store for Render Free.

This module is a drop-in replacement for ``services/vector_store.py``.
It intentionally avoids ChromaDB, ONNX Runtime, sentence-transformers,
Kubernetes, OpenTelemetry, and local embedding-model downloads.

The canonical portfolio PDF has a small, structured knowledge base. Named
projects/publications are retrieved by exact section metadata, while general
questions use an in-memory BM25 index.
"""

from __future__ import annotations

import gc
import logging
import math
import os
import re
import threading
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

COLLECTION_NAME = "portfolio_knowledge"

SECTION_ENTITY_MAP = {
    "1": "profile",
    "2": "profile",
    "3": "education",
    "4": "research",
    "5": "experience",
    "6": "research",
    "7": "skill",
    "8": "education",
    "9": "research",
    "10": "project",
    "11": "extracurricular",
    "12": "award",
    "13": "language",
}

QUERY_SECTION_BOOST = {
    "project": {"10"},
    "skill": {"7"},
    "experience": {"5"},
    "education": {"3", "8"},
    "research": {"4", "6", "9"},
    "award": {"12"},
    "language": {"13"},
    "profile": {"1", "2"},
    "extracurricular": {"11"},
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


class SimpleBM25:
    """Small in-memory BM25 index with update and delete support."""

    def __init__(self) -> None:
        self.docs: List[List[str]] = []
        self.doc_ids: List[str] = []
        self.avg_dl: float = 0.0
        self.doc_count: int = 0
        self.idf: Dict[str, float] = {}
        self._documents_by_id: Dict[str, List[str]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(
            r"\b[a-zA-Z0-9][a-zA-Z0-9_+#.-]*\b",
            text.lower(),
        )

    def _rebuild(self) -> None:
        self.doc_ids = list(self._documents_by_id.keys())
        self.docs = [self._documents_by_id[doc_id] for doc_id in self.doc_ids]
        self.doc_count = len(self.docs)
        self.avg_dl = (
            sum(len(doc) for doc in self.docs) / self.doc_count
            if self.doc_count
            else 0.0
        )

        document_frequency: Counter[str] = Counter()
        for doc in self.docs:
            document_frequency.update(set(doc))

        self.idf = {
            term: math.log(
                (self.doc_count - frequency + 0.5)
                / (frequency + 0.5)
                + 1.0
            )
            for term, frequency in document_frequency.items()
        }

    def add_documents(
        self,
        documents: List[str],
        doc_ids: Optional[List[str]] = None,
    ) -> None:
        if doc_ids is not None and len(documents) != len(doc_ids):
            raise ValueError("documents and doc_ids must have equal lengths")

        with self._lock:
            for index, document in enumerate(documents):
                doc_id = (
                    doc_ids[index]
                    if doc_ids is not None
                    else str(uuid.uuid4())
                )
                self._documents_by_id[doc_id] = self._tokenize(document)
            self._rebuild()

    def delete_documents(self, doc_ids: Iterable[str]) -> None:
        with self._lock:
            for doc_id in doc_ids:
                self._documents_by_id.pop(str(doc_id), None)
            self._rebuild()

    def clear(self) -> None:
        with self._lock:
            self._documents_by_id.clear()
            self._rebuild()

    def search(
        self,
        query_text: str,
        top_k: int = 5,
    ) -> List[Tuple[int, float]]:
        if top_k <= 0:
            return []

        query_tokens = self._tokenize(query_text)
        if not query_tokens:
            return []

        with self._lock:
            scores: List[Tuple[int, float]] = []
            k1, b = 1.5, 0.75

            for index, doc in enumerate(self.docs):
                doc_length = len(doc)
                term_frequency = Counter(doc)
                score = 0.0

                for term in query_tokens:
                    if term not in self.idf:
                        continue

                    frequency = term_frequency.get(term, 0)
                    if frequency == 0:
                        continue

                    numerator = frequency * (k1 + 1.0)
                    denominator = frequency + k1 * (
                        1.0
                        - b
                        + b * doc_length / max(self.avg_dl, 1.0)
                    )
                    score += self.idf[term] * numerator / denominator

                if score > 0:
                    scores.append((index, score))

            scores.sort(key=lambda item: item[1], reverse=True)
            return scores[:top_k]


class LightweightCollection:
    """Minimal Chroma-like adapter used by existing startup/admin code."""

    def __init__(self) -> None:
        self.name = COLLECTION_NAME
        self._records: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _matches_where(
        metadata: Dict[str, Any],
        where: Optional[Dict[str, Any]],
    ) -> bool:
        if not where:
            return True
        return all(metadata.get(key) == value for key, value in where.items())

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def upsert(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
        **_: Any,
    ) -> None:
        if not (len(documents) == len(metadatas) == len(ids)):
            raise ValueError("documents, metadatas, and ids must match")

        with self._lock:
            for document, metadata, doc_id in zip(
                documents,
                metadatas,
                ids,
            ):
                self._records[str(doc_id)] = {
                    "document": str(document),
                    "metadata": dict(metadata or {}),
                }

    def add(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
        **kwargs: Any,
    ) -> None:
        with self._lock:
            duplicates = [doc_id for doc_id in ids if doc_id in self._records]
            if duplicates:
                raise ValueError(f"Duplicate IDs: {duplicates}")
        self.upsert(documents, metadatas, ids, **kwargs)

    def get(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        del include

        with self._lock:
            if ids is not None:
                requested = [str(doc_id) for doc_id in ids]
                items = [
                    (doc_id, self._records[doc_id])
                    for doc_id in requested
                    if doc_id in self._records
                ]
            else:
                items = list(self._records.items())

            items = [
                (doc_id, record)
                for doc_id, record in items
                if self._matches_where(record["metadata"], where)
            ]

            if offset:
                items = items[offset:]
            if limit is not None:
                items = items[:limit]

            return {
                "ids": [doc_id for doc_id, _ in items],
                "documents": [
                    record["document"] for _, record in items
                ],
                "metadatas": [
                    dict(record["metadata"]) for _, record in items
                ],
            }

    def delete(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            if ids is not None:
                for doc_id in ids:
                    self._records.pop(str(doc_id), None)
                return

            if where:
                delete_ids = [
                    doc_id
                    for doc_id, record in self._records.items()
                    if self._matches_where(record["metadata"], where)
                ]
                for doc_id in delete_ids:
                    self._records.pop(doc_id, None)


_collection: Optional[LightweightCollection] = None
_bm25_index: Optional[SimpleBM25] = None
_global_lock = threading.RLock()


def get_bm25_index() -> SimpleBM25:
    global _bm25_index
    with _global_lock:
        if _bm25_index is None:
            _bm25_index = SimpleBM25()
        return _bm25_index


def initialize_collection() -> LightweightCollection:
    global _collection
    with _global_lock:
        if _collection is None:
            _collection = LightweightCollection()
    return _collection


def get_collection() -> LightweightCollection:
    return initialize_collection()


def get_chroma_client() -> LightweightCollection:
    """Backward-compatible name; no Chroma client is created."""
    return initialize_collection()


def rebuild_bm25_from_collection(batch_size: int = 200) -> None:
    collection = get_collection()
    bm25 = get_bm25_index()
    bm25.clear()

    total = collection.count()
    for offset in range(0, total, batch_size):
        payload = collection.get(
            limit=batch_size,
            offset=offset,
            include=["documents"],
        )
        documents = payload.get("documents") or []
        ids = payload.get("ids") or []
        if documents:
            bm25.add_documents(documents, ids)


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
    return ",".join(
        word for word, _ in frequencies.most_common(10)
    )


def _get_entity_type(section_number: str) -> str:
    return SECTION_ENTITY_MAP.get(
        str(section_number).split(".")[0],
        "profile",
    )


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
    text = re.sub(
        r"(?im)^\s*Muhammad\s+Junayed\s*[-\u2013\u2014]\s*"
        r"Complete\s+Portfolio[^\n]*$",
        "",
        text,
    )
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_sections(text: str) -> List[Dict[str, Any]]:
    """Parse the canonical portfolio hierarchy without list false positives."""
    heading_pattern = re.compile(
        r"^(\d+(?:\.\d+)*)(?:\.)?\s+(.+?)\s*$"
    )
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

        continuation_lines = 0
        if line_index + 2 < len(lines):
            next_line = lines[line_index + 1].strip()
            following_line = lines[line_index + 2].strip()
            following_is_body = (
                following_line.startswith(("•", "-", "*"))
                or following_line in {
                    "Problem", "Approach", "Dataset", "Technologies",
                    "Features", "Architecture", "Outcome", "Hardware",
                    "Models", "Responsibilities",
                }
            )
            next_is_metadata_or_bullet = bool(
                next_line.startswith(("•", "◦", "▪", "-", "*"))
                or re.match(
                    r"^[A-Za-z][^:\n]{0,55}\s*:\s*.+$",
                    next_line,
                )
            )
            if (
                len(heading_title) >= 55
                and next_line
                and len(next_line) <= 100
                and not heading_pattern.match(next_line)
                and not next_is_metadata_or_bullet
                and following_is_body
            ):
                heading_title = f"{heading_title} {next_line}"
                continuation_lines = 1

        accepted.append({
            "line_index": line_index,
            "body_start_line": line_index + 1 + continuation_lines,
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
        elif len(sentence) > max_chars:
            words = sentence.split()
            block = current
            for word in words:
                candidate = f"{block} {word}".strip()
                if block and len(candidate) > max_chars:
                    chunks.append(block)
                    overlap = block[-overlap_chars:].lstrip()
                    block = f"{overlap} {word}".strip()
                else:
                    block = candidate
            current = block
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks or [text.strip()]


def _split_section_into_chunks(
    section: Dict[str, Any],
    max_chars: int = 2500,
    overlap_chars: int = 240,
) -> List[Dict[str, Any]]:
    text = str(section.get("text") or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [dict(section)]

    parts = _hard_split_text(text, max_chars, overlap_chars)
    chunks: List[Dict[str, Any]] = []
    for index, part in enumerate(parts):
        item = dict(section)
        item["text"] = part
        item["section_chunk_index"] = index
        chunks.append(item)
    return chunks


def chunk_pdf_by_headings(text: str) -> List[Dict[str, Any]]:
    sections = _parse_sections(_clean_pdf_text(text))
    chunks: List[Dict[str, Any]] = []
    for section in sections:
        chunks.extend(_split_section_into_chunks(section))
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


def _normalize_metadata(
    metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[str(key)] = value
        else:
            normalized[str(key)] = str(value)
    return normalized


def add_document(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    doc_id: Optional[str] = None,
) -> str:
    if not text or not text.strip():
        raise ValueError("text must not be empty")

    final_id = doc_id or str(uuid.uuid4())
    final_metadata = _normalize_metadata(metadata)
    final_metadata.setdefault("keywords", extract_keywords(text))

    get_collection().upsert(
        documents=[text.strip()],
        metadatas=[final_metadata],
        ids=[final_id],
    )
    get_bm25_index().add_documents([text.strip()], [final_id])
    return final_id


def add_documents_batch(
    texts: List[str],
    metadatas: List[Dict[str, Any]],
    doc_ids: List[str],
    batch_size: int = 32,
) -> List[str]:
    if not (len(texts) == len(metadatas) == len(doc_ids)):
        raise ValueError("texts, metadatas, and doc_ids must match")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    clean_texts: List[str] = []
    clean_metadatas: List[Dict[str, Any]] = []
    clean_ids: List[str] = []

    for text, metadata, doc_id in zip(texts, metadatas, doc_ids):
        clean_text = str(text).strip()
        if not clean_text:
            continue

        clean_metadata = _normalize_metadata(metadata)
        clean_metadata.setdefault(
            "keywords",
            extract_keywords(clean_text),
        )

        clean_texts.append(clean_text)
        clean_metadatas.append(clean_metadata)
        clean_ids.append(str(doc_id))

    collection = get_collection()
    for start in range(0, len(clean_texts), batch_size):
        end = start + batch_size
        collection.upsert(
            documents=clean_texts[start:end],
            metadatas=clean_metadatas[start:end],
            ids=clean_ids[start:end],
        )

    get_bm25_index().add_documents(clean_texts, clean_ids)
    return clean_ids


def _section_sort_key(section_number: str) -> Tuple[int, ...]:
    values: List[int] = []
    for part in str(section_number).split("."):
        try:
            values.append(int(part))
        except ValueError:
            values.append(999)
    return tuple(values)


def _records_from_payload(
    payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
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
                str(
                    (item.get("metadata") or {}).get(
                        "section_number",
                        "999",
                    )
                )
            ),
            int(
                (item.get("metadata") or {}).get(
                    "chunk_index",
                    0,
                )
            ),
        )
    )
    return records


def get_by_section_numbers(
    section_numbers: List[str],
) -> List[Dict[str, Any]]:
    collection = get_collection()
    records: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for section_number in section_numbers:
        payload = collection.get(
            where={"section_number": str(section_number)},
            include=["documents", "metadatas"],
        )
        for record in _records_from_payload(payload):
            doc_id = str(record.get("doc_id") or "")
            if doc_id in seen:
                continue
            seen.add(doc_id)
            records.append(record)

    records.sort(
        key=lambda item: _section_sort_key(
            str(
                (item.get("metadata") or {}).get(
                    "section_number",
                    "999",
                )
            )
        )
    )
    return records


def get_by_entity_type(
    entity_type: str,
) -> List[Dict[str, Any]]:
    payload = get_collection().get(
        where={"entity_type": str(entity_type)},
        include=["documents", "metadatas"],
    )
    return _records_from_payload(payload)


def _section_boost(
    question: str,
    metadata: Dict[str, Any],
) -> float:
    question_lower = question.lower()
    section_number = str(metadata.get("section_number") or "")
    top_section = section_number.split(".")[0] if section_number else ""

    categories = {
        "project": (
            "project", "built", "developed", "created", "application",
        ),
        "skill": (
            "skill", "technology", "stack", "framework", "tool",
        ),
        "experience": (
            "experience", "work", "job", "intern", "company", "role",
        ),
        "education": (
            "education", "university", "degree", "course", "gpa", "cgpa",
        ),
        "research": (
            "research", "paper", "publication", "thesis", "conference",
        ),
        "award": (
            "award", "achievement", "honor", "prize", "winner",
        ),
        "language": (
            "language", "speak", "bangla", "english",
        ),
        "profile": (
            "who", "about", "summary", "overview", "background",
        ),
    }

    for category, keywords in categories.items():
        if any(keyword in question_lower for keyword in keywords):
            return (
                1.0
                if top_section in QUERY_SECTION_BOOST.get(category, set())
                else 0.0
            )
    return 0.0


def query(
    question: str,
    n_results: int = 5,
) -> List[Dict[str, Any]]:
    """BM25 + metadata retrieval with no local embedding model."""
    question = (question or "").strip()
    if not question or n_results <= 0:
        return []

    bm25 = get_bm25_index()
    if bm25.doc_count == 0:
        rebuild_bm25_from_collection()

    search_count = max(n_results * 4, n_results)
    matches = bm25.search(question, top_k=search_count)
    if not matches:
        return []

    max_score = max(score for _, score in matches)
    ranked: List[Tuple[float, Dict[str, Any]]] = []

    for index, raw_score in matches:
        if not (0 <= index < len(bm25.doc_ids)):
            continue

        doc_id = bm25.doc_ids[index]
        payload = get_collection().get(
            ids=[doc_id],
            include=["documents", "metadatas"],
        )
        records = _records_from_payload(payload)
        if not records:
            continue

        record = records[0]
        normalized_bm25 = raw_score / max(max_score, 1e-9)
        section_score = _section_boost(
            question,
            record.get("metadata") or {},
        )
        combined = 0.9 * normalized_bm25 + 0.1 * section_score

        record["bm25_score"] = normalized_bm25
        record["section_score"] = section_score
        record["combined_score"] = combined
        ranked.append((combined, record))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [record for _, record in ranked[:n_results]]


def delete_document(doc_id: str) -> None:
    if not doc_id:
        return
    get_collection().delete(ids=[doc_id])
    get_bm25_index().delete_documents([doc_id])


def clear_portfolio_collection() -> None:
    collection = get_collection()
    payload = collection.get(include=[])
    ids = payload.get("ids") or []
    if ids:
        collection.delete(ids=ids)
    get_bm25_index().clear()


def _make_document_id(file_path: str) -> str:
    stem = Path(file_path).stem
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)
    stem = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        stem,
    ).strip("_").lower()
    return stem or "document"


def process_pdf(
    file_path: str,
    document_id: Optional[str] = None,
) -> List[str]:
    reader = PdfReader(file_path)
    full_text = "\n".join(
        page.extract_text() or ""
        for page in reader.pages
    ).strip()

    if not full_text:
        logger.warning("No extractable text found in %s", file_path)
        return []

    parsed_chunks = chunk_pdf_by_headings(full_text)
    has_real_headings = any(
        chunk.get("heading") != "General"
        for chunk in parsed_chunks
    )

    if not has_real_headings:
        parsed_chunks = [
            {
                "text": item,
                "heading": "General",
                "section_number": "1",
                "subsection": None,
                "entity_type": "profile",
            }
            for item in chunk_text(full_text)
        ]

    final_document_id = (
        document_id or _make_document_id(file_path)
    )
    source_name = os.path.basename(file_path)
    collection = get_collection()

    previous = collection.get(
        where={"document_id": final_document_id},
        include=[],
    )
    previous_ids = previous.get("ids") or []
    if previous_ids:
        collection.delete(ids=previous_ids)
        get_bm25_index().delete_documents(previous_ids)

    texts: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    doc_ids: List[str] = []

    for index, chunk in enumerate(parsed_chunks):
        chunk_text_value = str(chunk.get("text") or "").strip()
        if not chunk_text_value:
            continue

        section_heading = str(
            chunk.get("heading") or "General"
        )
        section_number = str(
            chunk.get("section_number") or "1"
        )
        top_level = section_number.split(".")[0]
        parent_heading = PARENT_HEADINGS.get(top_level, "")

        heading_context = section_heading
        if parent_heading and parent_heading != section_heading:
            heading_context = f"{parent_heading} > {section_heading}"

        indexed_text = (
            f"{heading_context}\n{chunk_text_value}"
        ).strip()

        metadata: Dict[str, Any] = {
            "section": section_heading,
            "section_number": section_number,
            "document_id": final_document_id,
            "entity_type": str(
                chunk.get("entity_type") or "profile"
            ),
            "chunk_index": index,
            "source": source_name,
        }
        if chunk.get("subsection"):
            metadata["subsection"] = str(chunk["subsection"])

        texts.append(indexed_text)
        metadatas.append(metadata)
        doc_ids.append(
            f"{final_document_id}_chunk_{index}"
        )

    added_ids = add_documents_batch(
        texts,
        metadatas,
        doc_ids,
    )

    gc.collect()
    logger.info(
        "Processed PDF '%s': created %d lightweight chunks",
        source_name,
        len(added_ids),
    )
    return added_ids
