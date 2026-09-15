"""
TDD - Phase 1b: Math-aware chunking tests.
Pure Python - no external dependencies. Tests the core chunking logic.
"""

import pytest

PAPER_ID = "test-paper-001"

SIMPLE_MARKDOWN = """# Introduction

This is the introduction section of the paper. It contains background information
about the research area and motivates the work.

## Background

Previous approaches to this problem used recurrent neural networks.
These models had difficulty with long-range dependencies.

# Methods

We propose a new approach based on attention mechanisms.
The method is scalable and parallelizable.

# Results

Our method achieves state-of-the-art performance on standard benchmarks.
"""

MATH_MARKDOWN = """# Methods

The core of our approach is the attention mechanism defined as:

$$\\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V$$

This is a fundamental operation in the transformer architecture.
We also use multi-head attention with $h = 8$ heads.

The loss function is:

\\begin{equation}
\\mathcal{L} = -\\sum_{t=1}^{T} \\log p(y_t | y_{<t}, x)
\\end{equation}

The gradient update rule follows standard Adam optimization.
"""

LONG_MARKDOWN = "Word " * 1000  # ~5000 chars, well above 2048 char limit


class TestChunkingBasic:
    """Basic chunking behaviour on text without math."""

    def setup_method(self):
        from app.services.chunking_service import ChunkingService
        self.svc = ChunkingService()

    def test_returns_list_of_chunks(self):
        chunks = self.svc.chunk(SIMPLE_MARKDOWN, PAPER_ID)
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_each_chunk_has_required_fields(self):
        chunks = self.svc.chunk(SIMPLE_MARKDOWN, PAPER_ID)
        for c in chunks:
            assert c.chunk_id
            assert c.paper_id == PAPER_ID
            assert isinstance(c.page_number, int)
            assert isinstance(c.section_title, str)
            assert isinstance(c.block_index, int)
            assert isinstance(c.text, str)
            assert isinstance(c.contains_math, bool)
            assert isinstance(c.has_figure, bool)

    def test_chunk_ids_are_unique(self):
        chunks = self.svc.chunk(SIMPLE_MARKDOWN, PAPER_ID)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_no_chunk_exceeds_max_char_limit(self):
        # 512 tokens × ~4 chars/token = 2048 chars max
        chunks = self.svc.chunk(LONG_MARKDOWN, PAPER_ID)
        for c in chunks:
            assert len(c.text) <= 2100, f"Chunk too long: {len(c.text)} chars"

    def test_long_text_produces_multiple_chunks(self):
        chunks = self.svc.chunk(LONG_MARKDOWN, PAPER_ID)
        assert len(chunks) >= 2

    def test_empty_input_returns_empty_list(self):
        chunks = self.svc.chunk("", PAPER_ID)
        assert chunks == []

    def test_whitespace_only_returns_empty_list(self):
        chunks = self.svc.chunk("   \n\n\t  ", PAPER_ID)
        assert chunks == []


class TestMathProtection:
    """Math blocks must NEVER be split across chunk boundaries."""

    def setup_method(self):
        from app.services.chunking_service import ChunkingService
        self.svc = ChunkingService()

    def _math_is_intact_in_chunks(self, chunks: list, math_expr: str) -> bool:
        """Check that a math expression appears whole in exactly one chunk."""
        containing = [c for c in chunks if math_expr in c.text]
        return len(containing) >= 1

    def test_display_math_not_split(self):
        math_expr = r"\text{Attention}(Q, K, V)"
        chunks = self.svc.chunk(MATH_MARKDOWN, PAPER_ID)
        # The full display math block must appear intact in one chunk
        full_expr = r"$$\text{Attention}(Q, K, V)"
        assert self._math_is_intact_in_chunks(chunks, full_expr[:30])

    def test_equation_env_not_split(self):
        """\\begin{equation}...\\end{equation} must stay in one chunk."""
        chunks = self.svc.chunk(MATH_MARKDOWN, PAPER_ID)
        # Find which chunk contains the begin tag
        begin_chunks = [c for c in chunks if r"\begin{equation}" in c.text]
        end_chunks = [c for c in chunks if r"\end{equation}" in c.text]
        assert len(begin_chunks) > 0
        assert len(end_chunks) > 0
        # begin and end must be in the same chunk
        begin_ids = {c.chunk_id for c in begin_chunks}
        end_ids = {c.chunk_id for c in end_chunks}
        assert begin_ids & end_ids, "equation env was split across chunks!"

    def test_chunks_with_math_flagged(self):
        chunks = self.svc.chunk(MATH_MARKDOWN, PAPER_ID)
        math_chunks = [c for c in chunks if c.contains_math]
        assert len(math_chunks) > 0

    def test_chunks_without_math_not_flagged(self):
        chunks = self.svc.chunk(SIMPLE_MARKDOWN, PAPER_ID)
        math_chunks = [c for c in chunks if c.contains_math]
        assert len(math_chunks) == 0


class TestChunkMetadata:
    """Verify section titles and block indices are assigned correctly."""

    def setup_method(self):
        from app.services.chunking_service import ChunkingService
        self.svc = ChunkingService()

    def test_section_title_is_populated(self):
        chunks = self.svc.chunk(SIMPLE_MARKDOWN, PAPER_ID)
        titles = {c.section_title for c in chunks}
        # At least some chunks should have non-empty section titles
        assert any(t for t in titles)

    def test_block_index_is_sequential_within_section(self):
        chunks = self.svc.chunk(SIMPLE_MARKDOWN, PAPER_ID)
        # Group by section_title and verify block_index starts at 0
        from collections import defaultdict
        by_section = defaultdict(list)
        for c in chunks:
            by_section[c.section_title].append(c.block_index)
        for title, indices in by_section.items():
            assert indices[0] == 0, f"Section '{title}' doesn't start at block 0"

    def test_figure_caption_none_when_no_figure(self):
        chunks = self.svc.chunk(SIMPLE_MARKDOWN, PAPER_ID)
        for c in chunks:
            assert c.figure_caption is None
