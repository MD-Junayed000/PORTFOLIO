from __future__ import annotations

import asyncio
import logging
import re
from difflib import SequenceMatcher
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

from config import settings
from services.vector_store import (
    get_by_entity_type,
    get_by_section_numbers,
    query as vector_query,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public prompt and response constants
# ---------------------------------------------------------------------------

OFF_TOPIC_RESPONSE = (
    "I can only answer questions about Muhammad Junayed's portfolio "
    "and background."
)

NO_INFORMATION_RESPONSE = (
    "I don't have that specific information in the available portfolio "
    "knowledge base."
)

GREETING_WORDS = {
    "hello",
    "hi",
    "hey",
    "greetings",
    "howdy",
    "hola",
    "yo",
    "sup",
    "good morning",
    "good afternoon",
    "good evening",
}

OFF_TOPIC_KEYWORDS = (
    "weather",
    "sports",
    "game score",
    "movie",
    "recipe",
    "cook",
    "joke",
    "funny",
    "news today",
    "stock",
    "crypto",
    "bitcoin",
    "president",
    "politics",
    "war",
    "religion",
    "god",
    "meaning of life",
    "what time",
    "calculate",
    "translate",
    "write code",
    "debug",
    "fix my",
)

SYSTEM_PROMPT = """You are Muhammad Junayed's portfolio assistant.

Answer the user's question using ONLY the retrieved portfolio context.

Core rules:
- Answer the requested topic only. Do not mix projects, research, education, or work experience unless the question asks for more than one category.
- Convert the retrieved records into natural prose. Never dump raw PDF text, page numbers, section paths, chunk metadata, or internal Document IDs.
- Do not begin with labels such as "Professional Profile", "Selected Projects", "Research Problem", "Approach", or "Outcome".
- Preserve factual qualifiers such as "ongoing", "approximate", "up to", and "as reported".
- Do not invent missing measurements, responsibilities, deployment claims, results, or publication details.
- For a broad summary, synthesize the category instead of copying one retrieved chunk.
- For a named project or named publication, discuss only that item and include its purpose, main technologies or method, implementation, and outcome when present.
- Use complete, readable sentences. Avoid bullet points unless the user explicitly asks for a list.
- If the context does not contain the answer, say that the information is not available.

Task-specific instruction:
{intent_instruction}

Retrieved context:
{context}
"""


# ---------------------------------------------------------------------------
# Intent and entity definitions
# ---------------------------------------------------------------------------

INTENT_PROFILE = "profile"
INTENT_RESEARCH_SUMMARY = "research_summary"
INTENT_RESEARCH_SPECIFIC = "research_specific"
INTENT_PROJECT_SUMMARY = "project_summary"
INTENT_PROJECT_SPECIFIC = "project_specific"
INTENT_CGPA = "cgpa"
INTENT_EDUCATION = "education"
INTENT_EXPERIENCE = "experience"
INTENT_SKILLS = "skills"
INTENT_THESIS = "thesis"
INTENT_AWARDS = "awards"
INTENT_CONTACT = "contact"
INTENT_LOCATION = "location"
INTENT_LANGUAGES = "languages"
INTENT_COURSEWORK = "coursework"
INTENT_EXTRACURRICULAR = "extracurricular"
INTENT_GENERAL = "general"


INTENT_INSTRUCTIONS = {
    INTENT_PROFILE: (
        "Give a concise professional introduction. Explain who Junayed is, "
        "what he studies, and the main areas in which he works. Use 3-4 sentences."
    ),
    INTENT_RESEARCH_SUMMARY: (
        "Summarize his research work, not his software projects. Mention his "
        "ongoing undergraduate thesis and the three conference publications, "
        "including each publication's topic or method and any verified result. "
        "Use 4-6 sentences."
    ),
    INTENT_RESEARCH_SPECIFIC: (
        "Explain only the named research work. Include the problem, dataset when "
        "available, method, verified result or finding, and publication details "
        "when directly relevant. Use 4-6 sentences."
    ),
    INTENT_PROJECT_SUMMARY: (
        "Give a portfolio-level summary of his selected projects. Group them by "
        "area, mention representative named projects, and describe the breadth "
        "of his engineering work. Do not describe a research publication as a "
        "project. Use 4-6 sentences."
    ),
    INTENT_PROJECT_SPECIFIC: (
        "Explain only the named project in detail. Cover its purpose, major "
        "technologies, architecture or implementation, main capabilities, and "
        "documented outcome. Do not include unrelated projects. Use 4-6 sentences."
    ),
    INTENT_CGPA: (
        "Answer the CGPA question directly, including the scale and coverage "
        "semester when available. Use 1-2 sentences."
    ),
    INTENT_EDUCATION: (
        "Summarize his education accurately, including degree, institution, "
        "study period, and verified academic results. Use 3-4 sentences."
    ),
    INTENT_EXPERIENCE: (
        "Summarize only his work and training experience. Include organization, "
        "role, duration, and documented focus. Use 3-4 sentences."
    ),
    INTENT_SKILLS: (
        "Summarize his technical skills by meaningful categories. Mention only "
        "technologies present in the context. Use concise prose unless a list was requested."
    ),
    INTENT_THESIS: (
        "Explain his ongoing undergraduate thesis: title, problem, proposed "
        "direction, supervisor, and status. Do not claim completed results. "
        "Use 4-5 sentences."
    ),
    INTENT_AWARDS: (
        "Summarize his verified awards and competitive achievements. Preserve "
        "rankings and qualifiers exactly. Use 3-5 sentences."
    ),
    INTENT_CONTACT: (
        "Provide only the requested public contact or profile information in a "
        "natural sentence."
    ),
    INTENT_LOCATION: (
        "State only the documented general location. If the user asks for a "
        "home or street address, explain that the portfolio provides only the "
        "general location and does not contain an exact residential address."
    ),
    INTENT_LANGUAGES: (
        "State his documented languages and proficiency levels accurately."
    ),
    INTENT_COURSEWORK: (
        "Summarize the relevant coursework by academic category. Mention only "
        "courses present in the context."
    ),
    INTENT_EXTRACURRICULAR: (
        "Summarize his extracurricular activities and leadership roles, including "
        "documented responsibilities and dates."
    ),
    INTENT_GENERAL: (
        "Answer the question directly from the most relevant retrieved context "
        "without adding unrelated portfolio categories."
    ),
}


# Exact section mappings from the canonical PDF.
INTENT_SECTION_NUMBERS = {
    INTENT_PROFILE: ("1", "2"),
    INTENT_CGPA: ("3.1",),
    INTENT_EDUCATION: ("3.1", "3.2", "3.3"),
    INTENT_THESIS: ("4.1", "4.2", "4.3"),
    INTENT_EXPERIENCE: ("5.1", "5.2"),
    INTENT_RESEARCH_SUMMARY: ("4.1", "4.2", "4.3", "9.1", "9.2", "9.3"),
    INTENT_CONTACT: ("2",),
    INTENT_LOCATION: ("2",),
    INTENT_LANGUAGES: ("13.1", "13.2"),
    INTENT_COURSEWORK: ("8.1", "8.2", "8.3", "8.4"),
    INTENT_EXTRACURRICULAR: ("11.1", "11.2", "11.3"),
}


PROJECT_ALIASES: Dict[str, Tuple[str, ...]] = {
    "10.1": (
        "arobot",
        "aro bot",
        "agentic multimodal rag chatbot",
        "medical rag chatbot",
    ),
    "10.2": (
        "uber fare",
        "uber fare prediction",
        "mlops orchestration",
        "mlops uber fare",
    ),
    "10.3": (
        "bangladesh medicine scraper",
        "medicine scraper",
        "medex scraper",
    ),
    "10.4": (
        "nodescape",
        "graph algorithm visualizer",
        "graph type predictor",
    ),
    "10.5": (
        "bistro-92",
        "bistro 92",
        "bistro",
        "bisto",
        "restaurant management system",
    ),
    "10.6": (
        "smart attendance",
        "face recognition and rfid",
        "rfid smart attendance",
    ),
    "10.7": (
        "credit card fraud",
        "fraud detection",
    ),
    "10.8": (
        "eeg alcoholism",
        "alcoholism detection",
        "eeg data analysis",
    ),
    "10.9": (
        "flask celery aws",
        "flask asynchronous task",
        "async-tasks-main",
        "aws pulumi task",
    ),
    "10.10": (
        "node.js asynchronous task",
        "node js asynchronous task",
        "node async task",
        "async_task_node",
    ),
    "10.11": (
        "rickshawx",
        "rickshaw x",
        "smart mobility for cuet",
    ),
    "10.12": (
        "aroma pharmacy",
        "pharmacy e-commerce",
        "pharmacy ecommerce",
    ),
    "10.13": (
        "home power automation",
        "power automation",
        "prepaid energy monitoring",
    ),
    "10.14": (
        "databench",
        "tabular qa",
        "question answering system",
        "semeval 2024 task 8",
    ),
}


RESEARCH_ALIASES: Dict[str, Tuple[str, ...]] = {
    "9.1": (
        "wafer",
        "wafer map",
        "silicon wafer",
        "defect recognition",
        "icaeee",
        "cnn wafer",
    ),
    "9.2": (
        "bea 2025",
        "smollab",
        "ai-powered tutors",
        "ai powered tutors",
        "pedagogical evaluation",
        "mrbench",
        "tutor identity",
    ),
    "9.3": (
        "breast ultrasound",
        "busi",
        "cancer stages",
        "vision transformer paper",
        "spicscon",
    ),
}


@dataclass(frozen=True)
class IntentResult:
    intent: str
    section_number: Optional[str] = None
    entity_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Text matching and intent detection
# ---------------------------------------------------------------------------

def _repair_pdf_artifacts(text: str) -> str:
    """Repair common spacing artifacts introduced by PDF extraction."""
    if not text:
        return ""

    text = (
        text.replace("\u00ad", "")
        .replace("\ufffe", "-")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    text = re.sub(r"[\u2010-\u2015]", "-", text)

    # Repair only one-sided spacing around a compound hyphen.
    # "Residual -Stream" -> "Residual-Stream"
    # "Graph- Type" -> "Graph-Type"
    # Preserve intentional separators such as "NodeScape - Graph".
    text = re.sub(
        r"(?<=[A-Za-z0-9])\s+-(?=[A-Za-z0-9])",
        "-",
        text,
    )
    text = re.sub(
        r"(?<=[A-Za-z0-9])-\s+(?=[A-Za-z0-9])",
        "-",
        text,
    )

    # Remove spaces before punctuation without joining normal words.
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def _normalize_text(text: str) -> str:
    text = _repair_pdf_artifacts(text).lower().replace("_", " ")
    text = re.sub(r"[^a-z0-9+#.\-\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _contains_term(text: str, term: str) -> bool:
    """Match a whole word or phrase without substring errors."""
    normalized_text = _normalize_text(text)
    normalized_term = _normalize_text(term)
    if not normalized_term:
        return False
    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(normalized_term).replace(r"\ ", r"\s+")
        + r"(?![a-z0-9])"
    )
    return re.search(pattern, normalized_text, flags=re.IGNORECASE) is not None


def _find_alias(
    message: str,
    aliases: Dict[str, Tuple[str, ...]],
    allow_fuzzy: bool = True,
) -> Optional[Tuple[str, str]]:
    """Return an exact alias match, then tolerate one small user typo."""
    candidates: List[Tuple[int, str, str]] = []
    for section_number, names in aliases.items():
        for name in names:
            if _contains_term(message, name):
                candidates.append((len(name), section_number, name))

    if candidates:
        _, section_number, matched_name = max(
            candidates,
            key=lambda item: item[0],
        )
        return section_number, matched_name

    if not allow_fuzzy:
        return None

    ignored = {
        "tell", "about", "this", "that", "project", "paper", "research",
        "details", "detail", "please", "explain", "more", "his", "the",
        "what", "does", "work", "with", "uses", "used",
    }
    message_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", _normalize_text(message))
        if len(token) >= 5 and token not in ignored
    ]

    fuzzy_candidates: List[Tuple[float, str, str]] = []
    for section_number, names in aliases.items():
        for name in names:
            alias_tokens = [
                token
                for token in re.findall(r"[a-z0-9]+", _normalize_text(name))
                if len(token) >= 5 and token not in ignored
            ]
            for message_token in message_tokens:
                for alias_token in alias_tokens:
                    ratio = SequenceMatcher(
                        None,
                        message_token,
                        alias_token,
                    ).ratio()
                    if ratio >= 0.84:
                        fuzzy_candidates.append(
                            (ratio, section_number, name)
                        )

    if not fuzzy_candidates:
        return None

    _, section_number, matched_name = max(
        fuzzy_candidates,
        key=lambda item: item[0],
    )
    return section_number, matched_name


def _last_referenced_entity(
    conversation_history: Optional[Sequence[Dict[str, Any]]],
) -> Optional[Tuple[str, str, str]]:
    """Resolve a project or publication mentioned in recent conversation history."""
    if not conversation_history:
        return None

    for item in reversed(conversation_history[-8:]):
        content = str(item.get("content") or item.get("message") or "")
        project = _find_alias(content, PROJECT_ALIASES)
        if project:
            return INTENT_PROJECT_SPECIFIC, project[0], project[1]

        research = _find_alias(content, RESEARCH_ALIASES)
        if research:
            return INTENT_RESEARCH_SPECIFIC, research[0], research[1]

    return None


def _resolve_follow_up(
    message: str,
    conversation_history: Optional[Sequence[Dict[str, Any]]],
) -> str:
    normalized = _normalize_text(message)
    follow_up_markers = (
        "this project",
        "that project",
        "it",
        "this one",
        "that one",
        "tell me more",
        "more details",
        "how does it work",
        "what technologies",
    )

    if not any(_contains_term(normalized, marker) for marker in follow_up_markers):
        return message

    previous_entity = _last_referenced_entity(conversation_history)
    if not previous_entity:
        return message

    _, _, entity_name = previous_entity
    return f"{message} The referenced item is {entity_name}."


def _is_greeting(message: str) -> bool:
    normalized = re.sub(r"[^\w\s]", "", message.lower()).strip()
    return normalized in GREETING_WORDS


def _is_off_topic(message: str) -> bool:
    """Return True only when the question is clearly unrelated."""
    normalized = _normalize_text(message)
    if not normalized:
        return True

    if _find_alias(normalized, PROJECT_ALIASES) or _find_alias(
        normalized,
        RESEARCH_ALIASES,
    ):
        return False

    # Portfolio category words are valid even without explicitly naming Junayed.
    portfolio_terms = (
        "research",
        "research work",
        "publication",
        "paper",
        "papers",
        "project",
        "projects",
        "experience",
        "skills",
        "education",
        "cgpa",
        "gpa",
        "thesis",
        "award",
        "awards",
        "achievement",
        "coursework",
        "linkedin",
        "github",
        "contact",
        "email",
        "phone",
        "address",
        "location",
        "home address",
        "supervisor",
        "internship",
        "languages",
        "extracurricular",
        "arobot",
        "bistro",
        "rickshawx",
        "databench",
        "wafer",
        "breast ultrasound",
        "bea 2025",
    )
    if any(_contains_term(normalized, term) for term in portfolio_terms):
        return False

    person_reference = any(
        _contains_term(normalized, term)
        for term in ("junayed", "muhammad junayed", "he", "his", "him")
    )

    # Natural profile follow-ups such as "what does he do?" are valid.
    profile_patterns = (
        r"^what\s+does\s+(?:he|junayed)\s+do$",
        r"^who\s+is\s+(?:he|junayed|muhammad junayed)$",
        r"^tell\s+me\s+about\s+(?:him|junayed|muhammad junayed)$",
        r"^describe\s+(?:him|junayed|muhammad junayed)$",
        r"^what\s+is\s+his\s+background$",
    )
    if any(re.match(pattern, normalized) for pattern in profile_patterns):
        return False

    if person_reference and any(
        _contains_term(normalized, term)
        for term in (
            "work",
            "works",
            "working",
            "do",
            "does",
            "background",
            "about",
            "live",
            "lives",
            "based",
            "from",
            "study",
            "studies",
            "built",
            "created",
        )
    ):
        return False

    if any(_contains_term(normalized, term) for term in OFF_TOPIC_KEYWORDS):
        return True

    # A name reference remains portfolio-related; a bare pronoun does not.
    if _contains_term(normalized, "junayed") or _contains_term(
        normalized,
        "muhammad junayed",
    ):
        return False

    return True


def _detect_intent(
    message: str,
    conversation_history: Optional[Sequence[Dict[str, Any]]] = None,
) -> IntentResult:
    resolved_message = _resolve_follow_up(message, conversation_history)
    normalized = _normalize_text(resolved_message)

    project_match = _find_alias(normalized, PROJECT_ALIASES)
    if project_match:
        return IntentResult(
            INTENT_PROJECT_SPECIFIC,
            section_number=project_match[0],
            entity_name=project_match[1],
        )

    research_match = _find_alias(normalized, RESEARCH_ALIASES)
    if research_match:
        return IntentResult(
            INTENT_RESEARCH_SPECIFIC,
            section_number=research_match[0],
            entity_name=research_match[1],
        )

    # Specific facts before broad categories.
    if any(_contains_term(normalized, term) for term in ("cgpa", "gpa")):
        return IntentResult(INTENT_CGPA)

    if any(
        _contains_term(normalized, term)
        for term in (
            "address",
            "home address",
            "street address",
            "location",
            "where does he live",
            "where is he based",
            "where is he from",
        )
    ):
        return IntentResult(INTENT_LOCATION)

    if any(
        _contains_term(normalized, term)
        for term in (
            "linkedin",
            "github",
            "google scholar",
            "orcid",
            "portfolio website",
            "email",
            "contact",
            "phone",
            "mobile",
        )
    ):
        return IntentResult(INTENT_CONTACT)

    if any(
        _contains_term(normalized, term)
        for term in ("thesis", "dissertation", "research topic", "supervisor")
    ):
        return IntentResult(INTENT_THESIS)

    # Research must be checked before project/work.
    if any(
        _contains_term(normalized, term)
        for term in (
            "research",
            "research work",
            "publication",
            "publications",
            "paper",
            "papers",
            "conference work",
        )
    ):
        return IntentResult(INTENT_RESEARCH_SUMMARY)

    if any(
        _contains_term(normalized, term)
        for term in (
            "project",
            "projects",
            "project summary",
            "portfolio projects",
            "what has he built",
            "what did he build",
            "things he built",
            "applications he developed",
        )
    ):
        return IntentResult(INTENT_PROJECT_SUMMARY)

    if any(
        _contains_term(normalized, term)
        for term in (
            "experience",
            "work experience",
            "employment",
            "internship",
            "intern",
            "worked",
            "job",
            "industrial trainee",
        )
    ):
        return IntentResult(INTENT_EXPERIENCE)

    if any(
        _contains_term(normalized, term)
        for term in (
            "skills",
            "technical skill",
            "tech stack",
            "technologies he knows",
            "programming languages",
            "frameworks",
            "tools",
        )
    ):
        return IntentResult(INTENT_SKILLS)

    if any(
        _contains_term(normalized, term)
        for term in (
            "education",
            "degree",
            "academic background",
            "university",
            "ssc",
            "hsc",
        )
    ):
        return IntentResult(INTENT_EDUCATION)

    if any(
        _contains_term(normalized, term)
        for term in ("award", "awards", "achievement", "achievements", "prize")
    ):
        return IntentResult(INTENT_AWARDS)

    if any(
        _contains_term(normalized, term)
        for term in ("language", "languages", "bangla", "english", "speak")
    ):
        return IntentResult(INTENT_LANGUAGES)

    if any(
        _contains_term(normalized, term)
        for term in ("course", "courses", "coursework", "subjects")
    ):
        return IntentResult(INTENT_COURSEWORK)

    if any(
        _contains_term(normalized, term)
        for term in (
            "extracurricular",
            "leadership",
            "volunteer",
            "club",
            "photographic society",
            "televerse",
        )
    ):
        return IntentResult(INTENT_EXTRACURRICULAR)

    profile_patterns = (
        r"^who\s+is\s+",
        r"^tell\s+me\s+about\s+",
        r"^what\s+does\s+(?:he|junayed)\s+do$",
        r"^describe\s+",
        r"background",
        r"professional profile",
        r"introduce",
    )
    if any(re.search(pattern, normalized) for pattern in profile_patterns):
        return IntentResult(INTENT_PROFILE)

    if any(
        _contains_term(normalized, term)
        for term in ("junayed", "muhammad junayed")
    ):
        return IntentResult(INTENT_PROFILE)

    return IntentResult(INTENT_GENERAL)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _deduplicate_results(results: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduplicated: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for result in results:
        doc_id = str(result.get("doc_id") or "")
        metadata = result.get("metadata") or {}
        fallback_key = (
            f"{metadata.get('section_number', '')}:"
            f"{metadata.get('chunk_index', '')}:"
            f"{result.get('text', '')[:80]}"
        )
        key = doc_id or fallback_key
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(result)

    return deduplicated


async def _retrieve_for_intent(
    user_message: str,
    intent_result: IntentResult,
) -> List[Dict[str, Any]]:
    intent = intent_result.intent

    # The pgvector-backed helpers in services.vector_store are already
    # coroutine-safe (they schedule their own asyncio.run when called from
    # a thread, and await directly when called from the event loop), so we
    # do not need asyncio.to_thread here.
    if intent_result.section_number:
        return get_by_section_numbers([intent_result.section_number])

    section_numbers = INTENT_SECTION_NUMBERS.get(intent)
    if section_numbers:
        return get_by_section_numbers(list(section_numbers))

    if intent == INTENT_PROJECT_SUMMARY:
        return get_by_entity_type("project")

    if intent == INTENT_SKILLS:
        return get_by_entity_type("skill")

    if intent == INTENT_AWARDS:
        return get_by_entity_type("award")

    return vector_query(user_message, n_results=6)


# ---------------------------------------------------------------------------
# Context preparation
# ---------------------------------------------------------------------------

LIMITATION_HEADERS = {
    "evaluation limitation",
    "evaluation information not provided",
    "evaluation and safety limitations",
    "thesis limitation in this knowledge source",
}

BLOCK_HEADERS = {
    "problem",
    "research problem",
    "dataset",
    "approach",
    "main methods",
    "main result",
    "main finding",
    "technologies",
    "technologies and models",
    "technologies and methods",
    "functional components",
    "implementation context",
    "architecture",
    "features",
    "features and architecture",
    "services",
    "models",
    "reported results",
    "reported result",
    "reported outcome",
    "deployment",
    "outcome",
    "responsibilities",
    "evaluated tracks",
    "models evaluated",
    "shared-task rankings",
    "exact f1 results",
    "hardware",
    "keywords",
}


def _clean_context_for_llm(context: str) -> str:
    """Remove internal and unsupported text while preserving portfolio facts."""
    if not context:
        return ""

    context = _repair_pdf_artifacts(context)
    context = re.sub(r"(?im)^\s*Page\s+\d+(?:\s*/\s*\d+)?\s*$", "", context)

    internal_pattern = re.compile(
        r"^[\s•◦▪\-*]*(?:Document ID|Source|Chunk ID|Chunk Index)"
        r"\s*:\s*.*$",
        re.IGNORECASE,
    )

    unsupported_starters = (
        "the following information is not documented",
        "the following values are not included",
        "the following are not documented",
        "no final experiment",
    )

    disclaimer_phrases = (
        "should not infer",
        "should not assign",
        "not documented in the provided sources",
        "not specified in the provided sources",
        "not included in the source material",
        "should be added only after verification",
        "without verified information",
        "unless those details are added to a future verified version",
    )

    cleaned: List[str] = []
    skip_until_header = False
    skip_keywords = False

    for raw_line in context.splitlines():
        line = raw_line.strip()
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        lower = line.lower().rstrip(":").strip()

        if lower in LIMITATION_HEADERS:
            skip_until_header = True
            skip_keywords = False
            continue

        if lower == "keywords":
            skip_keywords = True
            skip_until_header = False
            continue

        if skip_keywords:
            # A new retrieved section is marked explicitly by this helper.
            if line.startswith("[Section:"):
                skip_keywords = False
            else:
                continue

        if any(lower.startswith(starter) for starter in unsupported_starters):
            skip_until_header = True
            continue

        if skip_until_header:
            if lower in BLOCK_HEADERS and lower not in LIMITATION_HEADERS:
                skip_until_header = False
                if lower == "keywords":
                    skip_keywords = True
                else:
                    cleaned.append(line)
            continue

        if internal_pattern.match(line):
            continue

        if any(phrase in lower for phrase in disclaimer_phrases):
            continue

        line = re.sub(r"^[•◦▪]\s*", "", line)
        line = re.sub(r"^[*-]\s+(?=[A-Za-z0-9])", "", line)
        line = re.sub(r"(?<=[A-Za-z])\s*-\s*(?=[a-z])", "-", line)
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            cleaned.append(line)

    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _metadata_section(result: Dict[str, Any]) -> str:
    metadata = result.get("metadata") or {}
    section = str(
        metadata.get("section") or "Relevant portfolio information"
    )
    section = _repair_pdf_artifacts(section)
    section = re.split(
        r"\s*[•◦▪]\s*|\s+Document\s+ID\s*:",
        section,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return section.strip(" -:") or "Relevant portfolio information"


def _result_sort_key(result: Dict[str, Any]) -> Tuple[int, ...]:
    metadata = result.get("metadata") or {}
    section_number = str(metadata.get("section_number") or "999")
    values: List[int] = []
    for part in section_number.split("."):
        try:
            values.append(int(part))
        except ValueError:
            values.append(999)
    values.append(int(metadata.get("chunk_index") or 0))
    return tuple(values)


def _extract_label(text: str, label: str) -> Optional[str]:
    """Extract a label value, including one or more wrapped PDF lines."""
    lines = _repair_pdf_artifacts(text).splitlines()
    label_pattern = re.compile(
        rf"^\s*[•◦▪\-*]?\s*{re.escape(label)}\s*:\s*(.*)$",
        re.IGNORECASE,
    )
    next_label_pattern = re.compile(
        r"^\s*[•◦▪\-*]?\s*[A-Za-z][^:\n]{0,55}\s*:\s*.+$"
    )

    for index, raw_line in enumerate(lines):
        match = label_pattern.match(raw_line.strip())
        if not match:
            continue

        parts = [match.group(1).strip()]
        for next_raw in lines[index + 1:index + 4]:
            next_line = next_raw.strip()
            if not next_line:
                break
            lower = next_line.lower().rstrip(":").strip()
            if (
                next_line.startswith(("•", "◦", "▪", "*"))
                or next_label_pattern.match(next_line)
                or lower in BLOCK_HEADERS
                or re.match(r"^\d+(?:\.\d+)*\.?\s+", next_line)
            ):
                break
            parts.append(next_line)

        value = _repair_pdf_artifacts(" ".join(parts))
        value = re.sub(r"\s+", " ", value).strip()
        return value or None

    return None


def _extract_block(text: str, header_names: Sequence[str]) -> str:
    lines = text.splitlines()
    normalized_headers = {header.lower() for header in header_names}
    start: Optional[int] = None
    collected: List[str] = []

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        lower = line.lower().rstrip(":").strip()

        if start is None:
            if lower in normalized_headers:
                start = index + 1
            continue

        if lower in BLOCK_HEADERS or re.match(r"^\d+(?:\.\d+)*\.?\s+", line):
            break

        if line:
            line = re.sub(r"^[•◦▪]\s*", "", line)
            collected.append(line)

    return " ".join(collected).strip()


def _extract_block_items(
    text: str,
    header_names: Sequence[str],
) -> List[str]:
    """Extract bullet/list items under a structural header."""
    lines = text.splitlines()
    normalized_headers = {header.lower() for header in header_names}
    start: Optional[int] = None
    items: List[str] = []

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        lower = line.lower().rstrip(":").strip()

        if start is None:
            if lower in normalized_headers:
                start = index + 1
            continue

        if lower in BLOCK_HEADERS or re.match(r"^\d+(?:\.\d+)*\.?\s+", line):
            break

        if not line:
            continue

        cleaned = re.sub(r"^[•◦▪\-*]\s*", "", line).strip()
        if cleaned:
            items.append(cleaned)

    return items


def _first_sentences(text: str, limit: int = 1) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
        if sentence.strip()
    ]
    return " ".join(sentences[:limit])


def _compact_result(
    result: Dict[str, Any],
    intent: str,
) -> str:
    raw_text = str(result.get("text") or "")
    section = _metadata_section(result)
    clean_text = _clean_context_for_llm(raw_text)

    if intent == INTENT_PROJECT_SUMMARY:
        project_type = _extract_label(raw_text, "Project type")
        problem = _extract_block(raw_text, ("Problem",))
        outcome = _extract_block(raw_text, ("Outcome", "Reported Outcome"))
        fields = [f"Project: {section}"]
        if project_type:
            fields.append(f"Type: {project_type}")
        if problem:
            fields.append(f"Purpose: {_first_sentences(problem, 1)}")
        if outcome:
            fields.append(f"Outcome: {_first_sentences(outcome, 1)}")
        return "\n".join(fields)

    if intent == INTENT_RESEARCH_SUMMARY:
        title = _extract_label(raw_text, "Title") or section
        research_problem = _extract_block(raw_text, ("Research Problem", "Problem"))
        approach = _extract_block(raw_text, ("Approach", "Proposed Research Direction"))
        result = _extract_block(
            raw_text,
            ("Main Result", "Main Finding", "Reported Result"),
        )
        fields = [f"Research item: {title}"]
        if research_problem:
            fields.append(f"Problem: {_first_sentences(research_problem, 1)}")
        if approach:
            fields.append(f"Method: {_first_sentences(approach, 1)}")
        if result:
            fields.append(f"Verified result/finding: {_first_sentences(result, 1)}")
        return "\n".join(fields)

    return f"[Section: {section}]\n{clean_text}".strip()


def _prepare_context(
    results: Sequence[Dict[str, Any]],
    intent: str,
) -> str:
    parts: List[str] = []

    for result in sorted(_deduplicate_results(results), key=_result_sort_key):
        compact = _compact_result(result, intent)
        if compact:
            parts.append(compact)

    return "\n\n---\n\n".join(parts) if parts else "No specific context available."


# ---------------------------------------------------------------------------
# Prompt and generated-response cleaning
# ---------------------------------------------------------------------------

def _build_prompt(
    user_message: str,
    context: str,
    intent: str = INTENT_GENERAL,
) -> str:
    instruction = INTENT_INSTRUCTIONS.get(
        intent,
        INTENT_INSTRUCTIONS[INTENT_GENERAL],
    )
    system = SYSTEM_PROMPT.format(
        intent_instruction=instruction,
        context=context,
    )
    return f"<s>[INST] {system}\n\nUser question: {user_message} [/INST]"


def _clean_response(text: str) -> str:
    if not text:
        return NO_INFORMATION_RESPONSE

    text = _repair_pdf_artifacts(text)

    for artifact in (
        "[INST]",
        "[/INST]",
        "</s>",
        "<s>",
        "<<SYS>>",
        "<</SYS>>",
        "<|",
        "|>",
    ):
        text = text.replace(artifact, "")

    text = re.sub(
        r"(?im)^\s*Page\s+\d+(?:\s*/\s*\d+)?\s*$",
        "",
        text,
    )
    text = re.sub(r"\[Section:[^\]]+\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?im)^\s*(?:Professional Profile|Selected Projects|"
        r"Research and Publications|Work Experience|Technical Skills|"
        r"Education|Personal and Professional Information)\s*:?\s*",
        "",
        text,
    )
    text = re.sub(
        r"(?im)^\s*(?:Research Problem|Problem|Approach|Dataset|"
        r"Technologies|Functional Components|Implementation Context|"
        r"Architecture|Features|Outcome|Main Result|Main Finding|"
        r"Reported Result|Reported Outcome)\s*:?\s*",
        "",
        text,
    )
    text = re.sub(
        r"(?im)^\s*(?:Document ID|Source|Chunk ID|Chunk Index)\s*:\s*.*$",
        "",
        text,
    )
    text = re.sub(
        r"Muhammad_Junayed_RAG_Knowledge_Base(?:\(1\))?\.pdf",
        "",
        text,
        flags=re.IGNORECASE,
    )

    disclaimer_phrases = (
        "should not infer",
        "should not assign",
        "not documented in the provided sources",
        "not specified in the provided sources",
        "not included in the source material",
        "should be added only after verification",
        "without verified information",
    )
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
        and not any(
            phrase in sentence.lower()
            for phrase in disclaimer_phrases
        )
    ]

    unique: List[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        sentence = re.sub(r"(?<=[A-Za-z])\s*-\s*(?=[a-z])", "-", sentence)
        sentence = re.sub(r"\s+", " ", sentence).strip(" -\n\t")
        normalized = sentence.lower()
        if sentence and normalized not in seen:
            seen.add(normalized)
            unique.append(sentence)

    response = " ".join(unique).strip()
    if not response:
        return NO_INFORMATION_RESPONSE

    if len(response) > 1400:
        truncated = response[:1400]
        boundary = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
        )
        response = (
            truncated[: boundary + 1]
            if boundary > 300
            else truncated.rstrip()
        )

    return response


# ---------------------------------------------------------------------------
# Hugging Face API
# ---------------------------------------------------------------------------

async def _call_hf_api(
    prompt: str,
    timeout: float = 35.0,
) -> str:
    url = f"https://api-inference.huggingface.co/models/{settings.HF_MODEL_ID}"
    headers = {"Authorization": f"Bearer {settings.HF_API_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 420,
            "temperature": 0.2,
            "top_p": 0.9,
            "repetition_penalty": 1.08,
            "return_full_text": False,
        },
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 429:
            raise RuntimeError("Hugging Face API rate limit reached.")

        if response.status_code == 503:
            await asyncio.sleep(4)
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            try:
                error_message = str(response.json().get("error", ""))
            except (ValueError, AttributeError):
                error_message = response.text[:300]

            if "loading" in error_message.lower():
                await asyncio.sleep(4)
                response = await client.post(url, json=payload, headers=headers)

            response.raise_for_status()

        result = response.json()

    if isinstance(result, list) and result:
        generated = str(result[0].get("generated_text") or "").strip()
        return _clean_response(generated)

    if isinstance(result, dict) and "generated_text" in result:
        return _clean_response(str(result["generated_text"]))

    logger.warning("Unexpected Hugging Face response: %s", str(result)[:300])
    return NO_INFORMATION_RESPONSE


# ---------------------------------------------------------------------------
# Deterministic fallback formatting
# ---------------------------------------------------------------------------

def _extract_urls(text: str) -> Dict[str, str]:
    text = _repair_pdf_artifacts(text)
    urls: Dict[str, str] = {}
    for label, url in re.findall(
        r"(?im)^\s*[•◦▪\-*]?\s*([A-Za-z][A-Za-z ]+?)\s*:\s*"
        r"(https?://[^\s]+)",
        text,
    ):
        urls[label.strip().lower()] = url.rstrip(".,)")

    for url in re.findall(r"https?://[^\s]+", text):
        clean = url.rstrip(".,)")
        lower = clean.lower()
        if "linkedin" in lower:
            urls.setdefault("linkedin", clean)
        elif "github" in lower:
            urls.setdefault("github", clean)
        elif "scholar" in lower:
            urls.setdefault("google scholar", clean)
        elif "orcid" in lower:
            urls.setdefault("orcid", clean)
        elif "muhammadjunayed.vercel.app" in lower:
            urls.setdefault("portfolio website", clean)

    return urls


def _extract_email(text: str) -> Optional[str]:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    return match.group(0) if match else None


def _unique_sections(
    results: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    unique: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for result in sorted(results, key=_result_sort_key):
        metadata = result.get("metadata") or {}
        section_number = str(metadata.get("section_number") or "")
        if section_number in seen:
            continue
        seen.add(section_number)
        unique.append(result)
    return unique


def _fallback_profile(results: Sequence[Dict[str, Any]]) -> str:
    for result in results:
        metadata = result.get("metadata") or {}
        if str(metadata.get("section_number")) != "1":
            continue

        text = _clean_context_for_llm(str(result.get("text") or ""))
        text = re.sub(
            r"^(?:Professional Profile|"
            r"Professional Profile\s*>\s*Professional Profile)\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text)
            if sentence.strip()
        ]
        if not sentences:
            continue

        first = sentences[0]
        publication_sentence = next(
            (
                sentence
                for sentence in sentences
                if "conference publication" in sentence.lower()
            ),
            "",
        )
        return (
            f"{first} He works across artificial intelligence, machine learning, "
            "computer vision, NLP and large language models, RAG, backend and "
            "cloud engineering, MLOps, distributed systems, and embedded systems. "
            f"{publication_sentence}"
        ).strip()

    return NO_INFORMATION_RESPONSE


def _fallback_cgpa(results: Sequence[Dict[str, Any]]) -> str:
    text = "\n".join(str(result.get("text") or "") for result in results)
    cgpa = re.search(
        r"(?im)^\s*[•◦▪\-*]?\s*CGPA\s*:\s*([^\n]+)",
        text,
    )
    coverage = re.search(
        r"(?im)^\s*[•◦▪\-*]?\s*CGPA coverage\s*:\s*([^\n]+)",
        text,
    )
    if not cgpa:
        return NO_INFORMATION_RESPONSE

    answer = f"Muhammad Junayed's CGPA is {cgpa.group(1).strip()}."
    if coverage:
        answer += f" This result covers {coverage.group(1).strip().lower()}."
    return answer


def _fallback_experience(results: Sequence[Dict[str, Any]]) -> str:
    items: List[str] = []
    for result in _unique_sections(results):
        raw = str(result.get("text") or "")
        section = _metadata_section(result)
        organization = _extract_label(raw, "Organization")
        role = _extract_label(raw, "Role")
        duration = _extract_label(raw, "Duration")
        focus = _extract_block(raw, ("The internship involved work related to",))
        if not focus:
            focus = _extract_block(raw, ("The training focused on",))

        identity = role or section
        if organization and organization.lower() not in identity.lower():
            identity = f"{identity} at {organization}"
        sentence = identity
        if duration:
            sentence += f" from {duration}"
        sentence += "."
        if focus:
            sentence += f" The documented focus included {focus.lower()}."
        items.append(sentence)

    if not items:
        return NO_INFORMATION_RESPONSE

    return " ".join(items)


def _fallback_project_summary(results: Sequence[Dict[str, Any]]) -> str:
    projects = _unique_sections(results)
    if not projects:
        return NO_INFORMATION_RESPONSE

    titles = [_metadata_section(result) for result in projects]
    types = [
        _extract_label(str(result.get("text") or ""), "Project type")
        for result in projects
    ]
    normalized_types = [project_type for project_type in types if project_type]

    representative = titles[:5]
    intro = (
        f"Muhammad Junayed's portfolio contains {len(projects)} documented "
        "projects spanning AI and machine learning, backend and distributed "
        "systems, full-stack development, MLOps, and IoT."
    )
    examples = (
        "Representative projects include "
        + ", ".join(representative[:-1])
        + (f", and {representative[-1]}." if representative else "")
    )

    if normalized_types:
        breadth = (
            "Across these projects, he has worked with multimodal RAG, "
            "microservices and asynchronous processing, data engineering, "
            "computer vision, cloud deployment, and embedded automation."
        )
    else:
        breadth = (
            "The projects demonstrate work across software, machine learning, "
            "cloud, and embedded systems."
        )

    closing = (
        "A named project can be explained separately with its architecture, "
        "technologies, features, and documented outcome."
    )
    return " ".join((intro, examples, breadth, closing))


def _fallback_specific_project(
    results: Sequence[Dict[str, Any]],
) -> str:
    if not results:
        return NO_INFORMATION_RESPONSE

    result = sorted(results, key=_result_sort_key)[0]
    raw = str(result.get("text") or "")
    title = _metadata_section(result)
    project_type = _extract_label(raw, "Project type")
    problem = _extract_block(raw, ("Problem",))
    technologies = _extract_block(
        raw,
        ("Technologies", "Technologies and Models", "Technologies and Methods"),
    )
    implementation = _extract_block(
        raw,
        (
            "Approach",
            "Architecture",
            "Implementation Context",
            "Features and Architecture",
        ),
    )
    outcome = _extract_block(raw, ("Outcome", "Reported Outcome"))

    sentences = [f"{title} is one of Muhammad Junayed's documented projects."]
    if project_type:
        article = "an" if project_type[:1].lower() in "aeiou" else "a"
        sentences.append(
            f"It is described as {article} {project_type.lower()}."
        )
    if problem:
        sentences.append(_first_sentences(problem, 2))
    if technologies:
        technology_items = _extract_block_items(
            raw,
            ("Technologies", "Technologies and Models", "Technologies and Methods"),
        )
        technology_text = ", ".join(technology_items[:8]) or technologies
        sentences.append(f"Its documented technologies include {technology_text}.")
    if implementation:
        sentences.append(_first_sentences(implementation, 2))
    if outcome:
        sentences.append(_first_sentences(outcome, 2))

    return _clean_response(" ".join(sentences))


def _fallback_research_summary(
    results: Sequence[Dict[str, Any]],
) -> str:
    by_section = {
        str((result.get("metadata") or {}).get("section_number")): result
        for result in _unique_sections(results)
    }

    sentences: List[str] = []

    thesis = by_section.get("4.1")
    thesis_problem = by_section.get("4.2")
    if thesis:
        raw = str(thesis.get("text") or "")
        title = _extract_label(raw, "Title")
        status = (_extract_label(raw, "Status") or "").lower()
        if title:
            if status.startswith("ongoing undergraduate thesis"):
                sentences.append(
                    f"His undergraduate thesis, “{title},” is ongoing."
                )
            elif status:
                sentences.append(
                    f"His undergraduate thesis, “{title},” has the status "
                    f"“{status}.”"
                )
            else:
                sentences.append(
                    f"His undergraduate thesis is titled “{title}.”"
                )

    if thesis_problem:
        problem_text = _clean_context_for_llm(
            str(thesis_problem.get("text") or "")
        )
        problem_text = re.sub(
            r"^(?:Undergraduate Thesis\s*>\s*)?Research Problem\s*",
            "",
            problem_text,
            flags=re.IGNORECASE,
        )
        problem_sentence = _first_sentences(problem_text, 1)
        if problem_sentence:
            sentences.append(problem_sentence)

    publication_sentences: List[str] = []
    for section_number in ("9.1", "9.2", "9.3"):
        item = by_section.get(section_number)
        if not item:
            continue

        raw = str(item.get("text") or "")
        title = _metadata_section(item)
        approach = _extract_block(raw, ("Approach",))
        result_text = _extract_block(raw, ("Main Result", "Main Finding"))

        method = _first_sentences(approach, 1)
        if method:
            method = method[0].lower() + method[1:] if len(method) > 1 else method.lower()

        sentence = f"For “{title},” "
        sentence += method or "he contributed to the reported study."
        if result_text:
            finding = _first_sentences(result_text, 1)
            sentence += f" {finding}"
        publication_sentences.append(sentence)

    if publication_sentences:
        sentences.append(
            "He has also contributed to three conference publications."
        )
        sentences.extend(publication_sentences)

    return _clean_response(" ".join(sentences)) if sentences else NO_INFORMATION_RESPONSE

def _fallback_specific_research(
    results: Sequence[Dict[str, Any]],
) -> str:
    if not results:
        return NO_INFORMATION_RESPONSE

    result = sorted(results, key=_result_sort_key)[0]
    raw = str(result.get("text") or "")
    title = _metadata_section(result)
    authors = _extract_label(raw, "Authors")
    venue = (
        _extract_label(raw, "Conference")
        or _extract_label(raw, "Venue")
    )
    problem = _extract_block(raw, ("Research Problem",))
    dataset = _extract_block(raw, ("Dataset",))
    approach = _extract_block(raw, ("Approach",))
    result_text = _extract_block(raw, ("Main Result", "Main Finding"))
    doi = _extract_label(raw, "DOI")

    sentences = [f"“{title}” is one of Muhammad Junayed's research publications."]
    if problem:
        sentences.append(_first_sentences(problem, 2))
    if dataset:
        sentences.append(f"The documented dataset information states that {_first_sentences(dataset, 1).lower()}")
    if approach:
        sentences.append(_first_sentences(approach, 2))
    if result_text:
        sentences.append(_first_sentences(result_text, 2))
    if authors or venue or (doi and doi.lower() != "not provided"):
        details: List[str] = []
        if venue:
            details.append(f"it was presented or published through {venue}")
        if authors:
            details.append(f"the listed authors are {authors}")
        if doi and doi.lower() != "not provided":
            details.append(f"the DOI is {doi}")
        sentences.append("For publication details, " + "; ".join(details) + ".")

    return _clean_response(" ".join(sentences))



def _fallback_location(
    question: str,
    results: Sequence[Dict[str, Any]],
) -> str:
    raw = "\n".join(str(result.get("text") or "") for result in results)
    location = _extract_label(raw, "Location")
    normalized = _normalize_text(question)

    if not location:
        return NO_INFORMATION_RESPONSE

    if any(
        _contains_term(normalized, term)
        for term in ("home address", "street address", "exact address", "address")
    ):
        return (
            f"The portfolio lists Muhammad Junayed's general location as "
            f"{location}. It does not provide an exact home or street address."
        )

    return f"Muhammad Junayed is based in {location}."

def _fallback_contact(
    question: str,
    results: Sequence[Dict[str, Any]],
) -> str:
    raw = "\n".join(str(result.get("text") or "") for result in results)
    urls = _extract_urls(raw)
    email = _extract_email(raw)
    normalized = _normalize_text(question)

    if _contains_term(normalized, "linkedin") and urls.get("linkedin"):
        return f"Muhammad Junayed's LinkedIn profile is {urls['linkedin']}."
    if _contains_term(normalized, "github") and urls.get("github"):
        return f"Muhammad Junayed's GitHub profile is {urls['github']}."
    if _contains_term(normalized, "google scholar") and urls.get("google scholar"):
        return f"His Google Scholar profile is {urls['google scholar']}."
    if _contains_term(normalized, "orcid") and urls.get("orcid"):
        return f"His ORCID profile is {urls['orcid']}."
    if _contains_term(normalized, "email") and email:
        return f"Muhammad Junayed's professional email is {email}."

    phone = re.search(
        r"(?im)^\s*[•◦▪\-*]?\s*Phone\s*:\s*([^\n]+)",
        raw,
    )
    if any(
        _contains_term(normalized, term)
        for term in ("phone", "mobile")
    ) and phone:
        return f"Muhammad Junayed's listed phone number is {phone.group(1).strip()}."

    details: List[str] = []
    if email:
        details.append(f"email at {email}")
    if urls.get("linkedin"):
        details.append(f"LinkedIn at {urls['linkedin']}")
    if urls.get("github"):
        details.append(f"GitHub at {urls['github']}")

    if not details:
        return NO_INFORMATION_RESPONSE

    return "You can reach Muhammad Junayed through " + ", ".join(details) + "."


def _generate_fallback_response(
    user_message: str,
    context: str,
    intent: str = INTENT_GENERAL,
    results: Optional[Sequence[Dict[str, Any]]] = None,
) -> str:
    """Produce a grounded answer when the LLM API is unavailable."""
    result_list = list(results or [])

    if _is_greeting(user_message):
        return (
            "Hello! I can tell you about Muhammad Junayed's profile, research, "
            "projects, skills, education, and experience."
        )

    if _is_off_topic(user_message):
        return OFF_TOPIC_RESPONSE

    if intent == INTENT_PROFILE:
        return _fallback_profile(result_list)
    if intent == INTENT_CGPA:
        return _fallback_cgpa(result_list)
    if intent == INTENT_EXPERIENCE:
        return _fallback_experience(result_list)
    if intent == INTENT_PROJECT_SUMMARY:
        return _fallback_project_summary(result_list)
    if intent == INTENT_PROJECT_SPECIFIC:
        return _fallback_specific_project(result_list)
    if intent == INTENT_RESEARCH_SUMMARY:
        return _fallback_research_summary(result_list)
    if intent == INTENT_RESEARCH_SPECIFIC:
        return _fallback_specific_research(result_list)
    if intent == INTENT_CONTACT:
        return _fallback_contact(user_message, result_list)
    if intent == INTENT_LOCATION:
        return _fallback_location(user_message, result_list)

    if not context or context == "No specific context available.":
        return NO_INFORMATION_RESPONSE

    clean = _clean_context_for_llm(context)
    return _first_sentences(clean, 5) or NO_INFORMATION_RESPONSE


# Compatibility wrappers for older tests/imports.
def _build_structured_answer(question: str, context: str) -> str:
    intent = _detect_intent(question).intent
    return _generate_fallback_response(
        question,
        context,
        intent=intent,
        results=[],
    )


def _format_skills_answer(chunks: list) -> str:
    return _first_sentences(" ".join(chunks), 6) or NO_INFORMATION_RESPONSE


def _format_projects_answer(chunks: list) -> str:
    return _first_sentences(" ".join(chunks), 6) or NO_INFORMATION_RESPONSE


def _format_research_answer(chunks: list) -> str:
    return _first_sentences(" ".join(chunks), 6) or NO_INFORMATION_RESPONSE


def _format_achievements_answer(chunks: list) -> str:
    return _first_sentences(" ".join(chunks), 6) or NO_INFORMATION_RESPONSE


def _format_about_answer(chunks: list) -> str:
    return _first_sentences(" ".join(chunks), 4) or NO_INFORMATION_RESPONSE


def _format_experience_answer(chunks: list) -> str:
    return _first_sentences(" ".join(chunks), 5) or NO_INFORMATION_RESPONSE


def _format_general_answer(chunks: list) -> str:
    return _first_sentences(" ".join(chunks), 5) or NO_INFORMATION_RESPONSE


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

async def generate_response(
    user_message: str,
    conversation_history: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate a metadata-aware, intent-routed portfolio answer."""
    message = (user_message or "").strip()

    if _is_greeting(message):
        return {
            "response": (
                "Hello! I can tell you about Muhammad Junayed's profile, "
                "research, projects, skills, education, and experience."
            ),
            "sources": [],
        }

    resolved_message = _resolve_follow_up(message, conversation_history)

    intent_result = _detect_intent(
        resolved_message,
        conversation_history=conversation_history,
    )

    if (
        intent_result.intent == INTENT_GENERAL
        and _is_off_topic(resolved_message)
    ):
        return {
            "response": OFF_TOPIC_RESPONSE,
            "sources": [],
        }

    try:
        results = await _retrieve_for_intent(
            resolved_message,
            intent_result,
        )
    except Exception as exc:
        logger.exception(
            "Portfolio retrieval failed for intent %s: %s",
            intent_result.intent,
            exc,
        )
        results = []

    results = _deduplicate_results(results)
    context = _prepare_context(results, intent_result.intent)

    sources = list(
        dict.fromkeys(
            str((result.get("metadata") or {}).get("source") or "profile")
            for result in results
        )
    )

    if not settings.HF_API_TOKEN:
        response_text = _generate_fallback_response(
            resolved_message,
            context,
            intent=intent_result.intent,
            results=results,
        )
        return {
            "response": _clean_response(response_text),
            "sources": sources,
        }

    prompt = _build_prompt(
        resolved_message,
        context,
        intent=intent_result.intent,
    )

    try:
        response_text = await _call_hf_api(prompt)
    except Exception as first_error:
        logger.warning(
            "HF API call failed; retrying once. Error: %s",
            first_error,
        )
        try:
            await asyncio.sleep(1.5)
            response_text = await _call_hf_api(prompt, timeout=18.0)
        except Exception as retry_error:
            logger.error(
                "HF API retry failed for intent %s: %s",
                intent_result.intent,
                retry_error,
            )
            response_text = _generate_fallback_response(
                resolved_message,
                context,
                intent=intent_result.intent,
                results=results,
            )

    return {
        "response": _clean_response(response_text),
        "sources": sources,
    }
