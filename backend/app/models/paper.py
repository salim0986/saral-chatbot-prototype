"""Pydantic models for paper ingestion."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class PaperStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class PaperResponse(BaseModel):
    paper_id: str
    status: PaperStatus
    filename: str


class PaperStatusResponse(BaseModel):
    paper_id: str
    status: PaperStatus
    chunk_count: int
    error_msg: Optional[str] = None
