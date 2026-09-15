"""
Change Tracking Service - computes deltas, manages iterations.
"""

import asyncio
import difflib
import hashlib
import json
import logging
import os
from typing import List

from groq import AsyncGroq, RateLimitError, APIStatusError
from openai import AsyncOpenAI, RateLimitError as OpenAIRateLimitError, APIStatusError as OpenAPIStatusError
from pydantic import ValidationError

from app.config import settings
from app.models.chunk import Chunk
from app.models.generation import GenerationOutput, Slide
from app.models.refine import DeltaResponse, DiffHunk

log = logging.getLogger(__name__)
_MAX_OUTPUT_TOKENS = 4096


class ChangeTrackingService:
    def __init__(self):
        groq_key = settings.effective_groq_key() or "fake-key"
        self.client = AsyncGroq(api_key=groq_key)
        
        self.openai_client = None
        if settings.openai_api_key:
            self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def apply_delta(
        self,
        session_id: str,
        version_from: int,
        version_to: int,
        old_output: GenerationOutput,
        target_slide_number: int,
        change_instruction: str,
        valid_chunks: List[Chunk]
    ) -> tuple[DeltaResponse, GenerationOutput]:
        """
        Applies a change instruction to a specific slide, computing a diff and a new version.
        Passes adjacent slide summaries to prevent narrative drift (Scenario 3 fix).
        """
        old_slide = next((s for s in old_output.slides if s.slide_number == target_slide_number), None)
        if not old_slide:
            raise ValueError(f"Target slide {target_slide_number} not found in old output.")

        # Extract true original text shown to the user
        if old_slide.sentences and len(old_slide.sentences) > 0:
            original_text = " ".join(s.text for s in old_slide.sentences)
        else:
            original_text = old_slide.script

        # Build narrative anchors: first sentence of the slide immediately before and after
        # the target slide. This gives the LLM enough context to preserve narrative coherence
        # without passing the entire deck (which would blow up context - Scenario 3 fix).
        sorted_slides = sorted(old_output.slides, key=lambda s: s.slide_number)
        idx = next((i for i, s in enumerate(sorted_slides) if s.slide_number == target_slide_number), None)

        prev_summary = (
            sorted_slides[idx - 1].sentences[0].text
            if idx and idx > 0 and sorted_slides[idx - 1].sentences
            else None
        )
        next_summary = (
            sorted_slides[idx + 1].sentences[0].text
            if idx is not None and idx < len(sorted_slides) - 1 and sorted_slides[idx + 1].sentences
            else None
        )

        # Call LLM to get revised slide, passing narrative context
        prompt = self._build_refine_prompt(
            slide_number=old_slide.slide_number,
            original_text=original_text,
            change_instruction=change_instruction,
            chunks=valid_chunks,
            prev_slide_summary=prev_summary,
            next_slide_summary=next_summary
        )
        
        response_text = await self._call_llm_with_cache(prompt)

        try:
            data = json.loads(response_text)
            from app.models.refine import RefinedTextOutput
            refined = RefinedTextOutput(**data)
            new_text = refined.revised_text
        except (json.JSONDecodeError, ValidationError) as e:
            raise ValueError(f"Failed to parse LLM refinement response: {e}")

        # Compute diff on the exact text
        diff_hunks = self._compute_diff(original_text, new_text)

        new_slide = old_slide.model_copy(deep=True)
        new_slide.script = new_text
        new_slide.sentences = []

        # Assemble DeltaResponse
        # Collect provenance from the new slide
        provenance = set()
        for sentence in new_slide.sentences:
            if sentence.source_ids:
                provenance.update(sentence.source_ids)

        delta = DeltaResponse(
            session_id=session_id,
            version_from=version_from,
            version_to=version_to,
            slide_number=target_slide_number,
            old_text=original_text,
            new_text=new_text,
            diff_hunks=diff_hunks,
            reason=refined.reason,
            provenance=list(provenance)
        )

        # Build new GenerationOutput
        new_output = old_output.model_copy(deep=True)
        # Replace the slide
        for i, s in enumerate(new_output.slides):
            if s.slide_number == target_slide_number:
                new_output.slides[i] = new_slide
                break

        # Recompute citation coverage for the entire new output
        valid_chunk_ids = {c.chunk_id for c in valid_chunks}
        valid_citations = 0
        total_sentences = 0
        for slide in new_output.slides:
            for sentence in slide.sentences:
                total_sentences += 1
                if sentence.source_ids and all(sid in valid_chunk_ids for sid in sentence.source_ids):
                    valid_citations += 1
        
        new_output.citation_coverage = valid_citations / total_sentences if total_sentences > 0 else 0.0

        return delta, new_output

    def _compute_diff(self, old_text: str, new_text: str) -> List[DiffHunk]:
        """Computes a word-level or character-level diff using difflib."""
        matcher = difflib.SequenceMatcher(None, old_text.split(), new_text.split())
        hunks = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                hunks.append(DiffHunk(operation='delete', text=' '.join(old_text.split()[i1:i2])))
                hunks.append(DiffHunk(operation='insert', text=' '.join(new_text.split()[j1:j2])))
            elif tag == 'delete':
                hunks.append(DiffHunk(operation='delete', text=' '.join(old_text.split()[i1:i2])))
            elif tag == 'insert':
                hunks.append(DiffHunk(operation='insert', text=' '.join(new_text.split()[j1:j2])))
            elif tag == 'equal':
                hunks.append(DiffHunk(operation='equal', text=' '.join(old_text.split()[i1:i2])))
        return hunks

    def _build_refine_prompt(
        self,
        slide_number: int,
        original_text: str,
        change_instruction: str,
        chunks: List[Chunk],
        prev_slide_summary: str | None = None,
        next_slide_summary: str | None = None,
    ) -> str:
        context = ""
        for c in chunks:
            context += f"\n[CHUNK_ID: {c.chunk_id} | PAGE: {c.page_number}]\n{c.text}\n"

        from app.models.refine import RefinedTextOutput
        schema_json = RefinedTextOutput.model_json_schema()

        # Build a minimal narrative anchor block - very few tokens but prevents drift (Scenario 3)
        narrative_anchor = ""
        if prev_slide_summary:
            narrative_anchor += f"\nThe slide BEFORE this one begins with: \"{prev_slide_summary}\""
        if next_slide_summary:
            narrative_anchor += f"\nThe slide AFTER this one begins with: \"{next_slide_summary}\""
        if narrative_anchor:
            narrative_anchor = "\nNarrative Context (for coherence, do not reproduce verbatim):" + narrative_anchor + "\n"

        return f"""You are an expert academic communicator.
The user wants to refine Slide {slide_number} of their presentation.

Change Instruction: "{change_instruction}"

<original_text>
{original_text}
</original_text>
{narrative_anchor}
Available Source Context (for reference):
{context}

Rewrite the original_text above according to the instruction.
You MUST output ONLY valid JSON matching the following schema.
Do not repeat the original_text verbatim anywhere in your output, unless instructed to keep parts of it.

Schema:
{json.dumps(schema_json, indent=2)}
"""

    async def _call_llm_with_cache(self, prompt: str) -> str:
        if settings.use_groq_cache:
            cache_key = hashlib.md5(prompt.encode()).hexdigest()
            cache_path = os.path.join(settings.groq_cache_dir, f"{cache_key}.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    return f.read()

        response = await self._call_llm(prompt)

        if settings.use_groq_cache:
            os.makedirs(settings.groq_cache_dir, exist_ok=True)
            with open(cache_path, "w") as f:
                f.write(response)

        return response

    async def _call_llm(self, prompt: str) -> str:
        """Route to OpenAI if configured, otherwise fallback to Groq."""
        if self.openai_client:
            try:
                return await self._call_openai(prompt)
            except Exception as e:
                log.warning(f"OpenAI refinement failed ({e}). Falling back to Groq.")
        
        return await self._call_groq(prompt)

    async def _call_openai(self, prompt: str) -> str:
        """Calls OpenAI with automatic retry on rate limits."""
        for attempt in range(4):
            try:
                response = await self.openai_client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a JSON-only API. Return ONLY raw JSON conforming to the requested schema. "
                                "CRITICAL GROUNDING RULE: Every sentence's source_ids MUST contain chunk IDs "
                                "from the provided CHUNK_ID list. Never invent or hallucinate chunk IDs. "
                                "Do not wrap output in markdown code fences."
                            )
                        },
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=_MAX_OUTPUT_TOKENS,
                )
                return response.choices[0].message.content

            except OpenAIRateLimitError as e:
                wait = 2 ** attempt
                log.warning("OpenAI rate limit hit (attempt %d/%d). Retrying in %ds. %s", attempt + 1, 4, wait, e)
                if attempt == 3:
                    raise
                await asyncio.sleep(wait)
            except OpenAPIStatusError as e:
                log.error("OpenAI API error: %s", e)
                raise

    async def _call_groq(self, prompt: str) -> str:
        """
        Calls Groq with automatic retry on rate limits (Scenario 1 fix).
        Grounding constraint in system message for max LLM attention (Scenario 4 fix).
        """
        for attempt in range(4):
            try:
                response = await self.client.chat.completions.create(
                    model=settings.groq_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a JSON-only API. Return ONLY raw JSON conforming to the requested schema. "
                                "CRITICAL GROUNDING RULE: Every sentence's source_ids MUST contain chunk IDs "
                                "from the provided CHUNK_ID list. Never invent or hallucinate chunk IDs. "
                                "Do not wrap output in markdown code fences."
                            )
                        },
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=_MAX_OUTPUT_TOKENS,
                )
                return response.choices[0].message.content

            except RateLimitError as e:
                wait = 2 ** attempt
                log.warning("Groq rate limit hit (attempt %d/4). Retrying in %ds.", attempt + 1, wait)
                if attempt == 3:
                    raise
                await asyncio.sleep(wait)

            except APIStatusError as e:
                if e.status_code == 413 or "context_length" in str(e).lower():
                    raise ValueError(
                        f"Prompt exceeded Groq context window. Original error: {e}"
                    ) from e
                raise
