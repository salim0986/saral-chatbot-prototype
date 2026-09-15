"""
Generation Service - constructs prompts, calls Groq, and strictly validates output.
Includes 3-layer validation, automatic retries, and fallback flagging.
"""

import asyncio
import hashlib
import json
import logging
import os
from groq import AsyncGroq, RateLimitError, APIStatusError
from openai import AsyncOpenAI, RateLimitError as OpenAIRateLimitError, APIStatusError as OpenAPIStatusError
from pydantic import ValidationError

from app.config import settings
from app.models.chunk import Chunk
from app.models.generation import (
    GenerationOutput, OutputType, Audience, Length, Style
)

log = logging.getLogger(__name__)

_TOKEN_CAPS = {
    Length.THIRTY_SEC: 1024,
    Length.NINETY_SEC: 2048,
    Length.FIVE_MIN: 6144,
}

class GenerationService:
    def __init__(self):
        # We allow api_key to be None during tests if we're patching _call_groq
        groq_key = settings.effective_groq_key() or "fake-key"
        self.client = AsyncGroq(api_key=groq_key)
        
        self.openai_client = None
        if settings.openai_api_key:
            self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate(
        self,
        paper_id: str,
        chunks: list[Chunk],
        audience: Audience,
        length: Length,
        style: Style,
        output_type: OutputType,
    ) -> GenerationOutput:
        """
        Generates content from chunks with up to 3 retries for citation validation.
        """
        # Filter chunks to prevent "lost in the middle" hallucination for short lengths
        selected_chunks = self._select_chunks_for_length(chunks, length)
        
        prompt = self._build_prompt(selected_chunks, audience, length, style, output_type)
        valid_chunk_ids = {c.chunk_id for c in selected_chunks}

        for attempt in range(3):
            # 1. Call LLM (with dev cache support)
            response_text = await self._call_llm_with_cache(prompt, length)
            
            try:
                # 2. Schema Validation (Pydantic)
                data = json.loads(response_text)
                output = GenerationOutput(**data)

                # 3. Citation & Structure Validation
                coverage = self._calculate_coverage(output, valid_chunk_ids)
                output.citation_coverage = coverage

                if coverage >= settings.citation_coverage_threshold and self._slide_count_valid(output, length):
                    return output

            except (json.JSONDecodeError, ValidationError) as e:
                # Fall through to retry on bad schema
                pass

        # If we exhausted retries, return the last output but flag it
        try:
            data = json.loads(response_text)
            output = GenerationOutput(**data)
            output.citation_coverage = self._calculate_coverage(output, valid_chunk_ids)
            output.low_confidence = True
            return output
        except (json.JSONDecodeError, ValidationError):
            # Absolute worst case fallback if schema never parsed
            return GenerationOutput(
                output_type=output_type,
                audience=audience,
                length=length,
                slides=[],
                citation_coverage=0.0,
                low_confidence=True
            )

    def _calculate_coverage(self, output: GenerationOutput, valid_chunk_ids: set[str]) -> float:
        valid_citations = 0
        total_sentences = 0
        for slide in output.slides:
            for sentence in slide.sentences:
                total_sentences += 1
                if sentence.source_ids and all(sid in valid_chunk_ids for sid in sentence.source_ids):
                    valid_citations += 1
        return valid_citations / total_sentences if total_sentences > 0 else 0.0

    def _select_chunks_for_length(self, chunks: list[Chunk], length: Length) -> list[Chunk]:
        """
        Filters chunks based on target length to prevent hallucination from over-stuffing
        the context window for short requests.
        """
        if not chunks:
            return chunks
            
        if length == Length.FIVE_MIN:
            # Broad coverage for long scripts (up to 30)
            return chunks[:30]
            
        # For shorter outputs, use a position-based heuristic: Intro + Conclusion
        k = 4 if length == Length.NINETY_SEC else 2
        
        if len(chunks) <= k:
            return chunks
            
        # Always take the first chunk (abstract/intro) and last chunk (conclusion)
        # Fill the rest with early chunks (intro/methods)
        selected = [chunks[0]]
        for i in range(1, k - 1):
            selected.append(chunks[i])
        selected.append(chunks[-1])
        
        return selected

    def _slide_count_valid(self, output: GenerationOutput, length: Length) -> bool:
        bounds = {
            Length.THIRTY_SEC: (1, 2),
            Length.NINETY_SEC: (3, 5),
            Length.FIVE_MIN: (8, 12),
        }
        lo, hi = bounds[length]
        return lo <= len(output.slides) <= hi

    def _build_prompt(self, chunks: list[Chunk], audience: Audience, length: Length, style: Style, output_type: OutputType) -> str:
        context = ""
        valid_ids = []
        for c in chunks:
            valid_ids.append(c.chunk_id)
            context += f"\n[CHUNK_ID: {c.chunk_id} | PAGE: {c.page_number}]\n{c.text}\n"

        structure_rules = {
            Length.THIRTY_SEC: "exactly 1 to 2 slides",
            Length.NINETY_SEC: "exactly 3 to 5 slides",
            Length.FIVE_MIN: "exactly 8 to 12 slides, structured as Introduction, Core Concepts, Results, and Conclusion",
        }[length]

        schema_json = GenerationOutput.model_json_schema()

        prompt = f"""<task>
Transform the research paper context below into a {output_type.value} for {audience.value},
in a {style.value} style, lasting {length.value}.
</task>

<valid_chunk_ids>
{json.dumps(valid_ids)}
</valid_chunk_ids>

<context>
{context}
</context>

<structural_requirement>
You MUST produce {structure_rules}. This is a hard requirement, not a suggestion.
</structural_requirement>

<schema>
{json.dumps(schema_json, indent=2)}
</schema>

<example>
{{"slides": [{{"title": "Example", "bullets": ["Point 1"], "script": "Script here", "speaker_notes": "Notes", "slide_number": 1, "sentences": [
  {{"text": "Short grounded claim.", "source_ids": ["{valid_ids[0] if valid_ids else 'chunk_1'}"], "source_pages": [1]}}
]}}], "output_type": "{output_type.value}", "audience": "{audience.value}", "length": "{length.value}", "citation_coverage": 1.0, "low_confidence": false}}
</example>

<final_reminders>
- Output ONLY the JSON object. No markdown fences, no commentary.
- Every source_ids value MUST come from valid_chunk_ids above - never invent one.
- If you cannot ground a sentence in the provided chunks, omit the sentence rather than guessing a source_id.
- Slide count MUST satisfy the structural_requirement above - count your slides before finishing.
</final_reminders>
"""
        return prompt

    async def _call_llm_with_cache(self, prompt: str, length: Length) -> str:
        if settings.use_groq_cache:
            cache_key = hashlib.md5(prompt.encode()).hexdigest()
            cache_path = os.path.join(settings.groq_cache_dir, f"{cache_key}.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    return f.read()

        response = await self._call_llm(prompt, length)

        if settings.use_groq_cache:
            os.makedirs(settings.groq_cache_dir, exist_ok=True)
            with open(cache_path, "w") as f:
                f.write(response)

        return response

    async def _call_llm(self, prompt: str, length: Length) -> str:
        """Route to OpenAI if configured, otherwise fallback to Groq."""
        if self.openai_client:
            try:
                return await self._call_openai(prompt, length)
            except Exception as e:
                log.warning(f"OpenAI generation failed ({e}). Falling back to Groq.")
        
        return await self._call_groq(prompt, length)

    async def _call_openai(self, prompt: str, length: Length) -> str:
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
                                "GROUNDING RULE: every sentence's source_ids must be drawn from valid_chunk_ids - never invent one; "
                                "omit ungroundable sentences instead. "
                                "LENGTH RULE: you must produce the exact slide count range given in structural_requirement - "
                                "this is validated programmatically and non-compliant output will be rejected. "
                                "Do not wrap output in markdown code fences."
                            )
                        },
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=_TOKEN_CAPS[length],
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

    async def _call_groq(self, prompt: str, length: Length) -> str:
        """
        Calls Groq with automatic retry on rate limits (Scenario 1 fix).
        Caps output tokens based on requested length to avoid burning quota or truncating.
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
                                "GROUNDING RULE: every sentence's source_ids must be drawn from valid_chunk_ids - never invent one; "
                                "omit ungroundable sentences instead. "
                                "LENGTH RULE: you must produce the exact slide count range given in structural_requirement - "
                                "this is validated programmatically and non-compliant output will be rejected. "
                                "Do not wrap output in markdown code fences."
                            )
                        },
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=_TOKEN_CAPS[length],
                )
                return response.choices[0].message.content

            except RateLimitError as e:
                # Scenario 1: Groq rate limit - exponential backoff
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s
                log.warning("Groq rate limit hit (attempt %d/%d). Retrying in %ds. %s", attempt + 1, 4, wait, e)
                if attempt == 3:
                    raise  # re-raise after final attempt
                await asyncio.sleep(wait)

            except APIStatusError as e:
                if e.status_code == 413 or "context_length" in str(e).lower():
                    # Context too large - this should not happen if retrieval_k_ceiling is sane,
                    # but raise with a clear message rather than hanging.
                    raise ValueError(
                        f"Prompt exceeded Groq context window. Reduce chunk count (current ceiling: "
                        f"{settings.retrieval_k_ceiling}). Original error: {e}"
                    ) from e
                raise  # re-raise all other API errors immediately
