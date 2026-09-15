"""
Pydantic models for the Generation phase.
Defines the strict JSON schema expected from Groq and API request/response models.
"""

from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class Audience(str, Enum):
    POLICYMAKERS = "policymakers"
    RESEARCHERS = "researchers"
    STUDENTS = "students"
    GENERAL_PUBLIC = "general_public"


class Length(str, Enum):
    THIRTY_SEC = "30s"
    NINETY_SEC = "90s"
    FIVE_MIN = "5m"


class Style(str, Enum):
    PLAIN_ENGLISH = "plain_english"
    ACADEMIC = "academic"
    STORYTELLING = "storytelling"


class OutputType(str, Enum):
    SPEAKER_SCRIPT = "speaker_script"
    Q_AND_A = "q_and_a"
    BULLET_POINTS = "bullet_points"


# --- Groq Output Schema ---

class SourcedSentence(BaseModel):
    text: str
    source_ids: List[str] = Field(description="List of chunk_ids that support this sentence")
    source_pages: List[int] = Field(description="List of page numbers corresponding to the chunk_ids")

class Slide(BaseModel):
    slide_number: int
    title: str
    bullets: List[str]
    script: str
    speaker_notes: str
    sentences: List[SourcedSentence]

class GenerationOutput(BaseModel):
    """The exact schema Groq is instructed to return."""
    output_type: OutputType
    audience: Audience
    length: Length
    slides: List[Slide]
    citation_coverage: float = Field(0.0, description="Percentage of sentences that have valid citations")
    low_confidence: bool = Field(False, description="True if generation failed strict validation checks")


# --- API Request/Response Models ---

class GenerateRequest(BaseModel):
    paper_id: str
    audience: Audience
    length: Length
    style: Style
    output_type: OutputType

class SessionCreateRequest(BaseModel):
    paper_id: str
