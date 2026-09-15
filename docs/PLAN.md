# SARAL Part B: 1-Page Plan

## 1. Retrieval Index Construction
Our retrieval index leverages a local vector database (Qdrant) to ensure privacy and low latency. Documents are ingested asynchronously to prevent event-loop starvation. We use **BGE-M3** embeddings, which excel at multi-lingual and dense academic text representations. To optimize for memory and compute, embeddings are generated in batches (size=16) via a dedicated `ThreadPoolExecutor`.

## 2. Math-Preserving Chunking Strategy
Standard sliding-window chunking (e.g., fixed 500-token splits) breaks scientific literature by severing LaTeX environments or Markdown tables. 
We employ an **AST-Aware, Delimiter-Respecting Chunker**:
- It utilizes regular expressions to detect atomic environments (`$$...$$`, `\begin{equation}...\end{equation}`).
- It guarantees these blocks are never bisected. If a block exceeds the token limit, it falls back to splitting on natural sentence boundaries (`\n\n`, `. `) outside the math environment.
- Each chunk is enriched with metadata (`page_number`, `has_math`, `section_title`) to allow downstream filtering.

## 3. Parameterized Prompt Template Family
Our generation pipeline relies on a strict, system-level prompt template family parameterized by `{audience}`, `{length}`, `{style}`, and `{change_instruction}` (for refinement). 

### Base Prompt Template Formulation:
> **System:** You are an academic presentation synthesizer. Return ONLY valid JSON.
> **Rules:**
> 1. Grounding: Every generated sentence MUST map to a provided `[chunk_id]`.
> 2. Structure: Generate exactly `{length}` slides.
> 3. Tone: Adapt the script for `{audience}` using a `{style}` style.
> 4. Refinement (If applicable): Apply the following editorial instruction: `{change_instruction}`.

### Instantiated Example 1: The Initial Generation
- **Parameters:** `{audience: "Policymakers"}`, `{length: "3 slides (90s)"}`, `{style: "Plain-English"}`, `{change_instruction: None}`
- **Resulting Behavior:** The LLM strips away dense academic jargon, replacing it with high-level impact statements. It generates exactly 3 JSON slide objects, mapping claims back to the chunks provided by the BGE-M3 retrieval layer.

### Instantiated Example 2: Iterative Refinement
- **Parameters:** `{audience: "Policymakers"}`, `{length: "N/A (Target: Slide 2)"}`, `{style: "Plain-English"}`, `{change_instruction: "Make this less technical and focus on the economic impact."}`
- **Resulting Behavior:** Instead of passing the whole deck, we pass only the `original_text` of Slide 2. The LLM acts purely as an editor, outputting a `revised_text` and a `reason`. Our `ChangeTrackingService` then computes an algorithmic diff (`difflib`) to show exactly what words were added or removed, preventing any LLM-induced structural hallucinations.
