import logging
import re

import httpx
from typing import Optional

from config import settings
from services.vector_store import query as vector_query

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an AI assistant for Muhammad Junayed's portfolio website.
Muhammad Junayed is an AI Engineering Enthusiast specializing in Computer Vision and Cloud-Native ML Systems.
He is a final-year ETE student at CUET.

Answer questions about Muhammad Junayed directly and concisely using ONLY the provided context below.
Do not make up information. If the context contains relevant information, present it clearly.
If you don't have enough information in the context to answer, say so politely.

Context from knowledge base:
{context}
"""


async def generate_response(user_message: str) -> dict:
    """Generate a response using RAG: query vector store for context, then call HuggingFace."""
    # Retrieve relevant context from vector store
    results = vector_query(user_message, n_results=3)
    context_texts = [r["text"] for r in results]
    context = "\n\n".join(context_texts) if context_texts else "No specific context available."

    sources = [r["metadata"].get("source", "profile") for r in results if r.get("metadata")]

    # If no HF API token, return a fallback response
    if not settings.HF_API_TOKEN:
        logger.warning(
            "HF_API_TOKEN is not set - using fallback response. "
            "Set HF_API_TOKEN environment variable to enable AI-generated responses."
        )
        return {
            "response": _generate_fallback_response(user_message, context),
            "sources": list(set(sources)),
        }

    # Call HuggingFace Inference API
    prompt = _build_prompt(user_message, context)
    try:
        response_text = await _call_hf_api(prompt)
        logger.info("Successfully generated response via HF API for query: %s", user_message[:80])
    except Exception as e:
        logger.error(
            "HF API call failed, using fallback. Error: %s | Model: %s | Query: %s",
            str(e),
            settings.HF_MODEL_ID,
            user_message[:80],
        )
        response_text = _generate_fallback_response(user_message, context)

    return {
        "response": response_text,
        "sources": list(set(sources)),
    }


def _build_prompt(user_message: str, context: str) -> str:
    system = SYSTEM_PROMPT.format(context=context)
    return (
        f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_message}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
    )


async def _call_hf_api(prompt: str) -> str:
    url = f"https://api-inference.huggingface.co/models/{settings.HF_MODEL_ID}"
    headers = {"Authorization": f"Bearer {settings.HF_API_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 500,
            "temperature": 0.7,
            "return_full_text": False,
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
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
        return result[0].get("generated_text", "").strip()
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
    greeting_words = {"hello", "hi", "hey", "greetings", "howdy", "hola", "yo"}
    # Strip punctuation for comparison
    stripped_message = re.sub(r'[^\w\s]', '', message_lower).strip()
    if stripped_message in greeting_words:
        return (
            "Hello! I'm Muhammad Junayed's AI assistant. "
            "I can tell you about his projects, skills, research, and experience. "
            "What would you like to know?"
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
    if any(word in message_lower for word in ["address", "location", "where", "live", "based"]):
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
    if any(word in message_lower for word in ["email", "mail", "contact info", "reach"]):
        found_email = _extract_email(context) if context else None
        found_email = found_email or "mdjunayed573@gmail.com"
        response = f"You can reach Muhammad Junayed via email at: {found_email}"
        if context and context != "No specific context available.":
            urls = _extract_urls(context)
            if urls:
                social_parts = []
                if "linkedin" in urls:
                    social_parts.append(f"LinkedIn: {urls['linkedin']}")
                if "github" in urls:
                    social_parts.append(f"GitHub: {urls['github']}")
                if social_parts:
                    response += "\n\nHe is also available on:\n" + "\n".join(f"- {s}" for s in social_parts)
        return response

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
