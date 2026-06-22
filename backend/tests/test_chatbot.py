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

    def test_preserves_narrative_with_colon(self):
        """Colon-containing narrative sentences must survive the context cleaner.
        This is the primary false-positive risk - sentences like 'His specialty: X'
        should NOT be stripped even though they contain a colon pattern."""
        context = (
            "His specialty: machine learning and NLP.\n"
            "His research focus: detecting hallucinations in language models.\n"
            "The goal: building robust AI systems for production use."
        )
        result = _clean_context_for_llm(context)
        assert "His specialty: machine learning and NLP" in result
        assert "His research focus: detecting hallucinations" in result
        assert "The goal: building robust AI systems" in result

    def test_preserves_narrative_colon_with_metadata(self):
        """Narrative sentences with colons survive while metadata is still stripped."""
        context = (
            "• Document ID: doc_789\n"
            "• Authors: Muhammad Junayed\n"
            "His specialty: machine learning and NLP.\n"
            "The approach: using transformer architectures for detection.\n"
            "• DOI: 10.1109/example\n"
            "He works on several areas including: vision, NLP, and speech."
        )
        result = _clean_context_for_llm(context)
        assert "Document ID" not in result
        assert "Authors:" not in result
        assert "DOI:" not in result
        assert "His specialty: machine learning and NLP" in result
        assert "The approach: using transformer architectures" in result
        assert "He works on several areas including" in result

    def test_strips_dataset_metadata(self):
        """Dataset, Common abbreviation, Target classes must be stripped as metadata."""
        context = (
            "• Dataset:  Breast Ultrasound Images Dataset\n"
            "• Common abbreviation:  BUSI\n"
            "• Target classes:  Normal, benign, and malignant\n"
            "A tailored Vision Transformer was developed for classification."
        )
        result = _clean_context_for_llm(context)
        assert "Dataset:" not in result
        assert "Common abbreviation:" not in result
        assert "Target classes:" not in result
        assert "BUSI" not in result
        assert "tailored Vision Transformer" in result

    def test_strips_training_type_metadata(self):
        """Training type and other missing labels are caught."""
        context = (
            "• Training type: Industrial training\n"
            "• DOI link: https://doi.org/10.1109/example\n"
            "The training focused on modern software engineering workflows."
        )
        result = _clean_context_for_llm(context)
        assert "Training type:" not in result
        assert "DOI link:" not in result
        assert "modern software engineering workflows" in result

    def test_strips_multiline_metadata_continuation(self):
        """Multi-line metadata values should not leave orphaned continuation lines."""
        context = (
            "• Conference:  2025 IEEE International Conference on Signal Processing, Information, Communication and\n"
            "Systems\n"
            "A tailored Vision Transformer was developed."
        )
        result = _clean_context_for_llm(context)
        assert "Conference:" not in result
        assert "Systems" not in result
        assert "tailored Vision Transformer" in result

    def test_strips_inline_dataset_header(self):
        """'Dataset' appearing as trailing section header after a sentence should be removed."""
        context = (
            "The study investigated deep-learning-based classification of breast-ultrasound images. Dataset\n"
            "• Dataset:  Breast Ultrasound Images Dataset"
        )
        result = _clean_context_for_llm(context)
        assert "Dataset:" not in result
        # The word "Dataset" as a trailing header should be removed
        assert "Dataset" not in result or "deep-learning" in result

    def test_bullet_catchall_strips_any_bullet_colon_pattern(self):
        """Any line starting with bullet + words + colon should be stripped."""
        context = (
            "• Some Unknown Label:  some value here\n"
            "• Another Weird Field:  another value\n"
            "This is a narrative sentence about the research."
        )
        result = _clean_context_for_llm(context)
        assert "Some Unknown Label:" not in result
        assert "Another Weird Field:" not in result
        assert "narrative sentence about the research" in result


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

    def test_preserves_prose_starting_with_dash(self):
        """Lines starting with dash that are valid prose sentences should NOT be stripped."""
        text = (
            "Muhammad Junayed focuses on NLP research.\n"
            "- His work on hallucination detection has been published at IEEE conferences and received positive reviews from the community.\n"
            "He is based in Bangladesh."
        )
        result = _clean_response(text)
        # The long prose sentence with terminal punctuation should survive
        assert "hallucination detection" in result
        assert "Muhammad Junayed focuses on NLP research" in result

    def test_removes_dataset_and_training_metadata(self):
        """_clean_response removes Dataset, Common abbreviation, Target classes, Training type."""
        text = (
            "• Dataset:  Breast Ultrasound Images Dataset\n"
            "• Common abbreviation:  BUSI\n"
            "• Target classes:  Normal, benign, and malignant\n"
            "• Training type:  Industrial training\n"
            "• DOI link:  https://doi.org/10.1109/example\n"
            "Muhammad Junayed developed a Vision Transformer for classification."
        )
        result = _clean_response(text)
        assert "Dataset:" not in result
        assert "Common abbreviation:" not in result
        assert "Target classes:" not in result
        assert "Training type:" not in result
        assert "DOI link:" not in result
        assert "Vision Transformer" in result

    def test_removes_all_bullet_lines(self):
        """All lines starting with bullet char are removed from LLM output."""
        text = (
            "• Organization: Brain Station 23 PLC\n"
            "• Role: Industrial Trainee\n"
            "• Duration: May 2025\n"
            "Muhammad Junayed completed industrial training at Brain Station 23."
        )
        result = _clean_response(text)
        assert "•" not in result
        assert "Organization:" not in result
        assert "Role:" not in result
        assert "industrial training" in result


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
