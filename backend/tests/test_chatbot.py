"""Unit tests for chatbot service functions."""
import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment variables BEFORE importing
os.environ["TESTING"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

from services.chatbot import _clean_context_for_llm, _clean_response, _is_off_topic


class TestCleanContextForLLM:
    """Test _clean_context_for_llm strips metadata and keeps narrative text."""

    def test_strips_document_id(self):
        context = "• Document ID: doc_123\nJunayed is an AI researcher."
        result = _clean_context_for_llm(context)
        assert "Document ID" not in result
        assert "doc_123" not in result
        assert "Junayed is an AI researcher" in result

    def test_strips_authors_metadata(self):
        context = "• Authors: Muhammad Junayed, John Doe\nHe published at IEEE."
        result = _clean_context_for_llm(context)
        assert "Authors:" not in result
        assert "He published at IEEE" in result

    def test_strips_conference_metadata(self):
        context = "• Conference: ICAEEE 2024\n• DOI: 10.1109/xyz\nThe paper studies hallucinations."
        result = _clean_context_for_llm(context)
        assert "Conference:" not in result
        assert "DOI:" not in result
        assert "The paper studies hallucinations" in result

    def test_strips_publisher_pages(self):
        context = "• Publisher: IEEE\n• Pages: 1-6\nThis work focuses on NLP."
        result = _clean_context_for_llm(context)
        assert "Publisher:" not in result
        assert "Pages:" not in result
        assert "This work focuses on NLP" in result

    def test_strips_multiple_metadata_lines(self):
        context = (
            "• Document ID: pub_001\n"
            "• Authors: Muhammad Junayed\n"
            "• Conference: ICAEEE 2024\n"
            "• DOI: 10.1109/ICAEEE62219.2024.10561848\n"
            "• Publisher: IEEE\n"
            "• Pages: 1-5\n"
            "• Publication date: 2024\n"
            "• Code repository: https://github.com/example\n"
            "\n"
            "This research addresses hallucination detection in LLMs."
        )
        result = _clean_context_for_llm(context)
        assert "Document ID" not in result
        assert "Authors:" not in result
        assert "Conference:" not in result
        assert "DOI:" not in result
        assert "Publisher:" not in result
        assert "Pages:" not in result
        assert "Publication date:" not in result
        assert "Code repository:" not in result
        assert "This research addresses hallucination detection" in result

    def test_strips_standalone_urls(self):
        context = "https://doi.org/10.1109/xyz\nJunayed studies AI."
        result = _clean_context_for_llm(context)
        assert "https://doi.org" not in result
        assert "Junayed studies AI" in result

    def test_strips_information_not_provided(self):
        context = "Information Not Provided\nJunayed is a student."
        result = _clean_context_for_llm(context)
        assert "Information Not Provided" not in result
        assert "Junayed is a student" in result

    def test_strips_section_headers(self):
        context = "Research Problem\nThe paper addresses hallucination.\nApproach\nUsing probes."
        result = _clean_context_for_llm(context)
        assert result.strip().startswith("The paper addresses")
        # "Research Problem" as standalone header should be removed
        assert "Research Problem" not in result or "addresses" in result

    def test_keeps_narrative_text(self):
        context = (
            "Muhammad Junayed is a final-year ETE student at CUET. "
            "He specializes in AI and machine learning. "
            "His research focuses on NLP and computer vision."
        )
        result = _clean_context_for_llm(context)
        assert "Muhammad Junayed is a final-year ETE student" in result
        assert "specializes in AI" in result

    def test_strips_metadata_without_bullet(self):
        context = "Document ID: doc_456\nAuthors: Someone\nThis is a narrative sentence."
        result = _clean_context_for_llm(context)
        assert "Document ID:" not in result
        assert "Authors:" not in result
        assert "This is a narrative sentence" in result

    def test_strips_images_keyword(self):
        context = "Images\nThe project uses CNN architectures."
        result = _clean_context_for_llm(context)
        assert "Images" not in result
        assert "CNN architectures" in result


class TestCleanResponse:
    """Test _clean_response removes metadata echoed by the LLM."""

    def test_removes_document_id_line(self):
        text = "Document ID: pub_001\nJunayed published a paper on NLP."
        result = _clean_response(text)
        assert "Document ID" not in result
        assert "Junayed published a paper on NLP" in result

    def test_removes_authors_line(self):
        text = "Authors: Muhammad Junayed, John Doe\nThe paper is about hallucination detection."
        result = _clean_response(text)
        assert "Authors:" not in result
        assert "hallucination detection" in result

    def test_removes_conference_and_doi(self):
        text = (
            "Conference: ICAEEE 2024\n"
            "DOI: 10.1109/xyz\n"
            "The research focuses on LLMs."
        )
        result = _clean_response(text)
        assert "Conference:" not in result
        assert "DOI:" not in result
        assert "The research focuses on LLMs" in result

    def test_removes_bullet_points(self):
        text = "• He has skills in Python\n• He knows machine learning\nJunayed is skilled in AI."
        result = _clean_response(text)
        assert "•" not in result
        assert "Junayed is skilled in AI" in result

    def test_removes_section_headers(self):
        text = "Research Problem\nThe work addresses X.\nApproach\nThey use Y."
        result = _clean_response(text)
        # Section headers alone on a line should be removed
        lines = [l.strip() for l in result.split('\n') if l.strip()]
        for line in lines:
            assert line.lower() not in ("research problem", "approach")

    def test_removes_sources_line(self):
        text = "Sources: Muhammad_Junayed_RAG_Knowledge_Base.pdf\nHe is a researcher."
        result = _clean_response(text)
        assert "Sources:" not in result
        assert "Muhammad_Junayed_RAG_Knowledge_Base.pdf" not in result
        assert "researcher" in result

    def test_removes_multiple_metadata_types(self):
        text = (
            "• Document ID: pub_001\n"
            "• Authors: Junayed\n"
            "• Conference: ICAEEE\n"
            "• DOI: 10.1109/abc\n"
            "• Publisher: IEEE\n"
            "• Pages: 1-5\n"
            "Muhammad Junayed presented a paper on hallucination detection at ICAEEE 2024."
        )
        result = _clean_response(text)
        assert "Document ID" not in result
        assert "Authors:" not in result
        assert "Publisher:" not in result
        assert "Pages:" not in result
        assert "hallucination detection" in result

    def test_empty_input_returns_fallback(self):
        result = _clean_response("")
        assert "could not generate" in result.lower() or "apologize" in result.lower()

    def test_preserves_natural_sentences(self):
        text = "Muhammad Junayed is a final-year student at CUET. He specializes in AI and NLP."
        result = _clean_response(text)
        assert "Muhammad Junayed is a final-year student" in result
        assert "specializes in AI" in result


class TestIsOffTopic:
    """Test _is_off_topic correctly identifies off-topic vs on-topic questions."""

    def test_is_he_ok_is_off_topic(self):
        """'is he ok?' should be off-topic - bare pronoun without portfolio context."""
        assert _is_off_topic("is he ok?") is True

    def test_where_does_he_live_is_on_topic(self):
        """'where does he live?' should be on-topic - contains 'live' keyword."""
        assert _is_off_topic("where does he live?") is False

    def test_weather_is_off_topic(self):
        assert _is_off_topic("what is the weather?") is True

    def test_sports_is_off_topic(self):
        assert _is_off_topic("who won the sports game?") is True

    def test_recipe_is_off_topic(self):
        assert _is_off_topic("give me a recipe") is True

    def test_skills_question_is_on_topic(self):
        assert _is_off_topic("what are his skills?") is False

    def test_project_question_is_on_topic(self):
        assert _is_off_topic("tell me about his projects") is False

    def test_research_question_is_on_topic(self):
        assert _is_off_topic("what is his research about?") is False

    def test_junayed_question_is_on_topic(self):
        assert _is_off_topic("who is Junayed?") is False

    def test_short_generic_is_off_topic(self):
        """Short questions without portfolio keywords are off-topic."""
        assert _is_off_topic("how are you?") is True

    def test_calculate_is_off_topic(self):
        assert _is_off_topic("calculate 2 + 2") is True

    def test_education_is_on_topic(self):
        assert _is_off_topic("what is his education?") is False

    def test_experience_is_on_topic(self):
        assert _is_off_topic("tell me about his work experience") is False

    def test_bare_him_is_off_topic(self):
        """'do you like him?' - bare pronoun without portfolio context is off-topic."""
        assert _is_off_topic("do you like him?") is True

    def test_his_with_portfolio_keyword_is_on_topic(self):
        """'his' combined with portfolio keywords is on-topic."""
        assert _is_off_topic("what is his background?") is False
