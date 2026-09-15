"""
TDD - Phase 2b: Generation Service tests.
Tests prompt building, output validation, and retry logic.
Uses the pre-crafted JSON fixture to avoid real Groq API calls.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models.generation import GenerationOutput, OutputType, Audience, Length, Style
from app.models.chunk import Chunk

FIXTURES = Path(__file__).parent / "fixtures" / "groq_responses"
POLICYMAKERS_FIXTURE = (FIXTURES / "policymakers_90s_script.json").read_text()


class TestGenerationService:

    @patch("app.services.generation_service.GenerationService._slide_count_valid", return_value=True)
    @patch("app.services.generation_service.GenerationService._call_groq")
    async def test_successful_generation_parses_json(self, mock_call, mock_valid):
        from app.services.generation_service import GenerationService
        svc = GenerationService()

        # Mock the Groq call to return our fixture
        mock_call.return_value = POLICYMAKERS_FIXTURE
        
        chunks = [
            Chunk(chunk_id="chunk-01", paper_id="p1", page_number=1, section_title="", block_index=0, text="text", contains_math=False, has_figure=False),
            Chunk(chunk_id="chunk-02", paper_id="p1", page_number=2, section_title="", block_index=1, text="text", contains_math=False, has_figure=False),
            Chunk(chunk_id="chunk-03", paper_id="p1", page_number=3, section_title="", block_index=2, text="text", contains_math=False, has_figure=False),
            Chunk(chunk_id="chunk-04", paper_id="p1", page_number=4, section_title="", block_index=3, text="text", contains_math=False, has_figure=False)
        ]

        result = await svc.generate(
            paper_id="p1",
            chunks=chunks,
            audience=Audience.POLICYMAKERS,
            length=Length.NINETY_SEC,
            style=Style.PLAIN_ENGLISH,
            output_type=OutputType.SPEAKER_SCRIPT
        )

        assert isinstance(result, GenerationOutput)
        assert result.audience == Audience.POLICYMAKERS
        assert len(result.slides) == 2
        assert result.slides[0].sentences[0].source_ids == ["chunk-01", "chunk-02"]

    @patch("app.services.generation_service.GenerationService._slide_count_valid", return_value=True)
    @patch("app.services.generation_service.GenerationService._call_groq")
    async def test_retry_on_low_citation_coverage(self, mock_call, mock_valid):
        from app.services.generation_service import GenerationService
        svc = GenerationService()

        # First call returns bad citations, second returns good citations
        bad_json = json.loads(POLICYMAKERS_FIXTURE)
        bad_json["slides"][0]["sentences"][0]["source_ids"] = [] # Remove citations
        bad_response = json.dumps(bad_json)
        
        good_response = POLICYMAKERS_FIXTURE

        mock_call.side_effect = [bad_response, good_response]

        chunks = [
            Chunk(chunk_id="chunk-01", paper_id="p1", page_number=1, section_title="", block_index=0, text="text", contains_math=False, has_figure=False),
            Chunk(chunk_id="chunk-02", paper_id="p1", page_number=2, section_title="", block_index=1, text="text", contains_math=False, has_figure=False),
            Chunk(chunk_id="chunk-03", paper_id="p1", page_number=3, section_title="", block_index=2, text="text", contains_math=False, has_figure=False),
            Chunk(chunk_id="chunk-04", paper_id="p1", page_number=4, section_title="", block_index=3, text="text", contains_math=False, has_figure=False)
        ]

        result = await svc.generate(
            paper_id="p1",
            chunks=chunks,
            audience=Audience.POLICYMAKERS,
            length=Length.NINETY_SEC,
            style=Style.PLAIN_ENGLISH,
            output_type=OutputType.SPEAKER_SCRIPT
        )
        
        # It should have retried and returned the good result
        assert mock_call.call_count == 2
        assert result.low_confidence is False
        assert result.slides[0].sentences[0].source_ids == ["chunk-01", "chunk-02"]

    @patch("app.services.generation_service.GenerationService._slide_count_valid", return_value=True)
    @patch("app.services.generation_service.GenerationService._call_groq")
    async def test_fallback_on_persistent_failure(self, mock_call, mock_valid):
        from app.services.generation_service import GenerationService
        svc = GenerationService()

        # All calls return bad citations
        bad_json = json.loads(POLICYMAKERS_FIXTURE)
        bad_json["slides"][0]["sentences"][0]["source_ids"] = []
        bad_response = json.dumps(bad_json)
        
        mock_call.side_effect = [bad_response, bad_response, bad_response]

        chunks = [
            Chunk(chunk_id="chunk-01", paper_id="p1", page_number=1, section_title="", block_index=0, text="text", contains_math=False, has_figure=False),
            Chunk(chunk_id="chunk-02", paper_id="p1", page_number=2, section_title="", block_index=1, text="text", contains_math=False, has_figure=False),
            Chunk(chunk_id="chunk-03", paper_id="p1", page_number=3, section_title="", block_index=2, text="text", contains_math=False, has_figure=False),
            Chunk(chunk_id="chunk-04", paper_id="p1", page_number=4, section_title="", block_index=3, text="text", contains_math=False, has_figure=False)
        ]

        result = await svc.generate(
            paper_id="p1",
            chunks=chunks,
            audience=Audience.POLICYMAKERS,
            length=Length.THIRTY_SEC,
            style=Style.PLAIN_ENGLISH,
            output_type=OutputType.SPEAKER_SCRIPT
        )
        
        # Low confidence should be true because both attempts failed citation threshold
        assert result.low_confidence is True
        assert result.citation_coverage < 0.80
