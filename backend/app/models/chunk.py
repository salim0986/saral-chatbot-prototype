"""Pydantic models for document chunks stored in Qdrant + SQLite."""

from typing import Optional
from pydantic import BaseModel


class Chunk(BaseModel):
    chunk_id: str
    paper_id: str
    page_number: int
    section_title: str
    block_index: int
    text: str
    contains_math: bool
    has_figure: bool
    figure_caption: Optional[str] = None
    # Dense + sparse vectors are stored directly in Qdrant payload - not here.
