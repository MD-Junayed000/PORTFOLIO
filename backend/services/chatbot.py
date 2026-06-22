import asyncio
import logging
import re
 
import httpx
from typing import Optional
 
from config import settings
from services.vector_store import query as vector_query
 
logger = logging.getLogger(__name__)
 
 
SYSTEM_PROMPT = """You are Muhammad Junayed's portfolio assistant. Answer questions about him using the context below.
 
Rules:
- Use ONLY the context to answer. Be concise (2-4 sentences).
- Speak naturally in complete sentences. NEVER use bullet points or lists.
- NEVER include metadata fields such as Document ID, Authors, Conference, DOI, Publisher, Pages, Code repository, Publication date, or any "Key: Value" formatted data in your response.
- NEVER echo raw formatting, section headers, or structured data from the context.
- NEVER repeat instructional notes, disclaimers, or meta-commentary from the context (e.g., phrases about what is "not documented", "not specified", or what "should not be inferred"). Only state facts.
- If the question is unrelated to Junayed's portfolio (weather, opinions, general knowledge), say: "I can only answer questions about Muhammad Junayed's portfolio and background."
- If the context doesn't contain the answer, say you don't have that specific information.
 
Context:
{context}
"""
 
 
# Detect off-topic questions that have nothing to do with a person's portfolio
OFF_TOPIC_KEYWORDS = [
    "weather", "sports", "game score", "movie", "recipe", "cook",
    "joke", "funny", "news today", "stock", "crypto", "bitcoin",
    "president", "politics", "war", "religion", "god",
    "meaning of life", "what time", "calculate", "math",
    "translate", "write code", "debug", "fix my",
]
 
 
def _is_off_topic(message: str) -> bool:
    message_lower = message.lower()
    # Check for off-topic keywords
    if any(kw in message_lower for kw in OFF_TOPIC_KEYWORDS):
        return True
    # If the message doesn't mention junayed/portfolio-related terms
    # AND doesn't ask about skills/projects/experience/education etc, it's likely off-topic
    portfolio_keywords = [
        "junayed", "skill", "project", "experience", "education", "research",
        "paper", "publication", "work", "works", "working", "job", "employ", "employed",
        "built", "tech", "stack", "language",
        "linkedin", "github", "email", "contact", "phone", "address", "cv",
        "resume", "certificate", "background", "about", "who", "qualification",
        "university", "cuet", "degree", "internship", "company", "kaggle",
        "scholar", "award", "achievement", "portfolio",
        "live", "lives", "located", "home", "city", "country", "place", "from", "based",
        "cgpa", "gpa", "grade", "result", "score", "marks",
        "thesis", "course", "coursework", "language", "speak", "bangla", "english",
        "interest", "orcid", "doi", "poridhi", "brain station", "intern", "hackathon",
        "competition", "conference", "ieee", "acl", "semeval", "televerse", "arobot",
        "rickshaw", "bistro", "sensor", "iot", "embedded", "extracurricular",
        "volunteer", "activity", "club", "society", "training", "trainee",
        "supervisor",
    ]
 
    # Pronouns alone are NOT sufficient to indicate portfolio relevance.
    # They only count if combined with a substantive keyword or a longer message.
    pronoun_keywords = ["he", "his", "him"]
 
    has_portfolio_relevance = any(kw in message_lower for kw in portfolio_keywords)
 
    # Check if pronouns are present (word-boundary match to avoid false positives)
    has_pronoun = any(
        re.search(r'\b' + re.escape(p) + r'\b', message_lower) for p in pronoun_keywords
    )
 
    # Pronouns only count as portfolio-relevant if the message ALSO contains
    # a substantive portfolio keyword OR is longer than 6 words
    if not has_portfolio_relevance and has_pronoun:
        if len(message.split()) > 6:
            has_portfolio_relevance = True
        # Otherwise pronouns alone don't make it portfolio-relevant
 
    # Short generic questions without portfolio keywords are likely off-topic
    if not has_portfolio_relevance and len(message.split()) <= 6:
        return True
    return False
 
 
def _clean_context_for_llm(context: str) -> str:
    """Remove metadata artifacts from context to prevent LLM from echoing them.
    
    The PDF contains structured metadata in '* Key: Value' format that the LLM
    tends to echo verbatim. Strip all of these and keep only narrative text.
    """
    lines = context.split("\n")
    cleaned_lines = []
 
    # Section headers that should be removed when they appear alone on a line
    standalone_headers = {
        "research problem", "approach", "dataset", "images", "keywords",
        "key contributions", "methodology", "results", "conclusion",
    }
 
    # Known metadata labels that should always be stripped from context.
    # This targeted approach avoids false-positives on narrative sentences
    # that happen to contain a colon (e.g., "His focus: NLP and vision systems").
    metadata_labels_pattern = re.compile(
        r'^[\s•◦▪\-*]*(?:'
        r'Document ID|Authors?|Conference|Publisher|DOI link|DOI|Pages?|'
        r'Code repository|Publication date|Conference abbreviation|'
        r'Conference location|Team|Venue|Workshop abbreviation|'
        r'Official paper link|Muhammad Junayed\'s author position|'
        r'Employment type|Duration|Organization|Role|'
        r'Source|Title|Volume|Issue|Journal|ISSN|ISBN|'
        r'Affiliation|Institution|Department|Year|Date|'
        r'Keywords|Abstract|References|Citation|'
        r'Dataset|Common abbreviation|Common|Target classes|Target|'
        r'Training type|Evaluation|Main|Shared|Exact|Individual|'
        r'Comparison|Per-|Error'
        r')[^:\n]{0,40}:\s+.+',
        re.IGNORECASE
    )
 
    # Fallback: lines with a short pre-colon segment (<=3 words, no lowercase verbs)
    # that look like metadata labels rather than narrative sentences.
    short_label_pattern = re.compile(
        r'^[\s•◦▪\-*]*([A-Z][A-Za-z]*(?:\s+[A-Za-z]+){0,2}):\s+.+'
    )
 
    prev_was_metadata = False
 
    for line in lines:
        stripped = line.strip()
 
        # Skip empty lines (will re-add paragraph breaks later)
        if not stripped:
            prev_was_metadata = False
            cleaned_lines.append("")
            continue
 
        # Handle multi-line metadata values: if the previous line was stripped as
        # metadata, also remove continuation lines (short lines without their own
        # bullet, don't end with sentence-ending punctuation, and don't start a
        # new sentence with a capital letter after whitespace).
        if prev_was_metadata:
            # A continuation line is typically short, has no bullet, and doesn't
            # end with sentence-ending punctuation (., !, ?)
            if (not re.match(r'^[•◦▪\-*]', stripped)
                    and not stripped.endswith(('.', '!', '?'))
                    and len(stripped.split()) <= 8):
                # This looks like a continuation of the metadata value (e.g., "Systems")
                continue
            # If it does look like a new item, fall through to normal processing
            prev_was_metadata = False
 
        # Skip lines matching known metadata labels (with or without bullet prefix)
        if metadata_labels_pattern.match(stripped):
            prev_was_metadata = True
            continue
 
        # For lines matching a short label pattern (<=3 capitalized words before colon),
        # only strip if the pre-colon segment looks like a metadata label, not a narrative.
        # Narrative sentences typically have more context before the colon or start with
        # pronouns/articles (His, The, A, etc.)
        short_match = short_label_pattern.match(stripped)
        if short_match:
            pre_colon = short_match.group(1).strip()
            pre_colon_words = pre_colon.split()
            # If it's a single capitalized word or a 2-word capitalized phrase
            # AND doesn't start with common narrative starters, treat as metadata.
            # Examples that should be stripped: "Dataset: BUSI", "Role: Intern",
            # "Common abbreviation: BUSI", "Target classes: Normal, benign"
            # Examples that should survive: "His focus: NLP", "The goal: detection"
            narrative_starters = {'his', 'her', 'the', 'a', 'an', 'my', 'our', 'their', 'its', 'this', 'that'}
            if (len(pre_colon_words) <= 2
                    and pre_colon_words[0].lower() not in narrative_starters):
                # Looks like a metadata label (e.g., "Publisher: IEEE", "Dataset: BUSI")
                # but NOT "His focus: NLP" or "The goal: detecting hallucinations"
                prev_was_metadata = True
                continue
 
        # Skip standalone section headers
        if stripped.lower().rstrip(":").strip() in standalone_headers:
            prev_was_metadata = False
            continue
 
        # Catch-all: ANY line starting with a bullet char followed by word(s) and a colon
        # is treated as metadata and stripped. Bullet-prefixed "Key: Value" patterns from
        # the PDF are always structured metadata, never narrative prose.
        if re.match(r'^[•◦▪]\s+[A-Za-z][^:]{0,60}:\s+', stripped):
            prev_was_metadata = True
            continue
 
        # Skip lines that are just URLs (DOI links, code repo links, etc.)
        if re.match(r'^https?://', stripped):
            continue
 
        # Skip "Information Not Provided" markers
        if "information not provided" in stripped.lower():
            continue
 
        # Skip lines that are just standalone labels like "Images"
        if stripped in ("Images", "Keywords"):
            continue
 
        # Skip "Keywords" lines with semicolons (keyword lists)
        if stripped.lower().startswith("keywords") and ";" in stripped:
            continue
 
        # Skip standalone section numbers like "- 11." or "- 5."
        if re.match(r'^[\-*•]\s*\d+\.?\s*$', stripped):
            continue
 
        # Skip lines that are pure bullet points with no narrative content
        # (e.g., lines that are just a bullet char or bullet + short label)
        if re.match(r'^[•◦▪\-*]\s*$', stripped):
            continue
 
        # Skip lines starting with bullet chars that look like list metadata
        if re.match(r'^[•◦▪\-*]\s+[A-Z][^.!?]{0,80}$', stripped) and ':' not in stripped:
            # This is a standalone bullet label without sentence structure - skip
            # But keep it if it looks like a real sentence (has a verb-like structure)
            words = stripped.lstrip('•◦▪-* ').split()
            if len(words) <= 4:
                continue
 
        cleaned_lines.append(line)
        prev_was_metadata = False
 
    result = "\n".join(cleaned_lines)
    # Collapse multiple blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)
    # Remove any remaining lone bullet chars on their own line
    result = re.sub(r'^\s*[•◦▪]\s*$', '', result, flags=re.MULTILINE)
    # Remove trailing standalone section headers that appear at end of a line
    # (e.g., "...breast-ultrasound images. Dataset" -> "...breast-ultrasound images.")
    standalone_headers_pattern = '|'.join(re.escape(h.title()) for h in standalone_headers)
    result = re.sub(
        r'([.!?])\s+(?:' + standalone_headers_pattern + r')\s*$',
        r'\1', result, flags=re.MULTILINE
    )
    return result.strip()
 
 
async def generate_response(user_message: str) -> dict:
    """Generate a response using RAG: query vector store for context, then call HuggingFace."""
    # Handle greetings directly (before off-topic check)
    greeting_words = {"hello", "hi", "hey", "greetings", "howdy", "hola", "yo", "sup", "good morning", "good evening", "good afternoon"}
    stripped = re.sub(r'[^\w\s]', '', user_message.lower()).strip()
    if stripped in greeting_words or stripped.startswith(("hi ", "hey ", "hello ")):
        return {
            "response": (
                "Hello! I'm Muhammad Junayed's AI assistant. "
                "I can tell you about his projects, skills, research, and experience. "
                "What would you like to know?"
            ),
            "sources": [],
        }
 
    # Retrieve relevant context from vector store (5 chunks for better coverage)
    results = vector_query(user_message, n_results=5)
 
    # Build context from retrieved chunks (no section labels - they leak into responses)
    context_parts = []
    for r in results:
        text = r.get("text", "").strip()
        if text:
            context_parts.append(text)
    
    context = "\n\n".join(context_parts) if context_parts else "No specific context available."
 
    sources = [r["metadata"].get("source", "profile") for r in results if r.get("metadata")]
 
    # Clean context to remove metadata before sending to LLM or fallback
    clean_context = _clean_context_for_llm(context)
 
    # If no HF API token, return a fallback response
    if not settings.HF_API_TOKEN:
        logger.warning(
            "HF_API_TOKEN is not set - using fallback response. "
            "Set HF_API_TOKEN environment variable to enable AI-generated responses."
        )
        return {
            "response": _generate_fallback_response(user_message, clean_context),
            "sources": list(set(sources)),
        }
 
    # Quick off-topic detection for clearly irrelevant questions (saves API calls)
    message_lower = user_message.lower()
    if any(kw in message_lower for kw in OFF_TOPIC_KEYWORDS):
        return {
            "response": (
                "I'm specifically designed to answer questions about Muhammad Junayed — "
                "his skills, projects, research, experience, and background. "
                "I can't help with general questions outside his portfolio. "
                "What would you like to know about him?"
            ),
            "sources": [],
        }
 
    # Call HuggingFace Inference API
    prompt = _build_prompt(user_message, clean_context)
    try:
        response_text = await _call_hf_api(prompt)
        logger.info("Successfully generated response via HF API for query: %s", user_message[:80])
    except Exception as e:
        logger.warning(
            "HF API call failed (attempt 1), retrying in 2 seconds. Error: %s | Query: %s",
            str(e),
            user_message[:80],
        )
        # Retry once after a 2-second delay for transient failures.
        # NOTE: Worst-case latency budget: _call_hf_api has internal 503 retry with 5s sleep,
        # so a single request path can take up to: 45s (first timeout) + 2s (sleep) +
        # 20s (retry timeout) = ~67s before falling back. With the 503 internal retry,
        # this could reach 45+5+45 + 2 + 20+5+20 = ~142s in the absolute worst case.
        # A full circuit breaker is not implemented, but the shorter retry timeout (20s)
        # limits the added latency from the retry attempt.
        try:
            await asyncio.sleep(2)
            response_text = await _call_hf_api(prompt, timeout=20.0)
            logger.info("Successfully generated response via HF API on retry for query: %s", user_message[:80])
        except Exception as retry_e:
            logger.error(
                "HF API retry also failed, using fallback. Error: %s | Model: %s | Query: %s",
                str(retry_e),
                settings.HF_MODEL_ID,
                user_message[:80],
            )
            response_text = _generate_fallback_response(user_message, clean_context)
 
    return {
        "response": response_text,
        "sources": list(set(sources)),
    }
 
 
def _build_prompt(user_message: str, context: str) -> str:
    system = SYSTEM_PROMPT.format(context=context)
    return f"<s>[INST] {system}\n\nUser question: {user_message} [/INST]"
 
 
def _clean_response(text: str) -> str:
    """Post-process LLM response to remove artifacts and ensure quality."""
    if not text:
        return "I apologize, but I could not generate a proper response. Please try asking your question in a different way."
 
    # Remove instruction artifacts
    artifacts = ["[INST]", "[/INST]", "</s>", "<s>", "<<SYS>>", "<</SYS>>", "<|", "|>"]
    for artifact in artifacts:
        text = text.replace(artifact, "")
 
    # Remove cases where the model echoes back the system prompt
    # Look for the system prompt signature and remove everything before the actual answer
    system_prompt_markers = [
        "You are a friendly, conversational AI assistant",
        "You are Muhammad Junayed's portfolio assistant",
        "Context from knowledge base:",
        "User question:",
        "Guidelines:",
        "Rules:",
    ]
    for marker in system_prompt_markers:
        if marker in text:
            # Find the last occurrence and take everything after it
            idx = text.rfind(marker)
            # Find the end of this echoed section (next newline after some content)
            remaining = text[idx:]
            newline_idx = remaining.find("\n\n")
            if newline_idx > 0:
                text = remaining[newline_idx:].strip()
            else:
                text = ""
 
    # Remove ANY line matching "Label: value" metadata pattern (with or without bullet)
    # This catches Document ID, Authors, Conference, DOI, Publisher, Pages, etc.
    metadata_labels = (
        r"Document ID|Authors?|Conference|Publisher|DOI link|DOI|Pages?|"
        r"Code repository|Publication date|Conference abbreviation|"
        r"Conference location|Team|Venue|Workshop abbreviation|"
        r"Official paper link|Muhammad Junayed's author position|"
        r"Employment type|Duration|Organization|Role|"
        r"Target classes|Target|Dataset|Common abbreviation|Common|"
        r"Training type|Evaluation|Main|Shared|Exact|Individual|"
        r"Comparison|Per-|Error"
    )
    # Remove lines with metadata labels (with or without bullet prefix)
    text = re.sub(
        r'^[\s•◦▪\-*]*(?:' + metadata_labels + r')[^:\n]{0,40}:\s*[^\n]*\n?',
        '', text, flags=re.MULTILINE | re.IGNORECASE
    )
 
    # Remove section headers appearing alone on a line
    section_headers = r"Research Problem|Approach|Dataset|Images|Keywords|Key Contributions|Methodology|Results|Conclusion"
    text = re.sub(
        r'^\s*(?:' + section_headers + r')\s*:?\s*$',
        '', text, flags=re.MULTILINE | re.IGNORECASE
    )
 
    # Remove "Sources:" lines and source filenames
    text = re.sub(r'^[\s•◦▪\-*]*Sources?:?\s*[^\n]*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'Muhammad_Junayed_RAG_Knowledge_Base\.pdf', '', text)
 
    # Remove any remaining bullet points (lines starting with bullet chars)
    # The LLM should NEVER output bullet points - all such lines are metadata artifacts
    text = re.sub(r'^\s*[•◦▪]\s*[^\n]*$', '', text, flags=re.MULTILINE)
    # Remove dashes/asterisks used as bullets ONLY when the line also looks like metadata
    # (contains a colon pattern or is a short label-like item <= 60 chars).
    # This avoids stripping legitimate LLM prose that starts with "- " for emphasis.
    text = re.sub(
        r'^\s*[-*]\s+(?=[^\n]{0,60}:[^\n]*$)[^\n]*$',
        '', text, flags=re.MULTILINE
    )
    # Also remove short dash-bullet lines (<=60 chars total, no sentence-ending punctuation)
    # which are likely list items rather than prose
    text = re.sub(
        r'^\s*[-*]\s+[^\n.!?]{0,55}$',
        '', text, flags=re.MULTILINE
    )
 
    # Remove "[Section: ...]" if still present
    text = re.sub(r'\[Section:[^\]]*\]', '', text)
    # Remove "Information Not Provided" blocks
    text = re.sub(r'Information Not Provided[^\n]*', '', text, flags=re.IGNORECASE)
    # Remove standalone "Images" artifact
    text = re.sub(r'^\s*Images\s*$', '', text, flags=re.MULTILINE)
    # Remove "Keywords ..." lines
    text = re.sub(r'Keywords\s+[\w;,\s]+\.?\s*', '', text)
    # Remove standalone URLs
    text = re.sub(r'^\s*https?://[^\s]+\s*$', '', text, flags=re.MULTILINE)
 
    # Collapse multiple newlines into max 2
    text = re.sub(r'\n{3,}', '\n\n', text)
 
    # Strip leading/trailing whitespace
    text = text.strip()
 
    # Remove repeated sentences (keep only first occurrence)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    seen = set()
    unique_sentences = []
    for sentence in sentences:
        normalized = sentence.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_sentences.append(sentence.strip())
    text = " ".join(unique_sentences)
 
    # Truncate to max 1000 characters at a sentence boundary
    if len(text) > 1000:
        truncated = text[:1000]
        # Find the last sentence boundary
        last_boundary = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
            truncated.rfind(".\n"),
        )
        if last_boundary > 200:
            text = truncated[:last_boundary + 1]
        else:
            # Try to cut at a period at the end
            last_period = truncated.rfind(".")
            if last_period > 200:
                text = truncated[:last_period + 1]
            else:
                text = truncated.strip()
 
    # If response is empty after cleaning, return graceful fallback
    if not text.strip():
        return "I apologize, but I could not generate a proper response. Please try asking your question in a different way."
 
    return text.strip()
 
 
async def _call_hf_api(prompt: str, timeout: float = 45.0) -> str:
    url = f"https://api-inference.huggingface.co/models/{settings.HF_MODEL_ID}"
    headers = {"Authorization": f"Bearer {settings.HF_API_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 300,
            "temperature": 0.4,
            "return_full_text": False,
        },
    }
 
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
 
        # Handle rate limiting
        if response.status_code == 429:
            raise Exception(
                "Rate limited by HuggingFace API. Please wait a moment and try again."
            )
 
        # Handle model loading (503) with retry
        if response.status_code == 503:
            logger.warning("Model is loading (503), retrying in 5 seconds...")
            await asyncio.sleep(5)
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                error_detail = response.text[:300]
                logger.error(
                    "HF API retry failed with status %d: %s (model: %s)",
                    response.status_code,
                    error_detail,
                    settings.HF_MODEL_ID,
                )
                response.raise_for_status()
        elif response.status_code != 200:
            # Check if JSON error mentions "loading"
            try:
                error_json = response.json()
                error_msg = str(error_json.get("error", ""))
                if "loading" in error_msg.lower():
                    logger.warning("Model is loading (from error message), retrying in 5 seconds...")
                    await asyncio.sleep(5)
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code != 200:
                        error_detail = response.text[:300]
                        logger.error(
                            "HF API retry failed with status %d: %s (model: %s)",
                            response.status_code,
                            error_detail,
                            settings.HF_MODEL_ID,
                        )
                        response.raise_for_status()
                else:
                    error_detail = response.text[:300]
                    logger.error(
                        "HF API returned status %d: %s (model: %s)",
                        response.status_code,
                        error_detail,
                        settings.HF_MODEL_ID,
                    )
                    response.raise_for_status()
            except (ValueError, KeyError):
                error_detail = response.text[:300]
                logger.error(
                    "HF API returned status %d: %s (model: %s)",
                    response.status_code,
                    error_detail,
                    settings.HF_MODEL_ID,
                )
                response.raise_for_status()
 
        result = response.json()
 
    if isinstance(result, list) and len(result) > 0:
        generated = result[0].get("generated_text", "").strip()
        return _clean_response(generated)
    logger.warning("HF API returned unexpected response format: %s", str(result)[:200])
    return "I apologize, but I could not generate a response at this time."
 
 
def _extract_urls(text: str) -> dict:
    """Extract labeled URLs from context text."""
    urls = {}
    # Match patterns like "LinkedIn - URL" or "GitHub - URL"
    url_patterns = re.findall(
        r'(\w[\w\s]*?)\s*[-:]\s*(https?://[^\s,]+)', text
    )
    for label, url in url_patterns:
        urls[label.strip().lower()] = url.strip().rstrip(",.")
    # Also find standalone URLs
    standalone = re.findall(r'https?://[^\s,]+', text)
    for url in standalone:
        url_clean = url.strip().rstrip(",.")
        if "linkedin" in url_clean.lower() and "linkedin" not in urls:
            urls["linkedin"] = url_clean
        elif "github" in url_clean.lower() and "github" not in urls:
            urls["github"] = url_clean
        elif "kaggle" in url_clean.lower() and "kaggle" not in urls:
            urls["kaggle"] = url_clean
        elif "scholar" in url_clean.lower() and "scholar" not in urls:
            urls["scholar"] = url_clean
    return urls
 
 
def _extract_email(text: str) -> Optional[str]:
    """Extract email address from context text."""
    match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
    return match.group(0) if match else None
 
 
def _generate_fallback_response(user_message: str, context: str) -> str:
    """Generate a structured, intelligent response from retrieved context when HF API is not available."""
    message_lower = user_message.lower().strip()
 
    # Handle greetings ONLY when the entire message is a greeting (not part of a longer question)
    greeting_words = {"hello", "hi", "hey", "greetings", "howdy", "hola", "yo", "sup", "good morning", "good evening", "good afternoon"}
    # Strip punctuation for comparison
    stripped_message = re.sub(r'[^\w\s]', '', message_lower).strip()
    if stripped_message in greeting_words or stripped_message.startswith(("hi ", "hey ", "hello ")):
        return (
            "Hello! I'm Muhammad Junayed's AI assistant. "
            "I can tell you about his projects, skills, research, and experience. "
            "What would you like to know?"
        )
 
    # Detect off-topic questions
    if _is_off_topic(user_message):
        return (
            "I'm specifically designed to answer questions about Muhammad Junayed — "
            "his skills, projects, research, experience, and background. "
            "I can't help with general questions outside his portfolio. "
            "What would you like to know about him?"
        )
 
    # If no meaningful context, check keyword-based answers first before giving generic response
    # Handle common keyword-based questions regardless of vector store results
 
    # LinkedIn requests
    if "linkedin" in message_lower:
        urls = _extract_urls(context) if context and context != "No specific context available." else {}
        if "linkedin" in urls:
            return f"Here is Muhammad Junayed's LinkedIn profile: {urls['linkedin']}"
        return (
            "Muhammad Junayed's LinkedIn profile is: "
            "https://www.linkedin.com/in/muhammad-junayed-ete20/"
        )
 
    # GitHub requests
    if "github" in message_lower:
        urls = _extract_urls(context) if context and context != "No specific context available." else {}
        if "github" in urls:
            return f"Here is Muhammad Junayed's GitHub profile: {urls['github']}"
        return (
            "Muhammad Junayed's GitHub profile is: "
            "https://github.com/MD-Junayed000"
        )
 
    # Kaggle requests
    if "kaggle" in message_lower:
        urls = _extract_urls(context) if context and context != "No specific context available." else {}
        if "kaggle" in urls:
            return f"Here is Muhammad Junayed's Kaggle profile: {urls['kaggle']}"
        return (
            "Muhammad Junayed's Kaggle profile is: "
            "https://www.kaggle.com/muhammedjunayed"
        )
 
    # Google Scholar requests
    if "scholar" in message_lower or "google scholar" in message_lower:
        urls = _extract_urls(context) if context and context != "No specific context available." else {}
        if "scholar" in urls:
            return f"Here is Muhammad Junayed's Google Scholar profile: {urls['scholar']}"
        return (
            "Muhammad Junayed's Google Scholar profile is: "
            "https://scholar.google.com/citations?user=wObQzNsAAAAJ&hl=en"
        )
 
    # Address/location requests
    if any(word in message_lower for word in ["address", "location", "live", "based", "home"]) and not any(w in message_lower for w in ["work", "job", "company", "employ"]):
        # Check context for address info
        if context and context != "No specific context available.":
            address_match = re.search(r'address[:\s-]+([^\n,]+)', context, re.IGNORECASE)
            if address_match:
                return f"Muhammad Junayed's address is: {address_match.group(1).strip()}"
        return (
            "Muhammad Junayed is based in Bangladesh. He is a final-year ETE student at "
            "Chittagong University of Engineering & Technology (CUET)."
        )
 
    # Phone requests
    if any(word in message_lower for word in ["phone", "call", "number", "mobile"]):
        if context and context != "No specific context available.":
            phone_match = re.search(r'(?:phone|mobile|contact)[:\s-]+([+\d\s()-]+)', context, re.IGNORECASE)
            if phone_match:
                return f"Muhammad Junayed's phone number is: {phone_match.group(1).strip()}"
        return (
            "For contact information, please use the contact form on this website or "
            "reach out via email at mdjunayed573@gmail.com"
        )
 
    # Email/contact requests
    if any(word in message_lower for word in ["email", "mail", "contact", "reach", "how to contact"]):
        return (
            "You can contact Muhammad Junayed via:\n"
            "- Email: mdjunayed573@gmail.com\n"
            "- LinkedIn: https://www.linkedin.com/in/muhammad-junayed-ete20/\n"
            "- GitHub: https://github.com/MD-Junayed000\n\n"
            "Or use the contact form on this website!"
        )
 
    # Achievement/award requests
    if any(word in message_lower for word in ["achievement", "award", "accomplish", "honor", "recognition"]):
        if context and context != "No specific context available.":
            # Try to find achievement-related content in context
            achievement_sentences = []
            for sentence in re.split(r'(?<=[.!?])\s+', context):
                if any(kw in sentence.lower() for kw in ["award", "achiev", "honor", "recogni", "certif", "winner", "first", "best"]):
                    achievement_sentences.append(sentence.strip())
            if achievement_sentences:
                intro = "Here are some of Muhammad Junayed's achievements:\n\n"
                points = [f"- {s}" for s in achievement_sentences[:5]]
                return intro + "\n".join(points)
        return (
            "Muhammad Junayed's notable achievements include:\n"
            "- Published research papers at IEEE (ICAEEE 2024) and ACL workshop (BEA 2025)\n"
            "- B.Sc. thesis on hallucination detection/mitigation in LLMs\n"
            "- Multiple ML/AI projects including healthcare chatbot and industrial defect recognition\n\n"
            "Ask about his research or projects for more details!"
        )
 
    # Thesis requests
    if any(word in message_lower for word in ["thesis", "research topic", "dissertation"]):
        return (
            "Muhammad Junayed's undergraduate thesis is titled 'Closing the Loop on RAG Hallucinations: "
            "Inference-Time Control via Dual Residual-Stream and FFN Activation Probes.' "
            "It investigates methods for detecting and mitigating hallucinations in large language models "
            "during inference. His supervisor is Priyonti Paul Tumpa, Assistant Professor at CUET's ETE department. "
            "The thesis is currently ongoing."
        )
 
    # Education/CGPA requests
    if any(word in message_lower for word in ["cgpa", "gpa", "grade", "education", "degree", "study"]):
        return (
            "Muhammad Junayed is pursuing a B.Sc. in Electronics and Telecommunication Engineering "
            "at Chittagong University of Engineering and Technology (CUET), Bangladesh. "
            "He started in March 2022 and is currently in his final year."
        )
 
    # Work/experience requests
    if any(word in message_lower for word in ["work", "job", "employ", "intern", "company", "experience"]) and not any(w in message_lower for w in ["project", "built", "research", "paper", "publication"]):
        return (
            "Muhammad Junayed has worked at:\n"
            "- Software Engineer Intern at Poridhi.io (cloud-native infrastructure)\n"
            "- Industrial Trainee at Brain Station 23 PLC (software development)\n\n"
            "He gained experience in backend engineering, cloud computing, and production software systems."
        )
 
    # Language requests
    if any(word in message_lower for word in ["language", "speak", "fluent", "bangla", "bengali", "english"]) and not any(w in message_lower for w in ["programming", "code", "python", "javascript"]):
        return (
            "Muhammad Junayed speaks:\n"
            "- Bangla (native language)\n"
            "- English (professional proficiency)"
        )
 
    # Coursework requests
    if any(word in message_lower for word in ["course", "coursework", "subject", "class"]):
        return (
            "Muhammad Junayed's relevant coursework includes:\n"
            "- Electronics & Communication: Digital Systems, VLSI, Communication Theory\n"
            "- Signal Processing: DSP, Control Systems\n"
            "- Computing: Data Structures, OOP, Computer Architecture\n"
            "- Mathematics: Linear Algebra, Probability, Numerical Methods"
        )
 
    # If no meaningful context available after keyword checks, return generic response
    if not context or context == "No specific context available.":
        return (
            "I'm Muhammad Junayed's AI portfolio assistant. "
            "I can help you learn about his projects, skills, research, and background. "
            "Please ask me something specific!"
        )
 
    # Extract structured information from context
    urls = _extract_urls(context)
    email = _extract_email(context)
 
    # For general questions, parse context into a structured answer
    return _build_structured_answer(message_lower, context)
 
 
def _build_structured_answer(question: str, context: str) -> str:
    """Build a structured, readable answer from context based on the question type."""
    # Split context into individual chunks for analysis
    chunks = [c.strip() for c in context.split("\n\n") if c.strip()]
 
    # Determine question category and format accordingly
    if any(word in question for word in ["skill", "tech", "proficient", "know", "stack"]):
        return _format_skills_answer(chunks)
    elif any(word in question for word in ["project", "built", "made", "portfolio", "work"]):
        return _format_projects_answer(chunks)
    elif any(word in question for word in ["research", "paper", "publication", "thesis"]):
        return _format_research_answer(chunks)
    elif any(word in question for word in ["achievement", "award", "accomplish", "honor", "recognition"]):
        return _format_achievements_answer(chunks)
    elif any(word in question for word in ["who", "about", "tell me", "introduce", "background"]):
        return _format_about_answer(chunks)
    elif any(word in question for word in ["experience", "job", "intern", "company"]):
        return _format_experience_answer(chunks)
    else:
        # General question: present the most relevant context clearly
        return _format_general_answer(chunks)
 
 
def _format_skills_answer(chunks: list) -> str:
    """Format a skills-focused answer from context chunks."""
    skill_info = []
    for chunk in chunks:
        if any(kw in chunk.lower() for kw in ["skill", "proficient", "expertise", "uses", "include"]):
            skill_info.append(chunk)
 
    if skill_info:
        intro = "Here are Muhammad Junayed's technical skills:\n\n"
        # Extract skill mentions and present them
        combined = " ".join(skill_info)
        sentences = [s.strip() for s in re.split(r'(?<=[.!])\s+', combined) if s.strip()]
        points = [f"- {s}" for s in sentences[:6]]
        return intro + "\n".join(points)
 
    # Fallback: use whatever context we have
    return _format_general_answer(chunks)
 
 
def _format_projects_answer(chunks: list) -> str:
    """Format a projects-focused answer from context chunks."""
    project_info = []
    for chunk in chunks:
        if any(kw in chunk.lower() for kw in ["project", "built", "developed", "arobot", "uber", "bistro"]):
            project_info.append(chunk)
 
    if project_info:
        intro = "Here are some of Muhammad Junayed's notable projects:\n\n"
        combined = " ".join(project_info)
        # Try to find individual project mentions
        projects = re.findall(r'([A-Z][\w\s-]+?)\s*\(([^)]+)\)', combined)
        if projects:
            points = [f"- **{name.strip()}**: {desc.strip()}" for name, desc in projects[:6]]
            return intro + "\n".join(points)
        # Fallback: present as sentences
        sentences = [s.strip() for s in re.split(r'(?<=[.!])\s+', combined) if s.strip()]
        points = [f"- {s}" for s in sentences[:6]]
        return intro + "\n".join(points)
 
    return _format_general_answer(chunks)
 
 
def _format_research_answer(chunks: list) -> str:
    """Format a research-focused answer from context chunks."""
    research_info = []
    for chunk in chunks:
        if any(kw in chunk.lower() for kw in ["research", "paper", "thesis", "ieee", "acl", "conference"]):
            research_info.append(chunk)
 
    if research_info:
        intro = "Here is Muhammad Junayed's research work:\n\n"
        combined = " ".join(research_info)
        sentences = [s.strip() for s in re.split(r'(?<=[.!])\s+', combined) if s.strip()]
        points = [f"- {s}" for s in sentences[:5]]
        return intro + "\n".join(points)
 
    return _format_general_answer(chunks)
 
 
def _format_achievements_answer(chunks: list) -> str:
    """Format an achievements-focused answer from context chunks."""
    achievement_info = []
    for chunk in chunks:
        if any(kw in chunk.lower() for kw in ["award", "achiev", "honor", "recogni", "certif", "winner", "first", "best"]):
            achievement_info.append(chunk)
 
    if achievement_info:
        intro = "Here are some of Muhammad Junayed's achievements:\n\n"
        combined = " ".join(achievement_info)
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', combined) if s.strip()]
        points = [f"- {s}" for s in sentences[:6]]
        return intro + "\n".join(points)
 
    return _format_general_answer(chunks)
 
 
def _format_about_answer(chunks: list) -> str:
    """Format an about/introduction answer from context chunks."""
    # Prioritize chunks about the person
    about_info = []
    for chunk in chunks:
        if any(kw in chunk.lower() for kw in ["muhammad junayed", "student", "specializ", "enthusiast"]):
            about_info.append(chunk)
 
    if about_info:
        # Use the first relevant chunk as a direct intro, clean it up
        intro = about_info[0]
        # Truncate at sentence boundary
        sentences = [s.strip() for s in re.split(r'(?<=[.!])\s+', intro) if s.strip()]
        return " ".join(sentences[:4])
 
    return _format_general_answer(chunks)
 
 
def _format_experience_answer(chunks: list) -> str:
    """Format an experience answer."""
    exp_info = []
    for chunk in chunks:
        if any(kw in chunk.lower() for kw in ["experience", "work", "intern", "company", "role"]):
            exp_info.append(chunk)
 
    if exp_info:
        combined = " ".join(exp_info)
        sentences = [s.strip() for s in re.split(r'(?<=[.!])\s+', combined) if s.strip()]
        return " ".join(sentences[:5])
 
    # If no specific experience info found, say so
    return (
        "I don't have detailed work experience information in my current knowledge base. "
        "Muhammad Junayed is a final-year ETE student at CUET focused on AI engineering, "
        "computer vision, and cloud-native ML systems. Feel free to ask about his projects or skills!"
    )
 
 
def _format_general_answer(chunks: list) -> str:
    """Format a general answer from context, presenting it as readable sentences."""
    combined = " ".join(chunks)
    # Clean up excessive whitespace
    combined = re.sub(r'\s+', ' ', combined).strip()
 
    # Truncate at sentence boundary
    if len(combined) > 600:
        truncated = combined[:600]
        last_period = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
        )
        if last_period > 150:
            combined = truncated[:last_period + 1]
        else:
            last_space = truncated.rfind(" ")
            if last_space > 150:
                combined = truncated[:last_space] + "."
            else:
                combined = truncated + "..."
 
    return combined
