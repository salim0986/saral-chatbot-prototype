import json
from unittest.mock import patch, MagicMock

import pytest

from app.models.chunk import Chunk
from app.models.generation import GenerationOutput, OutputType, Audience, Length, Style, Slide, SourcedSentence
from app.models.refine import RefinedTextOutput, DiffHunk
from app.services.change_tracking_service import ChangeTrackingService


@pytest.fixture
def sample_old_output():
    return GenerationOutput(
        output_type=OutputType.SPEAKER_SCRIPT,
        audience=Audience.POLICYMAKERS,
        length=Length.NINETY_SEC,
        slides=[
            Slide(
                slide_number=1,
                title="Intro",
                bullets=["Intro bullet"],
                script="This is the intro.",
                speaker_notes="",
                sentences=[]
            ),
            Slide(
                slide_number=2,
                title="Technical Detail",
                bullets=["A technical point"],
                script="The transformer attention mechanism computes scaled dot-product.",
                speaker_notes="Speak slowly",
                sentences=[
                    SourcedSentence(text="The transformer attention mechanism computes scaled dot-product.", source_ids=["chunk-01"], source_pages=[1])
                ]
            )
        ],
        citation_coverage=1.0,
        low_confidence=False
    )

@pytest.fixture
def sample_chunks():
    return [
        Chunk(chunk_id="chunk-01", paper_id="p1", page_number=1, section_title="", block_index=0, text="text1", contains_math=False, has_figure=False),
        Chunk(chunk_id="chunk-02", paper_id="p1", page_number=1, section_title="", block_index=1, text="spotlight analogy", contains_math=False, has_figure=False),
    ]

class TestChangeTrackingService:
    @patch("app.services.change_tracking_service.ChangeTrackingService._call_llm_with_cache")
    async def test_apply_delta_computes_diff_and_new_version(self, mock_call, sample_old_output, sample_chunks):
        svc = ChangeTrackingService()

        # Mock LLM response
        refined = RefinedTextOutput(
            revised_text="Think of attention like a spotlight.",
            reason="Replaced technical mechanism description with an analogy"
        )
        mock_call.return_value = refined.model_dump_json()

        delta, new_output = await svc.apply_delta(
            session_id="session_123",
            version_from=1,
            version_to=2,
            old_output=sample_old_output,
            target_slide_number=2,
            change_instruction="Make it less technical",
            valid_chunks=sample_chunks
        )

        # Check delta
        assert delta.session_id == "session_123"
        assert delta.version_from == 1
        assert delta.version_to == 2
        assert delta.slide_number == 2
        assert delta.reason == refined.reason
        assert delta.reason == refined.reason
        assert delta.provenance == []
        
        # Check difflib hunks
        assert any(h.operation == "delete" for h in delta.diff_hunks)
        assert any(h.operation == "insert" for h in delta.diff_hunks)

        # Check new output
        assert len(new_output.slides) == 2
        assert new_output.slides[1].script == "Think of attention like a spotlight."
        assert new_output.citation_coverage == 0.0

    async def test_apply_delta_raises_on_invalid_slide_number(self, sample_old_output, sample_chunks):
        svc = ChangeTrackingService()
        
        with pytest.raises(ValueError, match="Target slide 99 not found"):
            await svc.apply_delta(
                session_id="session_123",
                version_from=1,
                version_to=2,
                old_output=sample_old_output,
                target_slide_number=99, # Invalid
                change_instruction="Make it less technical",
                valid_chunks=sample_chunks
            )

    def test_compute_diff_with_latex_characters(self):
        svc = ChangeTrackingService()
        old_text = "The equation is $E = mc^2$ and it's very important."
        new_text = "The formula is $E = mc^2$ and it is crucial."
        
        hunks = svc._compute_diff(old_text, new_text)
        
        assert any(h.operation == "insert" and "formula" in h.text for h in hunks)
        assert any(h.operation == "delete" and "equation" in h.text for h in hunks)
        
        # Verify the latex chunk is preserved as equal
        assert any(h.operation == "equal" and "$E = mc^2$" in h.text for h in hunks)
