from __future__ import annotations

import gc
import hashlib
import logging
import math
import os
import re
import threading
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from PyPDF2 import PdfReader

from config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "portfolio_knowledge"

_client: Optional[Any] = None
_collection: Optional[Any] = None
_bm25_index: Optional["SimpleBM25"] = None
_index_lock = threading.RLock()


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
    "project": ["10"],
    "skill": ["7"],
    "experience": ["5"],
    "education": ["3", "8"],
    "research": ["4", "6", "9"],
    "award": ["12"],
    "language": ["13"],
    "profile": ["1", "2"],
    "extracurricular": ["11"],
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
        return re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9_+#.-]*\b", text.lower())

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
                (self.doc_count - frequency + 0.5) / (frequency + 0.5) + 1.0
            )
            for term, frequency in document_frequency.items()
        }

    def add_documents(
        self,
        documents: List[str],
        doc_ids: Optional[List[str]] = None,
    ) -> None:
        if doc_ids is not None and len(documents) != len(doc_ids):
            raise ValueError("documents and doc_ids must have the same length")

        with self._lock:
            for index, document in enumerate(documents):
                doc_id = (
                    doc_ids[index]
                    if doc_ids is not None
                    else str(uuid.uuid4())
                )
                self._documents_by_id[doc_id] = self._tokenize(document)
            self._rebuild()

    def delete_documents(self, doc_ids: List[str]) -> None:
        with self._lock:
            for doc_id in doc_ids:
                self._documents_by_id.pop(doc_id, None)
            self._rebuild()

    def search(self, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
        if top_k <= 0:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        with self._lock:
            scores: List[Tuple[int, float]] = []
            k1, b = 1.5, 0.75

            for index, doc in enumerate(self.docs):
                score = 0.0
                doc_len = len(doc)
                term_frequency = Counter(doc)

                for term in query_tokens:
                    if term not in self.idf:
                        continue

                    tf = term_frequency.get(term, 0)
                    if tf == 0:
                        continue

                    numerator = tf * (k1 + 1.0)
                    denominator = tf + k1 * (
                        1.0 - b + b * doc_len / max(self.avg_dl, 1.0)
                    )
                    score += self.idf[term] * numerator / denominator

                if score > 0.0:
                    scores.append((index, score))

            scores.sort(key=lambda item: item[1], reverse=True)
            return scores[:top_k]

    def clear(self) -> None:
        with self._lock:
            self._documents_by_id.clear()
            self._rebuild()


def get_bm25_index() -> SimpleBM25:
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = SimpleBM25()
    return _bm25_index


def get_chroma_client() -> Any:
    global _client

    if _client is None:
        persist_dir = Path(settings.CHROMA_PERSIST_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)

        _client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=chromadb.Settings(anonymized_telemetry=False),
        )

    return _client


def _create_or_get_collection(client: Any) -> Any:
    """Use the current Chroma configuration API, with a legacy fallback."""
    try:
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            configuration={"hnsw": {"space": "cosine"}},
        )
    except TypeError:
        # Compatibility with older Chroma releases.
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )


def rebuild_bm25_from_collection(batch_size: int = 200) -> None:
    """Rebuild the in-memory BM25 index from persistent Chroma records."""
    collection = get_collection()
    bm25 = get_bm25_index()
    bm25.clear()

    total = collection.count()
    for offset in range(0, total, batch_size):
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["documents"],
        )
        ids = batch.get("ids") or []
        documents = batch.get("documents") or []

        valid_ids: List[str] = []
        valid_documents: List[str] = []
        for doc_id, document in zip(ids, documents):
            if document:
                valid_ids.append(doc_id)
                valid_documents.append(document)

        if valid_documents:
            bm25.add_documents(valid_documents, valid_ids)


def initialize_collection() -> Any:
    global _client, _collection

    if _collection is not None:
        return _collection

    try:
        client = get_chroma_client()
        _collection = _create_or_get_collection(client)
    except Exception as exc:
        logger.exception(
            "Persistent ChromaDB initialization failed; using an ephemeral "
            "in-memory collection: %s",
            exc,
        )
        _client = chromadb.Client(
            settings=chromadb.Settings(anonymized_telemetry=False)
        )
        _collection = _create_or_get_collection(_client)

    try:
        rebuild_bm25_from_collection()
    except Exception as exc:
        logger.exception("Could not rebuild BM25 from ChromaDB: %s", exc)

    return _collection


def get_collection() -> Any:
    global _collection
    if _collection is None:
        return initialize_collection()
    return _collection


def _normalize_metadata(metadata: Optional[Dict]) -> Dict:
    """Return Chroma-safe scalar metadata without mutating the caller's dict."""
    normalized: Dict[str, Any] = {}

    for key, value in (metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[str(key)] = value
        else:
            normalized[str(key)] = str(value)

    return normalized


def extract_keywords(text: str) -> str:
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above",
        "below", "between", "out", "off", "over", "under", "again",
        "further", "then", "once", "here", "there", "when", "where",
        "why", "how", "all", "each", "every", "both", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not", "only",
        "own", "same", "so", "than", "too", "very", "just", "because",
        "but", "and", "or", "if", "while", "about", "this", "that",
        "these", "those", "it", "its", "he", "she", "they", "them",
        "his", "her", "their", "what", "which", "who", "whom",
    }

    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    frequencies = Counter(word for word in words if word not in stop_words)
    return ",".join(word for word, _ in frequencies.most_common(10))


def _get_entity_type(section_number: str) -> str:
    top_level = section_number.split(".")[0]
    return SECTION_ENTITY_MAP.get(top_level, "profile")


def _clean_pdf_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?im)^\s*Page\s+\d+(?:\s+of\s+\d+)?\s*$", "", text)
    text = re.sub(
        r"(?im)^\s*Muhammad\s+Junayed\s*[-\u2013\u2014]\s*"
        r"Complete\s+Portfolio[^\n]*$",
        "",
        text,
    )
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_sections(text: str) -> List[Dict]:
    """Parse headings 1-13, accepting both `1 Title` and `1. Title`."""
    heading_pattern = re.compile(
        r"^((?:[1-9]|1[0-3])(?:\.\d+)*)(?:\.)?\s+(.+?)\s*$",
        re.MULTILINE,
    )
    matches = list(heading_pattern.finditer(text))

    if not matches:
        return [{
            "heading": "General",
            "section_number": "1",
            "subsection": None,
            "text": text.strip(),
            "entity_type": "profile",
        }]

    sections: List[Dict] = []
    for index, match in enumerate(matches):
        section_number = match.group(1)
        heading_title = match.group(2).strip()
        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        section_text = text[start:end].strip()
        if not section_text:
            continue

        sections.append({
            "heading": heading_title,
            "section_number": section_number,
            "subsection": heading_title if "." in section_number else None,
            "text": section_text,
            "entity_type": _get_entity_type(section_number),
        })

    return sections


def _hard_split_text(
    text: str,
    max_chars: int,
    overlap_chars: int,
) -> List[str]:
    """Split oversized text while preserving sentence/word boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    pieces: List[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) > max_chars:
            words = sentence.split()
            word_block = ""
            for word in words:
                candidate = f"{word_block} {word}".strip()
                if word_block and len(candidate) > max_chars:
                    pieces.append(word_block)
                    overlap = word_block[-overlap_chars:].lstrip()
                    word_block = f"{overlap} {word}".strip()
                else:
                    word_block = candidate
            if word_block:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.append(word_block)
            continue

        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            pieces.append(current)
            overlap = current[-overlap_chars:].lstrip()
            current = f"{overlap} {sentence}".strip()
        else:
            current = candidate

    if current:
        pieces.append(current)

    return pieces or [text.strip()]


def _split_section_into_chunks(
    section: Dict,
    max_chars: int = 2500,
    overlap_chars: int = 240,
) -> List[Dict]:
    text = section["text"].strip()
    if not text:
        return []

    if len(text) <= max_chars:
        return [section.copy()]

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]

    text_chunks: List[str] = []
    current = ""

    for paragraph in paragraphs:
        paragraph_parts = (
            _hard_split_text(paragraph, max_chars, overlap_chars)
            if len(paragraph) > max_chars
            else [paragraph]
        )

        for part in paragraph_parts:
            candidate = f"{current}\n\n{part}".strip()
            if current and len(candidate) > max_chars:
                text_chunks.append(current.strip())
                overlap = current[-overlap_chars:].lstrip()
                current = f"{overlap}\n\n{part}".strip()
            else:
                current = candidate

    if current:
        text_chunks.append(current.strip())

    chunks: List[Dict] = []
    for chunk_index, chunk_text in enumerate(text_chunks):
        chunk = section.copy()
        chunk["text"] = chunk_text
        chunk["section_chunk_index"] = chunk_index
        chunks.append(chunk)

    return chunks


def chunk_pdf_by_headings(text: str) -> List[Dict]:
    cleaned = _clean_pdf_text(text)
    sections = _parse_sections(cleaned)

    chunks: List[Dict] = []
    for section in sections:
        chunks.extend(_split_section_into_chunks(section))
    return chunks


def add_document(
    text: str,
    metadata: Optional[Dict] = None,
    doc_id: Optional[str] = None,
) -> str:
    if not text or not text.strip():
        raise ValueError("text must not be empty")

    collection = get_collection()
    final_doc_id = doc_id or str(uuid.uuid4())

    final_metadata = _normalize_metadata(metadata)
    final_metadata.setdefault("keywords", extract_keywords(text))

    collection.upsert(
        documents=[text.strip()],
        metadatas=[final_metadata],
        ids=[final_doc_id],
    )

    get_bm25_index().add_documents([text.strip()], [final_doc_id])
    return final_doc_id


def add_documents_batch(
    texts: List[str],
    metadatas: List[Dict],
    doc_ids: List[str],
    batch_size: int = 32,
) -> List[str]:
    if not (len(texts) == len(metadatas) == len(doc_ids)):
        raise ValueError("texts, metadatas, and doc_ids must have equal lengths")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    collection = get_collection()

    cleaned_texts: List[str] = []
    cleaned_metadatas: List[Dict] = []
    cleaned_ids: List[str] = []

    for text, metadata, doc_id in zip(texts, metadatas, doc_ids):
        if not text or not text.strip():
            continue

        clean_text = text.strip()
        clean_metadata = _normalize_metadata(metadata)
        clean_metadata.setdefault("keywords", extract_keywords(clean_text))

        cleaned_texts.append(clean_text)
        cleaned_metadatas.append(clean_metadata)
        cleaned_ids.append(doc_id)

    for start in range(0, len(cleaned_texts), batch_size):
        end = start + batch_size
        collection.upsert(
            documents=cleaned_texts[start:end],
            metadatas=cleaned_metadatas[start:end],
            ids=cleaned_ids[start:end],
        )

    get_bm25_index().add_documents(cleaned_texts, cleaned_ids)
    return cleaned_ids


def _get_section_boost(question: str, chunk_metadata: Dict) -> float:
    """Return a normalized category match: either 0.0 or 1.0."""
    question_lower = question.lower()
    section_number = str(chunk_metadata.get("section_number", ""))
    top_section = section_number.split(".")[0] if section_number else ""

    boost_keywords = {
        "project": [
            "project", "built", "developed", "made", "created", "app",
            "application",
        ],
        "skill": [
            "skill", "technology", "proficient", "know", "stack",
            "framework", "tool",
        ],
        "experience": [
            "experience", "work", "job", "intern", "company", "employ", "role",
        ],
        "education": [
            "education", "university", "degree", "study", "course", "gpa",
            "cgpa",
        ],
        "research": [
            "research", "paper", "publication", "thesis", "conference",
            "journal",
        ],
        "award": [
            "award", "achievement", "honor", "prize", "recognition", "winner",
        ],
        "language": [
            "language", "speak", "fluent", "bangla", "english",
        ],
        "profile": [
            "who", "about", "introduce", "summary", "overview", "background",
        ],
        "extracurricular": [
            "extracurricular", "volunteer", "club", "activity", "organization",
        ],
    }

    for category, keywords in boost_keywords.items():
        if any(keyword in question_lower for keyword in keywords):
            if top_section in QUERY_SECTION_BOOST.get(category, []):
                return 1.0
            return 0.0

    return 0.0


def _rerank_results(
    results: List[Dict],
    question: str,
    bm25_scores: Dict[str, float],
) -> List[Dict]:
    if not results:
        return []

    max_bm25 = max(bm25_scores.values(), default=0.0)
    scored: List[Tuple[float, Dict]] = []

    for result in results:
        doc_id = result.get("doc_id", "")
        distance = float(result.get("distance", 1.0))

        # For cosine distance d = 1 - cosine_similarity, this maps [-1, 1]
        # cosine similarity into [0, 1].
        vector_score = min(1.0, max(0.0, 1.0 - distance / 2.0))

        raw_bm25 = bm25_scores.get(doc_id, 0.0)
        normalized_bm25 = raw_bm25 / max_bm25 if max_bm25 > 0 else 0.0

        section_score = _get_section_boost(
            question,
            result.get("metadata") or {},
        )

        combined_score = (
            0.55 * vector_score
            + 0.35 * normalized_bm25
            + 0.10 * section_score
        )

        ranked_result = dict(result)
        ranked_result["vector_score"] = vector_score
        ranked_result["bm25_score"] = normalized_bm25
        ranked_result["section_score"] = section_score
        ranked_result["combined_score"] = combined_score
        scored.append((combined_score, ranked_result))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [result for _, result in scored]


def query(question: str, n_results: int = 5) -> List[Dict]:
    question = (question or "").strip()
    if not question or n_results <= 0:
        return []

    collection = get_collection()
    collection_size = collection.count()
    if collection_size == 0:
        return []

    fetch_count = min(max(n_results * 4, n_results), collection_size)

    try:
        results = collection.query(
            query_texts=[question],
            n_results=fetch_count,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.exception("ChromaDB query failed: %s", exc)
        return []

    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    ids = (results.get("ids") or [[]])[0]

    vector_results: Dict[str, Dict] = {}
    for document, metadata, distance, doc_id in zip(
        documents,
        metadatas,
        distances,
        ids,
    ):
        if not document:
            continue
        vector_results[doc_id] = {
            "text": document,
            "metadata": metadata or {},
            "distance": float(distance),
            "doc_id": doc_id,
        }

    bm25 = get_bm25_index()
    bm25_scores: Dict[str, float] = {}

    for index, score in bm25.search(question, top_k=fetch_count):
        if 0 <= index < len(bm25.doc_ids) and score > 0:
            bm25_scores[bm25.doc_ids[index]] = score

    merged: Dict[str, Dict] = dict(vector_results)

    bm25_only_ids = [
        doc_id
        for doc_id in bm25_scores
        if doc_id not in merged
    ]

    if bm25_only_ids:
        try:
            fetched = collection.get(
                ids=bm25_only_ids,
                include=["documents", "metadatas"],
            )
            fetched_ids = fetched.get("ids") or []
            fetched_documents = fetched.get("documents") or []
            fetched_metadatas = fetched.get("metadatas") or []

            for doc_id, document, metadata in zip(
                fetched_ids,
                fetched_documents,
                fetched_metadatas,
            ):
                if document:
                    merged[doc_id] = {
                        "text": document,
                        "metadata": metadata or {},
                        # Neutral semantic score for a lexical-only candidate.
                        "distance": 1.0,
                        "doc_id": doc_id,
                    }
        except Exception as exc:
            logger.warning("Could not fetch BM25-only candidates: %s", exc)

    reranked = _rerank_results(
        list(merged.values()),
        question,
        bm25_scores,
    )
    return reranked[:n_results]


def delete_document(doc_id: str) -> None:
    if not doc_id:
        return

    collection = get_collection()
    collection.delete(ids=[doc_id])
    get_bm25_index().delete_documents([doc_id])


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


def _make_document_id(file_path: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(file_path).stem).strip("_")
    stem = stem or "document"
    path_hash = hashlib.sha1(
        str(Path(file_path).resolve()).encode("utf-8")
    ).hexdigest()[:10]
    return f"{stem.lower()}_{path_hash}"


def process_pdf(
    file_path: str,
    document_id: Optional[str] = None,
) -> List[str]:
    reader = PdfReader(file_path)
    page_texts = [
        page.extract_text() or ""
        for page in reader.pages
    ]
    full_text = "\n".join(page_texts).strip()

    if not full_text:
        logger.warning("No extractable text found in PDF: %s", file_path)
        return []

    parsed_chunks = chunk_pdf_by_headings(full_text)
    has_real_headings = any(
        chunk.get("heading") != "General"
        for chunk in parsed_chunks
    )

    if not has_real_headings:
        text_chunks = chunk_text(full_text)
        parsed_chunks = [
            {
                "text": chunk,
                "heading": "General",
                "section_number": "1",
                "subsection": None,
                "entity_type": "profile",
            }
            for chunk in text_chunks
        ]

    final_document_id = document_id or _make_document_id(file_path)
    source_name = os.path.basename(file_path)
    collection = get_collection()

    # Remove stale chunks from an earlier version of this same document.
    try:
        previous = collection.get(
            where={"document_id": final_document_id},
            include=[],
        )
        previous_ids = previous.get("ids") or []
        if previous_ids:
            collection.delete(ids=previous_ids)
            get_bm25_index().delete_documents(previous_ids)
    except Exception as exc:
        logger.warning(
            "Could not remove previous chunks for %s: %s",
            final_document_id,
            exc,
        )

    texts: List[str] = []
    metadatas: List[Dict] = []
    doc_ids: List[str] = []

    for index, chunk in enumerate(parsed_chunks):
        chunk_text_value = (chunk.get("text") or "").strip()
        if not chunk_text_value:
            continue

        texts.append(chunk_text_value)
        metadata = {
            "section": chunk.get("heading", "General"),
            "section_number": chunk.get("section_number", "1"),
            "document_id": final_document_id,
            "entity_type": chunk.get("entity_type", "profile"),
            "chunk_index": index,
            "source": source_name,
        }
        if chunk.get("subsection"):
            metadata["subsection"] = chunk["subsection"]

        metadatas.append(metadata)
        doc_ids.append(f"{final_document_id}_chunk_{index}")

    added_ids = add_documents_batch(texts, metadatas, doc_ids)

    gc.collect()
    logger.info(
        "Processed PDF '%s': created %d chunks",
        source_name,
        len(added_ids),
    )
    return added_ids
