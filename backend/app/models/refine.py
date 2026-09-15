"""
Models for Phase 3: Change Tracking & Iterative Refinement.
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field, model_validator


from app.models.generation import Slide

class RefineRequest(BaseModel):
    change_instruction: str = Field(..., description="The user's instructions for what to change")
    target_slide: int = Field(..., description="Which slide number to target for refinement")


class RefinedTextOutput(BaseModel):
    revised_text: str = Field(..., description="The fully revised text for the slide based on the instruction")
    reason: str = Field(..., description="Explanation of what was changed and why")

    @model_validator(mode='before')
    @classmethod
    def inject_default_reason(cls, data: Any) -> Any:
        if isinstance(data, dict) and 'reason' not in data:
            data['reason'] = "Refined based on user instruction (auto-generated reason)"
        return data


class DiffHunk(BaseModel):
    operation: str = Field(..., description="'insert', 'delete', or 'equal'")
    text: str = Field(..., description="The text associated with this operation")


class DeltaResponse(BaseModel):
    session_id: str
    version_from: int
    version_to: int
    slide_number: int
    old_text: str
    new_text: str
    diff_hunks: List[DiffHunk]
    reason: str
    provenance: List[str] = Field(default_factory=list, description="chunk_ids that support the new text")
    
    # We also return the newly updated full GenerationOutput so the UI can render the whole thing
    # But in the DB, this is just the delta record.
