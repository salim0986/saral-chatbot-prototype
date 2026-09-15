"""
ChunkingService - math-aware, heading-aware sliding-window chunker.
No external dependencies: only stdlib (re, uuid) and pydantic models.
"""

import re
import uuid
from collections import defaultdict

from app.models.chunk import Chunk

# ── Token/char budgets ────────────────────────────────────────────────────────
# Approximation: 1 token ≈ 4 characters
MAX_CHARS = 512 * 4        # 2048 chars  (~512 tokens)
OVERLAP_CHARS = 64 * 4     # 256 chars   (~64 tokens overlap)

# ── Math block patterns (ordered: larger blocks first) ───────────────────────
# These are ATOMIC - the chunker never cuts inside them.
_BLOCK_MATH_PATTERNS = [
    re.compile(r'\\begin\{equation\*?\}.*?\\end\{equation\*?\}', re.DOTALL),
    re.compile(r'\\begin\{align\*?\}.*?\\end\{align\*?\}', re.DOTALL),
    re.compile(r'\\begin\{gather\*?\}.*?\\end\{gather\*?\}', re.DOTALL),
    re.compile(r'\\begin\{multline\*?\}.*?\\end\{multline\*?\}', re.DOTALL),
    re.compile(r'\$\$.*?\$\$', re.DOTALL),    # display math $$...$$
]

_INLINE_MATH_PATTERN = re.compile(r'\$[^$\n]+?\$')  # inline math $...$

# ── Heading splitter ──────────────────────────────────────────────────────────
_HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# ── Figure caption ────────────────────────────────────────────────────────────
_FIGURE_PATTERN = re.compile(
    r'\[?[Ff]igure\s+\d+[:\.]?\]?\s*(.+?)(?:\n|$)'
)


def _find_math_ranges(text: str) -> list[tuple[int, int]]:
    """Return (start, end) character ranges of all math blocks in text."""
    ranges = []
    for pattern in _BLOCK_MATH_PATTERNS + [_INLINE_MATH_PATTERN]:
        for match in pattern.finditer(text):
            ranges.append((match.start(), match.end()))
    # Merge overlapping ranges
    ranges.sort()
    merged = []
    for start, end in ranges:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _is_inside_range(pos: int, ranges: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Return the range (start, end) if pos falls inside any range, else None."""
    for start, end in ranges:
        if start < pos < end:
            return (start, end)
    return None


def _sliding_window_split(
    text: str,
    math_ranges: list[tuple[int, int]],
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[str]:
    """
    Split text into chunks of at most max_chars, never cutting inside a math range.
    Adjacent chunks share overlap_chars of context.
    """
    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + max_chars, text_len)

        # Push end forward if it falls inside a math block
        inside = _is_inside_range(end, math_ranges)
        if inside:
            end = inside[1]

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(chunk_text)

        if end >= text_len:
            break

        # Compute next start with overlap
        next_start = end - overlap_chars

        # Pull next_start back if it falls inside a math block
        inside = _is_inside_range(next_start, math_ranges)
        if inside:
            next_start = inside[0]

        # Guarantee forward progress
        start = max(next_start, start + 1)

    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """
    Split markdown text by headings.
    Returns list of (section_title, section_body) tuples.
    Preserves content before the first heading under title ''.
    """
    sections = []
    last_end = 0
    current_title = ""

    for match in _HEADING_PATTERN.finditer(text):
        body = text[last_end:match.start()].strip()
        if body or current_title:
            sections.append((current_title, body))
        current_title = match.group(2).strip()
        last_end = match.end()

    # Remaining text after last heading
    remaining = text[last_end:].strip()
    if remaining or current_title:
        sections.append((current_title, remaining))

    return [(title, body) for title, body in sections if body.strip()]


class ChunkingService:
    """
    Converts a Markdown document into a list of Chunks.
    Guarantees: math blocks are never split across chunk boundaries.
    """

    def chunk(self, markdown: str, paper_id: str) -> list[Chunk]:
        """
        Main entry point. Splits markdown into Chunks with full metadata.

        Args:
            markdown: The document content as Markdown text.
            paper_id: UUID of the parent paper in SQLite.

        Returns:
            List of Chunk objects ready for embedding.
        """
        if not markdown or not markdown.strip():
            return []

        sections = _split_by_headings(markdown)
        result: list[Chunk] = []
        section_block_counters: dict[str, int] = defaultdict(int)

        for section_title, section_body in sections:
            math_ranges = _find_math_ranges(section_body)
            text_segments = _sliding_window_split(section_body, math_ranges)

            for segment in text_segments:
                if not segment.strip():
                    continue

                has_math = bool(_find_math_ranges(segment))
                figure_caption = self._extract_figure_caption(segment)

                result.append(Chunk(
                    chunk_id=str(uuid.uuid4()),
                    paper_id=paper_id,
                    page_number=0,          # updated by IngestionService from Docling metadata
                    section_title=section_title,
                    block_index=section_block_counters[section_title],
                    text=segment,
                    contains_math=has_math,
                    has_figure=figure_caption is not None,
                    figure_caption=figure_caption,
                ))
                section_block_counters[section_title] += 1

        return result

    def _extract_figure_caption(self, text: str) -> str | None:
        """Return the first figure caption found in a chunk, or None."""
        match = _FIGURE_PATTERN.search(text)
        if match:
            caption = match.group(1).strip()
            return caption if caption else None
        return None
