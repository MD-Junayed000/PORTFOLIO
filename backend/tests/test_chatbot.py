"""Comprehensive unit tests for ``services.chatbot``.

Place this file at::

    backend/tests/test_chatbot.py

Run it from the repository root with::

    pytest backend/tests/test_chatbot.py -v

The tests do not make real Hugging Face or ChromaDB network calls. They mock
retrieval and API behavior while validating the chatbot's routing, cleaning,
fallback, retry, and response-generation logic.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest


# ---------------------------------------------------------------------------
# Import setup
# ---------------------------------------------------------------------------

def _find_backend_directory() -> Path:
    """Locate the backend directory without depending on the current shell path."""
    current_file = Path(__file__).resolve()
    candidates = [
        current_file.parent.parent,          # backend/tests/test_chatbot.py
        current_file.parent.parent / "backend",
        current_file.parent.parent.parent / "backend",
        Path.cwd() / "backend",
        Path.cwd(),
    ]

    for candidate in candidates:
        if (candidate / "services" / "chatbot.py").is_file():
            return candidate

    raise RuntimeError(
        "Could not locate backend/services/chatbot.py. "
        "Place this test at backend/tests/test_chatbot.py or run pytest "
        "from the repository root."
    )


BACKEND_DIR = _find_backend_directory()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Provide harmless defaults before importing application settings.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("HF_API_TOKEN", "")
os.environ.setdefault("HF_MODEL_ID", "test-model")

import services.chatbot as chatbot  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async function without requiring pytest-asyncio."""
    return asyncio.run(coro)


def fake_settings(token: str = "", model_id: str = "test-model") -> SimpleNamespace:
    return SimpleNamespace(
        HF_API_TOKEN=token,
        HF_MODEL_ID=model_id,
    )


def make_result(
    text: str,
    source: str = "Muhammad_Junayed_RAG_Knowledge_Base.pdf",
    **metadata: Any,
) -> Dict[str, Any]:
    combined_metadata = {"source": source, **metadata}
    return {
        "text": text,
        "metadata": combined_metadata,
        "distance": 0.1,
        "doc_id": "test-doc",
    }


class FakeResponse:
    """Minimal HTTP response used to test ``_call_hf_api``."""

    def __init__(
        self,
        status_code: int,
        payload: Any,
        text: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else str(payload)

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


class FakeAsyncClient:
    """Async context manager that returns queued fake HTTP responses."""

    def __init__(self, responses: List[FakeResponse]) -> None:
        self.responses = list(responses)
        self.posts: List[Dict[str, Any]] = []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(self, url: str, json: Dict, headers: Dict) -> FakeResponse:
        self.posts.append({"url": url, "json": json, "headers": headers})
        if not self.responses:
            raise AssertionError("No fake HTTP response remains")
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# Term matching and routing
# ---------------------------------------------------------------------------

class TestContainsTerm:
    def test_matches_complete_word(self):
        assert chatbot._contains_term("What are his skills?", "skills") is True

    def test_matches_phrase_with_flexible_whitespace(self):
        assert chatbot._contains_term("Show the game   score", "game score") is True

    def test_does_not_match_war_inside_award(self):
        assert chatbot._contains_term("What awards did he receive?", "war") is False

    def test_does_not_match_math_inside_mathematics(self):
        assert chatbot._contains_term("His mathematics coursework", "math") is False

    def test_is_case_insensitive(self):
        assert chatbot._contains_term("JUNAYED'S PROJECTS", "junayed") is True


class TestIsOffTopic:
    @pytest.mark.parametrize(
        "message",
        [
            "",
            "What is the weather today?",
            "Tell me a joke.",
            "Give me a recipe.",
            "Calculate 2 + 2.",
            "Who won the sports game?",
            "Write code for sorting numbers.",
            "What is the latest Bitcoin price?",
            "Do you like him?",
            "Where is pizza from?",
            "What city is the Eiffel Tower in?",
        ],
    )
    def test_off_topic_messages(self, message):
        assert chatbot._is_off_topic(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "Who is Junayed?",
            "Tell me about Muhammad Junayed.",
            "What are his skills?",
            "Tell me about his projects.",
            "What is his research about?",
            "Where does he live?",
            "What is his education?",
            "What awards has Junayed received?",
            "What mathematics coursework has he completed?",
            "What is his thesis title?",
            "What is his CGPA?",
            "Tell me about AroBot.",
            "What is the DOI of his wafer-map paper?",
            "What programming languages does he know?",
        ],
    )
    def test_portfolio_messages(self, message):
        assert chatbot._is_off_topic(message) is False


# ---------------------------------------------------------------------------
# Context cleaning for this exact RAG knowledge-base style
# ---------------------------------------------------------------------------

class TestCleanContextForLLM:
    def test_preserves_important_label_value_facts(self):
        context = (
            "• Full name: Muhammad Junayed\n"
            "• Location: Chattogram, Bangladesh\n"
            "• Professional email: mdjunayed573@gmail.com\n"
            "• CGPA: 3.51 out of 4.00\n"
            "• Expected graduation date: June, 2026"
        )
        result = chatbot._clean_context_for_llm(context)

        assert "Full name: Muhammad Junayed" in result
        assert "Location: Chattogram, Bangladesh" in result
        assert "Professional email: mdjunayed573@gmail.com" in result
        assert "CGPA: 3.51 out of 4.00" in result
        assert "Expected graduation date: June, 2026" in result
        assert "•" not in result

    def test_preserves_thesis_identity(self):
        context = (
            "• Title: Closing the Loop on RAG Hallucinations: "
            "Inference-Time Control via Dual Residual-Stream and FFN Activation Probes\n"
            "• Status: Ongoing undergraduate thesis\n"
            "• Supervisor: Priyonti Paul Tumpa"
        )
        result = chatbot._clean_context_for_llm(context)

        assert "Closing the Loop on RAG Hallucinations" in result
        assert "Ongoing undergraduate thesis" in result
        assert "Priyonti Paul Tumpa" in result

    def test_preserves_work_experience_fields(self):
        context = (
            "• Organization: Poridhi.io\n"
            "• Role: Software Engineer Intern\n"
            "• Duration: May 2025 to November 2025\n"
            "The internship involved backend development."
        )
        result = chatbot._clean_context_for_llm(context)

        assert "Organization: Poridhi.io" in result
        assert "Role: Software Engineer Intern" in result
        assert "Duration: May 2025 to November 2025" in result
        assert "backend development" in result

    def test_preserves_contact_and_repository_links(self):
        context = (
            "• LinkedIn: https://www.linkedin.com/in/muhammad-junayed-ete20/\n"
            "• GitHub: https://github.com/MD-Junayed000\n"
            "• Repository: https://github.com/MD-Junayed000/Bistro-92\n"
            "• Phone: +880 1876220119"
        )
        result = chatbot._clean_context_for_llm(context)

        assert "linkedin.com/in/muhammad-junayed-ete20" in result
        assert "github.com/MD-Junayed000" in result
        assert "github.com/MD-Junayed000/Bistro-92" in result
        assert "+880 1876220119" in result

    def test_preserves_short_skill_bullets(self):
        context = "• Python\n• C\n• C++\n• JavaScript\n• FastAPI\n• TensorFlow"
        result = chatbot._clean_context_for_llm(context)

        for skill in ("Python", "C", "C++", "JavaScript", "FastAPI", "TensorFlow"):
            assert skill in result
        assert "•" not in result

    def test_preserves_scores_ranks_and_qualifiers(self):
        context = (
            "• Best rank: 9th place in Tutor Identity\n"
            "• Best reported score: Exact F1 of 0.8621\n"
            "• Approximate AUPRC: 0.98\n"
            "The project reports accuracy of up to 99 percent.\n"
            "• Achievement: Finalist, as reported in the source CV"
        )
        result = chatbot._clean_context_for_llm(context)

        assert "9th place in Tutor Identity" in result
        assert "Exact F1 of 0.8621" in result
        assert "Approximate AUPRC: 0.98" in result
        assert "up to 99 percent" in result
        assert "as reported in the source CV" in result

    @pytest.mark.parametrize(
        "line",
        [
            "• Document ID: publication_wafer_map_cnn",
            "Document ID: project_arobot",
            "• Source: profile.pdf",
            "• Chunk ID: abc123",
            "• Chunk Index: 7",
        ],
    )
    def test_removes_internal_retrieval_fields(self, line):
        context = f"{line}\nMuhammad Junayed works on AI."
        result = chatbot._clean_context_for_llm(context)

        assert "Muhammad Junayed works on AI" in result
        assert "publication_wafer_map_cnn" not in result
        assert "project_arobot" not in result
        assert "abc123" not in result

    def test_removes_limitation_block(self):
        context = (
            "Main Result\n"
            "The model achieved 91.7 percent accuracy.\n"
            "Evaluation Limitation\n"
            "Exact per-class precision is not included in the provided sources.\n"
            "Final accuracy\n"
            "Confusion matrix\n"
            "Keywords\n"
            "wafer; CNN; Grad-CAM"
        )
        result = chatbot._clean_context_for_llm(context)

        assert "91.7 percent accuracy" in result
        assert "Evaluation Limitation" not in result
        assert "Exact per-class precision" not in result
        assert "Confusion matrix" not in result
        assert "wafer; CNN; Grad-CAM" not in result

    def test_removes_thesis_verification_instruction(self):
        context = (
            "The thesis is ongoing.\n"
            "Thesis Limitation in This Knowledge Source\n"
            "No final experiment should be claimed unless those details are added "
            "to a future verified version of this document."
        )
        result = chatbot._clean_context_for_llm(context)

        assert "The thesis is ongoing" in result
        assert "future verified version" not in result

    def test_removes_keyword_dump(self):
        context = (
            "Outcome\n"
            "A multimodal assistant was developed.\n"
            "Keywords\n"
            "Agentic RAG; multimodal chatbot; Ollama; Pinecone; OCR"
        )
        result = chatbot._clean_context_for_llm(context)

        assert "multimodal assistant was developed" in result
        assert "Agentic RAG; multimodal chatbot" not in result

    def test_removes_pdf_control_characters(self):
        context = "breast\u00adultrasound and defect\uffferecognition"
        result = chatbot._clean_context_for_llm(context)

        assert "\u00ad" not in result
        assert "\ufffe" not in result
        assert "breastultrasound" in result
        assert "defect-recognition" in result

    def test_preserves_narrative_after_internal_metadata(self):
        context = (
            "• Document ID: publication_001\n"
            "Junayed studies AI\n"
            "He also works on computer vision."
        )
        result = chatbot._clean_context_for_llm(context)

        assert "Junayed studies AI" in result
        assert "computer vision" in result

    def test_empty_context_returns_empty_string(self):
        assert chatbot._clean_context_for_llm("") == ""


# ---------------------------------------------------------------------------
# Generated-response cleaning
# ---------------------------------------------------------------------------

class TestCleanResponse:
    def test_empty_input_returns_graceful_message(self):
        result = chatbot._clean_response("")
        assert "could not generate" in result.lower() or "apologize" in result.lower()

    def test_removes_instruction_tokens(self):
        text = "<s>[INST] Muhammad Junayed works on AI. [/INST]</s>"
        result = chatbot._clean_response(text)

        for artifact in ("<s>", "</s>", "[INST]", "[/INST]"):
            assert artifact not in result

    def test_removes_internal_document_id(self):
        text = "Document ID: project_arobot\nMuhammad Junayed developed AroBot."
        result = chatbot._clean_response(text)

        assert "Document ID" not in result
        assert "project_arobot" not in result
        assert "developed AroBot" in result

    def test_removes_raw_source_line(self):
        text = (
            "Sources: Muhammad_Junayed_RAG_Knowledge_Base.pdf\n"
            "He is an AI researcher."
        )
        result = chatbot._clean_response(text)

        assert "Sources:" not in result
        assert "Muhammad_Junayed_RAG_Knowledge_Base.pdf" not in result
        assert "AI researcher" in result

    def test_removes_disclaimer_sentence_but_keeps_facts(self):
        text = (
            "Muhammad Junayed is a researcher at CUET. "
            "His exact responsibilities are not specified in the provided sources. "
            "He works on NLP and computer vision."
        )
        result = chatbot._clean_response(text)

        assert "not specified in the provided sources" not in result
        assert "researcher at CUET" in result
        assert "NLP and computer vision" in result

    def test_removes_section_header_prefix(self):
        text = "Main Result: The proposed CNN achieved 91.7 percent accuracy."
        result = chatbot._clean_response(text)

        assert "Main Result" not in result
        assert "91.7 percent accuracy" in result

    def test_removes_standalone_section_headers(self):
        text = (
            "Research Problem\n"
            "The work addresses wafer defects.\n"
            "Approach\n"
            "A CNN was trained."
        )
        result = chatbot._clean_response(text)

        assert "Research Problem" not in result
        assert "Approach" not in result
        assert "wafer defects" in result
        assert "CNN was trained" in result

    def test_preserves_natural_doi_sentence(self):
        text = (
            "The DOI of his wafer-map paper is "
            "https://doi.org/10.1109/ICAEEE62219.2024.10561853."
        )
        result = chatbot._clean_response(text)

        assert "10.1109/ICAEEE62219.2024.10561853" in result

    def test_preserves_natural_conference_sentence(self):
        text = "The paper was published at ICAEEE 2024 by IEEE."
        result = chatbot._clean_response(text)

        assert "ICAEEE 2024" in result
        assert "IEEE" in result

    def test_removes_duplicate_sentences_case_insensitively(self):
        text = (
            "He works on artificial intelligence. "
            "He works on artificial intelligence. "
            "He also studies NLP."
        )
        result = chatbot._clean_response(text)

        assert result.lower().count("he works on artificial intelligence.") == 1
        assert "He also studies NLP" in result

    def test_does_not_return_raw_bullet_metadata(self):
        text = (
            "• Document ID: x\n"
            "• Source: profile.pdf\n"
            "Muhammad Junayed is based in Chattogram."
        )
        result = chatbot._clean_response(text)

        assert "•" not in result
        assert "Document ID" not in result
        assert "based in Chattogram" in result

    def test_truncates_very_long_response(self):
        text = " ".join(
            f"Sentence {index} contains useful portfolio information."
            for index in range(100)
        )
        result = chatbot._clean_response(text)

        assert len(result) <= 1000
        assert result.strip()


# ---------------------------------------------------------------------------
# Prompt construction and extraction helpers
# ---------------------------------------------------------------------------

class TestPromptAndExtractionHelpers:
    def test_build_prompt_contains_question_and_context(self):
        prompt = chatbot._build_prompt(
            "What is his CGPA?",
            "CGPA: 3.51 out of 4.00",
        )

        assert "What is his CGPA?" in prompt
        assert "CGPA: 3.51 out of 4.00" in prompt
        assert "Muhammad Junayed" in prompt

    def test_extracts_labeled_urls(self):
        text = (
            "LinkedIn: https://www.linkedin.com/in/muhammad-junayed-ete20/\n"
            "GitHub: https://github.com/MD-Junayed000"
        )
        urls = chatbot._extract_urls(text)

        assert "linkedin" in urls
        assert "github" in urls
        assert "muhammad-junayed-ete20" in urls["linkedin"]
        assert "MD-Junayed000" in urls["github"]

    def test_extracts_standalone_scholar_url(self):
        text = "https://scholar.google.com/citations?user=wObQzNsAAAAJ&hl=en"
        urls = chatbot._extract_urls(text)

        assert "scholar" in urls

    def test_extracts_email(self):
        email = chatbot._extract_email(
            "Professional email: mdjunayed573@gmail.com"
        )
        assert email == "mdjunayed573@gmail.com"

    def test_extract_email_returns_none_when_absent(self):
        assert chatbot._extract_email("No email is present.") is None


# ---------------------------------------------------------------------------
# Fallback behavior
# ---------------------------------------------------------------------------

class TestFallbackResponse:
    def test_off_topic_fallback(self):
        result = chatbot._generate_fallback_response(
            "What is the weather?",
            "Muhammad Junayed works on AI.",
        )
        assert "portfolio" in result.lower() or "Muhammad Junayed" in result

    def test_linkedin_comes_from_retrieved_context(self):
        context = (
            "LinkedIn: "
            "https://www.linkedin.com/in/muhammad-junayed-ete20/"
        )
        result = chatbot._generate_fallback_response(
            "What is his LinkedIn?",
            context,
        )
        assert "muhammad-junayed-ete20" in result

    def test_cgpa_answer_uses_retrieved_value(self):
        context = (
            "Bachelor of Science in Electronics and Telecommunication Engineering\n"
            "CGPA: 3.51 out of 4.00\n"
            "CGPA coverage: Up to the seventh semester"
        )
        result = chatbot._generate_fallback_response(
            "What is his CGPA?",
            context,
        )
        assert "3.51" in result
        assert "4.00" in result

    def test_language_answer_preserves_pdf_wording(self):
        context = (
            "Bangla\nProficiency: Native\n\n"
            "English\nProficiency: Working and academic proficiency"
        )
        result = chatbot._generate_fallback_response(
            "What languages does he speak?",
            context,
        )
        assert "Bangla" in result
        assert "English" in result
        assert "working and academic" in result.lower()

    def test_unknown_fact_does_not_invent_answer(self):
        result = chatbot._generate_fallback_response(
            "What is his passport number?",
            "Muhammad Junayed is an ETE student at CUET.",
        )
        lowered = result.lower()
        assert (
            "do not have" in lowered
            or "don't have" in lowered
            or "not available" in lowered
            or "specific information" in lowered
        )

    def test_contact_answer_is_not_a_raw_metadata_dump(self):
        context = (
            "Professional email: mdjunayed573@gmail.com\n"
            "LinkedIn: https://www.linkedin.com/in/muhammad-junayed-ete20/\n"
            "GitHub: https://github.com/MD-Junayed000"
        )
        result = chatbot._generate_fallback_response(
            "How can I contact him?",
            context,
        )

        assert "mdjunayed573@gmail.com" in result
        assert "•" not in result
        assert "\n- " not in result


# ---------------------------------------------------------------------------
# Main orchestration: generate_response
# ---------------------------------------------------------------------------

class TestGenerateResponse:
    def test_greeting_bypasses_retrieval_and_api(self, monkeypatch):
        def forbidden_query(*args, **kwargs):
            raise AssertionError("Vector search should not run for greetings")

        async def forbidden_api(*args, **kwargs):
            raise AssertionError("HF API should not run for greetings")

        monkeypatch.setattr(chatbot, "vector_query", forbidden_query)
        monkeypatch.setattr(chatbot, "_call_hf_api", forbidden_api)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(chatbot.generate_response("Hello!"))

        assert "Hello" in result["response"]
        assert result["sources"] == []

    def test_off_topic_bypasses_retrieval_and_api(self, monkeypatch):
        def forbidden_query(*args, **kwargs):
            raise AssertionError("Vector search should not run off-topic")

        async def forbidden_api(*args, **kwargs):
            raise AssertionError("HF API should not run off-topic")

        monkeypatch.setattr(chatbot, "vector_query", forbidden_query)
        monkeypatch.setattr(chatbot, "_call_hf_api", forbidden_api)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(chatbot.generate_response("What is the weather?"))

        assert "portfolio" in result["response"].lower()
        assert result["sources"] == []

    def test_award_query_is_not_rejected_as_war(self, monkeypatch):
        calls = {"query": 0, "api": 0}

        def fake_query(question, n_results=5):
            calls["query"] += 1
            return [
                make_result(
                    "Awards and Achievements\nAchievement: Champion",
                )
            ]

        async def fake_api(prompt, timeout=45.0):
            calls["api"] += 1
            return "He was champion in the ETE Infixon Case Solving Competition."

        monkeypatch.setattr(chatbot, "vector_query", fake_query)
        monkeypatch.setattr(chatbot, "_call_hf_api", fake_api)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(
            chatbot.generate_response("What awards has Junayed received?")
        )

        assert calls == {"query": 1, "api": 1}
        assert "champion" in result["response"].lower()

    def test_missing_token_uses_fallback_with_cleaned_context(self, monkeypatch):
        captured = {}

        def fake_query(question, n_results=5):
            return [
                make_result(
                    "• Document ID: profile_1\n"
                    "• CGPA: 3.51 out of 4.00\n"
                    "• Expected graduation date: June, 2026"
                )
            ]

        def fake_fallback(message, context):
            captured["message"] = message
            captured["context"] = context
            return "Fallback answer."

        monkeypatch.setattr(chatbot, "vector_query", fake_query)
        monkeypatch.setattr(
            chatbot,
            "_generate_fallback_response",
            fake_fallback,
        )
        monkeypatch.setattr(chatbot, "settings", fake_settings(""))

        result = run_async(chatbot.generate_response("What is his CGPA?"))

        assert result["response"] == "Fallback answer."
        assert "Document ID" not in captured["context"]
        assert "CGPA: 3.51 out of 4.00" in captured["context"]
        assert "Expected graduation date: June, 2026" in captured["context"]

    def test_successful_api_receives_clean_context(self, monkeypatch):
        captured = {}

        def fake_query(question, n_results=5):
            return [
                make_result(
                    "• Document ID: thesis_1\n"
                    "• Title: Closing the Loop on RAG Hallucinations\n"
                    "• Status: Ongoing undergraduate thesis"
                )
            ]

        async def fake_api(prompt, timeout=45.0):
            captured["prompt"] = prompt
            captured["timeout"] = timeout
            return "His thesis studies hallucination detection in RAG systems."

        monkeypatch.setattr(chatbot, "vector_query", fake_query)
        monkeypatch.setattr(chatbot, "_call_hf_api", fake_api)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(
            chatbot.generate_response("What is his thesis about?")
        )

        assert "Document ID" not in captured["prompt"]
        assert "Closing the Loop on RAG Hallucinations" in captured["prompt"]
        assert "Ongoing undergraduate thesis" in captured["prompt"]
        assert "hallucination detection" in result["response"]

    def test_sources_are_deduplicated_in_retrieval_order(self, monkeypatch):
        def fake_query(question, n_results=5):
            return [
                make_result("First relevant chunk.", source="first.pdf"),
                make_result("Second relevant chunk.", source="second.pdf"),
                make_result("Third relevant chunk.", source="first.pdf"),
            ]

        async def fake_api(prompt, timeout=45.0):
            return "A grounded answer."

        monkeypatch.setattr(chatbot, "vector_query", fake_query)
        monkeypatch.setattr(chatbot, "_call_hf_api", fake_api)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(chatbot.generate_response("Tell me about Junayed."))

        assert result["sources"] == ["first.pdf", "second.pdf"]

    def test_first_api_failure_then_retry_success(self, monkeypatch):
        calls = []

        def fake_query(question, n_results=5):
            return [make_result("Muhammad Junayed works on AI.")]

        async def fake_api(prompt, timeout=45.0):
            calls.append(timeout)
            if len(calls) == 1:
                raise RuntimeError("Temporary API error")
            return "He works on artificial intelligence."

        async def no_sleep(seconds):
            return None

        monkeypatch.setattr(chatbot, "vector_query", fake_query)
        monkeypatch.setattr(chatbot, "_call_hf_api", fake_api)
        monkeypatch.setattr(chatbot.asyncio, "sleep", no_sleep)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(chatbot.generate_response("What does he work on?"))

        assert calls == [45.0, 20.0]
        assert "artificial intelligence" in result["response"]

    def test_double_api_failure_uses_fallback(self, monkeypatch):
        calls = {"api": 0, "fallback": 0}

        def fake_query(question, n_results=5):
            return [make_result("Muhammad Junayed works on NLP.")]

        async def failing_api(prompt, timeout=45.0):
            calls["api"] += 1
            raise RuntimeError("API unavailable")

        def fake_fallback(message, context):
            calls["fallback"] += 1
            assert "Muhammad Junayed works on NLP" in context
            return "He works on NLP."

        async def no_sleep(seconds):
            return None

        monkeypatch.setattr(chatbot, "vector_query", fake_query)
        monkeypatch.setattr(chatbot, "_call_hf_api", failing_api)
        monkeypatch.setattr(
            chatbot,
            "_generate_fallback_response",
            fake_fallback,
        )
        monkeypatch.setattr(chatbot.asyncio, "sleep", no_sleep)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(chatbot.generate_response("What is his research?"))

        assert calls == {"api": 2, "fallback": 1}
        assert result["response"] == "He works on NLP."

    def test_empty_retrieval_is_handled_without_invention(self, monkeypatch):
        def fake_query(question, n_results=5):
            return []

        async def fake_api(prompt, timeout=45.0):
            assert "No specific context available." in prompt
            return "I do not have that specific information."

        monkeypatch.setattr(chatbot, "vector_query", fake_query)
        monkeypatch.setattr(chatbot, "_call_hf_api", fake_api)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(
            chatbot.generate_response("What is his passport number?")
        )

        assert "specific information" in result["response"].lower()
        assert result["sources"] == []


# ---------------------------------------------------------------------------
# Hugging Face API adapter
# ---------------------------------------------------------------------------

class TestCallHuggingFaceAPI:
    def test_successful_generated_text_response(self, monkeypatch):
        client = FakeAsyncClient(
            [FakeResponse(200, [{"generated_text": "He works on AI."}])]
        )
        monkeypatch.setattr(
            chatbot.httpx,
            "AsyncClient",
            lambda timeout: client,
        )
        monkeypatch.setattr(chatbot, "settings", fake_settings("secret-token"))

        result = run_async(chatbot._call_hf_api("test prompt"))

        assert result == "He works on AI."
        assert len(client.posts) == 1
        request = client.posts[0]
        assert request["headers"]["Authorization"] == "Bearer secret-token"
        assert request["json"]["inputs"] == "test prompt"
        assert request["json"]["parameters"]["return_full_text"] is False

    def test_rate_limit_raises_clear_exception(self, monkeypatch):
        client = FakeAsyncClient(
            [FakeResponse(429, {"error": "rate limited"})]
        )
        monkeypatch.setattr(
            chatbot.httpx,
            "AsyncClient",
            lambda timeout: client,
        )
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        with pytest.raises(Exception, match="Rate limited"):
            run_async(chatbot._call_hf_api("test prompt"))

    def test_503_retries_once_then_succeeds(self, monkeypatch):
        client = FakeAsyncClient(
            [
                FakeResponse(503, {"error": "Model is loading"}),
                FakeResponse(200, [{"generated_text": "Ready now."}]),
            ]
        )

        async def no_sleep(seconds):
            return None

        monkeypatch.setattr(
            chatbot.httpx,
            "AsyncClient",
            lambda timeout: client,
        )
        monkeypatch.setattr(chatbot.asyncio, "sleep", no_sleep)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(chatbot._call_hf_api("test prompt"))

        assert result == "Ready now."
        assert len(client.posts) == 2

    def test_loading_message_in_non_503_response_retries(self, monkeypatch):
        client = FakeAsyncClient(
            [
                FakeResponse(500, {"error": "Model is loading"}),
                FakeResponse(200, [{"generated_text": "Loaded."}]),
            ]
        )

        async def no_sleep(seconds):
            return None

        monkeypatch.setattr(
            chatbot.httpx,
            "AsyncClient",
            lambda timeout: client,
        )
        monkeypatch.setattr(chatbot.asyncio, "sleep", no_sleep)
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(chatbot._call_hf_api("test prompt"))

        assert result == "Loaded."
        assert len(client.posts) == 2

    def test_unexpected_response_format_returns_graceful_message(self, monkeypatch):
        client = FakeAsyncClient(
            [FakeResponse(200, {"unexpected": "format"})]
        )
        monkeypatch.setattr(
            chatbot.httpx,
            "AsyncClient",
            lambda timeout: client,
        )
        monkeypatch.setattr(chatbot, "settings", fake_settings("token"))

        result = run_async(chatbot._call_hf_api("test prompt"))

        assert "could not generate" in result.lower() or "apologize" in result.lower()
