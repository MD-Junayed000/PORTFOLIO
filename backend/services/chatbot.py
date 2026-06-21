import httpx
from typing import Optional

from config import settings
from services.vector_store import query as vector_query


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
        return {
            "response": _generate_fallback_response(user_message, context),
            "sources": list(set(sources)),
        }

    # Call HuggingFace Inference API
    prompt = _build_prompt(user_message, context)
    try:
        response_text = await _call_hf_api(prompt)
    except Exception:
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
        response.raise_for_status()
        result = response.json()

    if isinstance(result, list) and len(result) > 0:
        return result[0].get("generated_text", "").strip()
    return "I apologize, but I could not generate a response at this time."


def _format_context_response(context: str) -> str:
    """Format retrieved context into a coherent, readable response."""
    # Clean up the context - remove excessive whitespace and normalize
    lines = context.strip().split("\n")
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    cleaned = " ".join(cleaned_lines)

    # Truncate at a sentence boundary rather than mid-sentence
    if len(cleaned) > 800:
        # Find the last sentence end before 800 chars
        truncated = cleaned[:800]
        last_period = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
        )
        if last_period > 200:
            cleaned = truncated[: last_period + 1]
        else:
            # Fall back to last space
            last_space = truncated.rfind(" ")
            if last_space > 200:
                cleaned = truncated[:last_space] + "..."
            else:
                cleaned = truncated + "..."

    return cleaned


def _generate_fallback_response(user_message: str, context: str) -> str:
    """Generate a response using retrieved context when HF API is not available."""
    message_lower = user_message.lower()

    # If we have meaningful context from the vector store, use it directly
    if context and context != "No specific context available.":
        formatted = _format_context_response(context)
        # Provide a conversational wrapper based on question type
        if any(word in message_lower for word in ["hello", "hi", "hey"]):
            return (
                "Hello! I'm Muhammad Junayed's AI assistant. "
                "I can tell you about his projects, skills, research, and experience. "
                "What would you like to know?"
            )
        return f"Based on what I know: {formatted}"

    # Only use generic responses when no context is available at all
    if any(word in message_lower for word in ["hello", "hi", "hey"]):
        return (
            "Hello! I'm Muhammad Junayed's AI assistant. "
            "I can tell you about his projects, skills, research, and experience. "
            "What would you like to know?"
        )

    return (
        "I'm Muhammad Junayed's AI portfolio assistant. "
        "I can help you learn about his projects, skills, research, and background. "
        "Please ask me something specific!"
    )
