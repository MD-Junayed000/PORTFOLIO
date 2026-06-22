import gc
import logging
import math
import re
import os
import uuid
from collections import Counter
from typing import Dict, List, Optional, Tuple
 
import chromadb
from PyPDF2 import PdfReader
 
from config import settings
 
logger = logging.getLogger(__name__)
 
 
_client: Optional[chromadb.ClientAPI] = None
_collection = None
 
# Global BM25 index instance
_bm25_index: Optional["SimpleBM25"] = None
 
 
# --- Entity type mapping based on section numbers ---
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
 
# Section relevance mapping for query boosting
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
    """Simple BM25 implementation for keyword search - no external dependencies."""
 
    def __init__(self):
        self.docs: List[List[str]] = []
        self.doc_ids: List[str] = []
        self.avg_dl: float = 0
        self.doc_count: int = 0
        self.idf: Dict[str, float] = {}
 
    def add_documents(self, documents: List[str], doc_ids: List[str] = None):
        """Add documents to the BM25 index."""
        for i, doc in enumerate(documents):
            tokens = self._tokenize(doc)
            self.docs.append(tokens)
            if doc_ids:
                self.doc_ids.append(doc_ids[i])
            else:
                self.doc_ids.append(str(len(self.docs) - 1))
        self.doc_count = len(self.docs)
        self.avg_dl = sum(len(d) for d in self.docs) / max(self.doc_count, 1)
        self._compute_idf()
 
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into lowercase words (min 2 chars)."""
        return re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
 
    def _compute_idf(self):
        """Compute inverse document frequency for all terms."""
        df: Counter = Counter()
        for doc in self.docs:
            unique_terms = set(doc)
            for term in unique_terms:
                df[term] += 1
        self.idf = {}
        for term, freq in df.items():
            self.idf[term] = math.log(
                (self.doc_count - freq + 0.5) / (freq + 0.5) + 1
            )
 
    def search(self, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
        """Search for documents matching query. Returns list of (index, score)."""
        query_tokens = self._tokenize(query)
        scores: List[Tuple[int, float]] = []
        k1, b = 1.5, 0.75
        for idx, doc in enumerate(self.docs):
            score = 0.0
            doc_len = len(doc)
            tf_counter = Counter(doc)
            for term in query_tokens:
                if term in self.idf:
                    tf = tf_counter.get(term, 0)
                    numerator = tf * (k1 + 1)
                    denominator = tf + k1 * (1 - b + b * doc_len / max(self.avg_dl, 1))
                    score += self.idf[term] * numerator / denominator
            scores.append((idx, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
 
    def clear(self):
        """Clear all documents from the index."""
        self.docs = []
        self.doc_ids = []
        self.avg_dl = 0
        self.doc_count = 0
        self.idf = {}
 
 
def get_bm25_index() -> SimpleBM25:
    """Get or create the global BM25 index."""
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = SimpleBM25()
    return _bm25_index
 
 
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
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    word_freq: Dict[str, int] = {}
    for word in words:
        if word not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    top_keywords = [w for w, _ in sorted_words[:10]]
    return ",".join(top_keywords)
 
 
def _get_entity_type(section_number: str) -> str:
    """Map a section number to its entity type."""
    # Get the top-level section number
    top_level = section_number.split(".")[0]
    return SECTION_ENTITY_MAP.get(top_level, "profile")
 
 
def _clean_pdf_text(text: str) -> str:
    """Remove repeated page headers and page markers from PDF text."""
    # Remove "Page X" markers (standalone on a line or at boundaries)
    text = re.sub(r'\bPage\s+\d+\b', '', text, flags=re.IGNORECASE)
    # Remove repeated portfolio header
    text = re.sub(
        r'Muhammad\s+Junayed\s*[-\u2013\u2014]\s*Complete\s+Portfolio[^\n]*\n?',
        '',
        text,
        flags=re.IGNORECASE,
    )
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
 
 
def _parse_sections(text: str) -> List[Dict]:
    """Parse PDF text into sections based on numbered headings.
 
    Returns a list of dicts with keys: heading, section_number, subsection, text, entity_type
    """
    # Pattern to match section headings like "1. Professional Profile" or "10.3 Some Project"
    heading_pattern = re.compile(r'^(\d+(?:\.\d+)*)\s+(.+)$', re.MULTILINE)
 
    matches = list(heading_pattern.finditer(text))
 
    if not matches:
        # No headings found, return entire text as one section
        return [{
            "heading": "General",
            "section_number": "1",
            "subsection": None,
            "text": text.strip(),
            "entity_type": "profile",
        }]
 
    sections = []
    for i, match in enumerate(matches):
        section_number = match.group(1)
        heading_title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
 
        section_text = text[start:end].strip()
 
        # Determine subsection
        subsection = None
        if "." in section_number:
            # It's a subsection (e.g., "3.1")
            parts = section_number.split(".")
            subsection = heading_title
 
        entity_type = _get_entity_type(section_number)
 
        sections.append({
            "heading": heading_title,
            "section_number": section_number,
            "subsection": subsection,
            "text": section_text,
            "entity_type": entity_type,
        })
 
    return sections
 
 
def _split_section_into_chunks(
    section: Dict,
    max_chars: int = 2500,
    overlap_chars: int = 240,
) -> List[Dict]:
    """Split a section into chunks if it exceeds max_chars.
 
    Splits at paragraph boundaries within the section.
    Target: 500-700 tokens (~2000-2800 chars).
    Overlap: 60 tokens (~240 chars).
    """
    text = section["text"]
 
    if len(text) <= max_chars:
        # Section fits in one chunk
        return [section]
 
    # Split at paragraph boundaries (double newline or single newline followed by content)
    paragraphs = re.split(r'\n\s*\n', text)
 
    chunks = []
    current_chunk_text = ""
 
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
 
        if current_chunk_text and len(current_chunk_text) + len(para) + 2 > max_chars:
            # Save current chunk
            chunk_data = section.copy()
            chunk_data["text"] = current_chunk_text.strip()
            chunks.append(chunk_data)
 
            # Start new chunk with overlap from end of previous
            if len(current_chunk_text) > overlap_chars:
                overlap_text = current_chunk_text[-overlap_chars:]
                # Try to start at a word/sentence boundary
                space_idx = overlap_text.find(" ")
                if space_idx != -1:
                    overlap_text = overlap_text[space_idx + 1:]
                current_chunk_text = overlap_text + "\n\n" + para
            else:
                current_chunk_text = para
        else:
            if current_chunk_text:
                current_chunk_text += "\n\n" + para
            else:
                current_chunk_text = para
 
    # Handle remaining text
    if current_chunk_text.strip():
        # If remaining text is very short, merge with last chunk if possible
        if chunks and len(current_chunk_text) < 200:
            chunks[-1]["text"] += "\n\n" + current_chunk_text.strip()
        else:
            chunk_data = section.copy()
            chunk_data["text"] = current_chunk_text.strip()
            chunks.append(chunk_data)
 
    return chunks if chunks else [section]
 
 
def chunk_pdf_by_headings(text: str) -> List[Dict]:
    """Main chunking function: heading-aware semantic chunking for the canonical PDF.
 
    Returns list of dicts with: text, heading, section_number, subsection, entity_type
    """
    # Clean the text first
    cleaned = _clean_pdf_text(text)
 
    # Parse into sections
    sections = _parse_sections(cleaned)
 
    # Split large sections into smaller chunks
    all_chunks = []
    for section in sections:
        chunks = _split_section_into_chunks(section)
        all_chunks.extend(chunks)
 
    return all_chunks
 
 
def add_document(text: str, metadata: Dict = None, doc_id: str = None) -> str:
    """Add a single document to the vector store and BM25 index."""
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
    # Also add to BM25 index
    bm25 = get_bm25_index()
    bm25.add_documents([text], [doc_id])
    return doc_id
 
 
def add_documents_batch(
    texts: List[str],
    metadatas: List[Dict],
    doc_ids: List[str],
) -> List[str]:
    """Add multiple documents to both ChromaDB and BM25 index one at a time to keep memory low."""
    collection = get_collection()
    bm25 = get_bm25_index()
 
    for i in range(len(texts)):
        meta = metadatas[i]
        if "keywords" not in meta:
            meta["keywords"] = extract_keywords(texts[i])
        # Add one at a time to keep memory low
        collection.add(
            documents=[texts[i]],
            metadatas=[meta],
            ids=[doc_ids[i]],
        )
 
    # Add all to BM25 (lightweight - just stores tokenized words)
    bm25.add_documents(texts, doc_ids)
 
    return doc_ids
 
 
def _get_section_boost(question: str, chunk_metadata: Dict) -> float:
    """Calculate section relevance boost based on question content and chunk section."""
    question_lower = question.lower()
    section_number = chunk_metadata.get("section_number", "")
    top_section = section_number.split(".")[0] if section_number else ""
 
    boost = 0.0
    # Check if question mentions category keywords that map to sections
    boost_keywords = {
        "project": ["project", "built", "developed", "made", "created", "app", "application"],
        "skill": ["skill", "technology", "proficient", "know", "stack", "framework", "tool"],
        "experience": ["experience", "work", "job", "intern", "company", "employ", "role"],
        "education": ["education", "university", "degree", "study", "course", "gpa", "cgpa"],
        "research": ["research", "paper", "publication", "thesis", "conference", "journal"],
        "award": ["award", "achievement", "honor", "prize", "recognition", "winner"],
        "language": ["language", "speak", "fluent", "bangla", "english"],
        "profile": ["who", "about", "introduce", "summary", "overview", "junayed", "muhammad", "tell me about", "background", "himself"],
        "extracurricular": ["extracurricular", "volunteer", "club", "activity", "organization"],
    }
 
    for category, keywords in boost_keywords.items():
        if any(kw in question_lower for kw in keywords):
            relevant_sections = QUERY_SECTION_BOOST.get(category, [])
            if top_section in relevant_sections:
                boost += 5.0
                break
 
    return boost
 
 
def _rerank_results(
    results: List[Dict],
    question: str,
    bm25_scores: Dict[str, float],
) -> List[Dict]:
    """Re-rank results using vector similarity, BM25 scores, and section relevance."""
    scored = []
    for result in results:
        doc_id = result.get("doc_id", "")
 
        # (1) Vector similarity score (convert distance to similarity)
        # ChromaDB cosine distance: 0 = identical, 2 = opposite
        distance = result.get("distance", 1.0)
        vector_score = max(0, 1.0 - distance / 2.0)  # Normalize to 0-1
 
        # (2) BM25 keyword score (already computed)
        bm25_score = bm25_scores.get(doc_id, 0.0)
        # Normalize BM25 score relative to max
        max_bm25 = max(bm25_scores.values()) if bm25_scores else 1.0
        normalized_bm25 = bm25_score / max(max_bm25, 0.001)
 
        # (3) Section relevance boost
        section_boost = _get_section_boost(question, result.get("metadata", {}))
 
        # Combined score: weighted sum
        combined_score = (
            vector_score * 0.4
            + normalized_bm25 * 0.35
            + section_boost * 0.25
        )
        result["combined_score"] = combined_score
        scored.append((combined_score, result))
 
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]
 
 
def query(question: str, n_results: int = 5) -> List[Dict]:
    """Hybrid retrieval: ChromaDB vector search + BM25 keyword search, merged and re-ranked.
 
    Returns top n_results chunks with metadata.
    """
    collection = get_collection()
    if collection.count() == 0:
        return []
 
    # (1) ChromaDB vector search - fetch more candidates for re-ranking
    fetch_count = min(n_results * 3, collection.count())
    try:
        results = collection.query(
            query_texts=[question],
            n_results=fetch_count,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error("ChromaDB query failed: %s", str(e))
        return []
 
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    ids = results.get("ids", [[]])[0]
 
    # Build a map of vector results
    vector_results: Dict[str, Dict] = {}
    for doc, meta, dist, doc_id in zip(documents, metadatas, distances, ids):
        vector_results[doc_id] = {
            "text": doc,
            "metadata": meta,
            "distance": dist,
            "doc_id": doc_id,
        }
 
    # (2) BM25 keyword search
    bm25 = get_bm25_index()
    bm25_scores: Dict[str, float] = {}
    if bm25.doc_count > 0:
        bm25_results = bm25.search(question, top_k=n_results * 3)
        for idx, score in bm25_results:
            if idx < len(bm25.doc_ids):
                bm25_scores[bm25.doc_ids[idx]] = score
 
    # (3) Merge: combine vector results with any BM25-only results
    # Start with vector results (which have distance info)
    merged: Dict[str, Dict] = dict(vector_results)
 
    # Add BM25 results that are not in vector results
    for doc_id, score in bm25_scores.items():
        if doc_id not in merged:
            # Fetch from collection by ID
            try:
                fetched = collection.get(
                    ids=[doc_id],
                    include=["documents", "metadatas"],
                )
                if fetched["documents"]:
                    merged[doc_id] = {
                        "text": fetched["documents"][0],
                        "metadata": fetched["metadatas"][0] if fetched["metadatas"] else {},
                        "distance": 1.0,  # Default distance for BM25-only results
                        "doc_id": doc_id,
                    }
            except Exception:
                pass
 
    # (4) Re-rank all candidates
    all_candidates = list(merged.values())
 
    # Filter by relevance threshold
    RELEVANCE_THRESHOLD = 1.5
    filtered = [
        item for item in all_candidates
        if item["distance"] <= RELEVANCE_THRESHOLD
        or bm25_scores.get(item["doc_id"], 0) > 0
    ]
 
    if not filtered:
        filtered = all_candidates
 
    reranked = _rerank_results(filtered, question, bm25_scores)
    return reranked[:n_results]
 
 
def delete_document(doc_id: str):
    """Delete a document from the vector store."""
    collection = get_collection()
    collection.delete(ids=[doc_id])
 
 
def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    """Legacy: Split text into overlapping chunks using sentence-based splitting.
 
    Kept for backward compatibility with manual document uploads.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""
 
    for sentence in sentences:
        if current_chunk and len(current_chunk) + len(sentence) + 1 > chunk_size:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            if len(current_chunk) > overlap:
                overlap_text = current_chunk[-overlap:]
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
 
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
 
    return chunks
 
 
def process_pdf(file_path: str) -> List[str]:
    """Extract text from PDF and add chunks to vector store using heading-aware chunking."""
    reader = PdfReader(file_path)
    full_text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            full_text += page_text + "\n"
 
    if not full_text.strip():
        return []
 
    # Use heading-aware chunking for structured PDFs
    chunks = chunk_pdf_by_headings(full_text)
 
    if not chunks or len(chunks) < 3:
        # Fallback to legacy chunking if heading parsing fails
        text_chunks = chunk_text(full_text)
        doc_ids = []
        filename = os.path.basename(file_path)
        for i, chunk in enumerate(text_chunks):
            doc_id = add_document(
                text=chunk,
                metadata={"source": filename, "chunk_index": i},
                doc_id=f"{filename}_{i}",
            )
            doc_ids.append(doc_id)
        return doc_ids
 
    # Add all chunks with rich metadata
    texts = []
    metadatas = []
    doc_ids = []
    document_id = "muhammad_junayed_complete_rag_profile"
 
    for i, chunk in enumerate(chunks):
        texts.append(chunk["text"])
        meta = {
            "section": chunk["heading"],
            "section_number": chunk["section_number"],
            "document_id": document_id,
            "entity_type": chunk["entity_type"],
            "chunk_index": i,
            "source": os.path.basename(file_path),
        }
        if chunk.get("subsection"):
            meta["subsection"] = chunk["subsection"]
        metadatas.append(meta)
        doc_ids.append(f"{document_id}_chunk_{i}")
 
    add_documents_batch(texts, metadatas, doc_ids)
    gc.collect()
    logger.info(
        "Processed PDF '%s': created %d chunks with heading-aware chunking",
        os.path.basename(file_path),
        len(texts),
    )
    return doc_ids
