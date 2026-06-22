import logging
import re

import chromadb
from PyPDF2 import PdfReader
from typing import List, Dict, Optional
import os
import uuid

from config import settings

logger = logging.getLogger(__name__)


_client: Optional[chromadb.ClientAPI] = None
_collection = None


def get_chroma_client():
    global _client
    if _client is None:
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
    return _client


def initialize_collection():
    global _collection
    try:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name="portfolio_knowledge",
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as e:
        # Fallback: use simple in-memory client if persistent fails
        logger.warning(
            "ChromaDB persistent client failed, falling back to in-memory mode: %s",
            str(e),
        )
        global _client
        _client = chromadb.Client()
        _collection = _client.get_or_create_collection(
            name="portfolio_knowledge",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def get_collection():
    global _collection
    if _collection is None:
        initialize_collection()
    return _collection


def extract_keywords(text: str) -> str:
    """Extract top keywords from text for metadata storage."""
    # Remove common stop words and extract meaningful terms
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
    # Extract words (alphanumeric, min 3 chars)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    # Filter stop words and count frequencies
    word_freq: Dict[str, int] = {}
    for word in words:
        if word not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1
    # Sort by frequency and take top 10
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    top_keywords = [w for w, _ in sorted_words[:10]]
    return ",".join(top_keywords)


def add_document(text: str, metadata: Dict = None, doc_id: str = None) -> str:
    collection = get_collection()
    if doc_id is None:
        doc_id = str(uuid.uuid4())
    if metadata is None:
        metadata = {}
    # Add keywords to metadata if not already present
    if "keywords" not in metadata:
        metadata["keywords"] = extract_keywords(text)
    collection.add(
        documents=[text],
        metadatas=[metadata],
        ids=[doc_id],
    )
    return doc_id


def _rerank_results(results: List[Dict], question: str) -> List[Dict]:
    """Re-rank results by keyword overlap with the query."""
    query_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', question.lower()))
    scored = []
    for result in results:
        text_lower = result["text"].lower()
        # Score by how many query words appear in the result text
        score = sum(1 for word in query_words if word in text_lower)
        # Bonus for keyword metadata matches
        keywords = result.get("metadata", {}).get("keywords", "")
        keyword_set = set(keywords.split(",")) if keywords else set()
        score += sum(0.5 for word in query_words if word in keyword_set)
        scored.append((score, result))
    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


def query(question: str, n_results: int = 3) -> List[Dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    fetch_count = min(n_results * 2, collection.count())
    results = collection.query(
        query_texts=[question],
        n_results=fetch_count,
        include=["documents", "metadatas", "distances"],
    )
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    # Filter by relevance threshold (cosine distance: lower = more similar)
    RELEVANCE_THRESHOLD = 1.5
    items = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        if dist <= RELEVANCE_THRESHOLD:
            items.append({"text": doc, "metadata": meta, "distance": dist})

    # Re-rank by keyword overlap
    reranked = _rerank_results(items, question)
    return reranked[:n_results]


def delete_document(doc_id: str):
    collection = get_collection()
    collection.delete(ids=[doc_id])


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    """Split text into overlapping chunks using sentence-based splitting."""
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        # If adding this sentence exceeds chunk_size, save current chunk and start new one
        if current_chunk and len(current_chunk) + len(sentence) + 1 > chunk_size:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            # Start new chunk with overlap from end of previous chunk
            # Take the last `overlap` characters of the previous chunk
            if len(current_chunk) > overlap:
                overlap_text = current_chunk[-overlap:]
                # Try to start at a word boundary
                space_idx = overlap_text.find(" ")
                if space_idx != -1:
                    overlap_text = overlap_text[space_idx + 1:]
                current_chunk = overlap_text + " " + sentence
            else:
                current_chunk = sentence
        else:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence

    # Add the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def process_pdf(file_path: str) -> List[str]:
    """Extract text from PDF and add chunks to vector store."""
    reader = PdfReader(file_path)
    full_text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            full_text += page_text + "\n"

    if not full_text.strip():
        return []

    chunks = chunk_text(full_text)
    doc_ids = []
    filename = os.path.basename(file_path)
    for i, chunk in enumerate(chunks):
        doc_id = add_document(
            text=chunk,
            metadata={"source": filename, "chunk_index": i},
            doc_id=f"{filename}_{i}",
        )
        doc_ids.append(doc_id)

    return doc_ids
