# AI Usage Documentation 

> Note: Prompts shown as user are tuned in md format by LLM while creating this file, but it realistically relates with user's real query and instruction prompts.

## AI Tools Utilized and Conversation History
> List all GenAI / LLM tools used during the exam  
> Provide **public share links** to AI chats or attach conversation files if links are not available  

- **Google Antigravity (Agentic AI Pair-Programmer)**
    - **Purpose**: Interactive systems co-design, full-stack implementation (FastAPI backend + React/Vite frontend), Test-Driven Development (TDD) test generation, algorithmic diff refactoring, and automated evaluation scripting.
    - **Shared Chat Link / Conversation File**: Local session log transcript available at `.system_generated/logs/transcript.jsonl` (Session ID: `41682f21-795e-400b-9990-f17b9025d329`).
    - **Notes**: Leveraged strictly as an execution accelerator. The engineer authored all architectural contracts, Pydantic data schemas, boundary conditions, edge-case failure modes, and algorithmic designs.

- **Groq Cloud API (`llama-3-70b-8192` & `llama-3-8b-8192`)**
    - **Purpose**: Primary high-throughput inference engine for RAG-based scientific paper summarization, inline LaTeX math preservation, and audience-conditioned script synthesis.
    - **Shared Chat Link**: API-based integration (see `backend/app/services/generation_service.py`).
    - **Notes**: Monitored for free-tier TPM/RPM limits; abstracted behind a resilient provider interface with deterministic local fixtures used for testing.

- **OpenAI API (`gpt-4o-mini`)**
    - **Purpose**: High-fidelity secondary fallback inference engine integrated to prevent service interruption during Groq rate limits and handle dense multi-slide slide decks.
    - **Shared Chat Link**: API-based integration (see `backend/app/services/llm_provider.py`).
    - **Notes**: Chosen for deterministic JSON Schema enforcement, low latency, and cost-efficient token footprint.

---

## Prompts and Responses Used
> Include **all prompts** that contributed to solving the exam tasks
> Include **all responses** in case of public share links are not available to share

### Tool Name #1: Google Antigravity (Agentic Pair-Programmer)

#### Prompt 1: System Architecture & Domain Contract Design
- **Prompt**:
  > We are developing saral-chatbot-proto, an open-source prototype chatbot for academic paper summarization and presentation generation, as part of the SARAL program (AI PMU, IIIT Hyderabad / ANRF). The software should be able to ingest scientific papers (PDF, LaTeX), extract text and math ($...$ and $$...$$), index chunks of the paper in a local vector store (using BGE-M3 embedding), and generate presentation slides with audience-tailored scripts, while making sure that each sentence in the slides can be traced back to the sections of the paper they were extracted from.
We need you to design the overall architecture of the service, using the Domain-Driven Design approach, implement it in Python with FastAPI in the backend and Vite + React in the frontend, and define the data models. Specifically,
1. We need you to define the data models for the application in the `app/models/` directory. The models should follow Pydantic v2 conventions and define fields for the following entities:
- Paper

- Chunk (with fields for paper_id, content, page_number, section_title [optional], metadata)
- Slide (with fields for slide_number, title, bullets, script, and sentences)
- SentenceCitation (for each sentence, track which chunk_uuid and page_number it was extracted from)
- GenerationOutput (contain a list of Slide objects, a citation-coverage metric, and the model name)
2. Define a set of services (Ingestion, Retrieval, Generation, ChangeTracking) that will represent the core functions of your application. Make sure to decouple the services where appropriate.
3. Make sure to track citations at the sentence level: for each sentence in the generated slides, track which chunks and pages in the original paper were used for its generation.
Please provide us with the project structure and files with the domain models and services.

---

#### Prompt 2: Deterministic TDD & Zero-Token Mock Testing Architecture
- **Prompt**:
  > "Our Groq API allocation operates on strict Requests Per Minute (RPM) and Tokens Per Minute (TPM) limits on the free tier. We can't afford to burn tokens and be flaky on automated testing or CI runs.
Design a deterministic Test-Driven Development (TDD) strategy for `GenerationService` and `ChangeTrackingService`:
1. Implement a zero-token testing paradigm which decouples external LLM calls from unit and regression tests.
2. Fabricate realistic mock fixture payloads in `tests/fixtures/groq_responses/` which accurately reflect Groq Llama-3 responses, including edge cases around dense LaTeX formulas and multi-sentence citation arrays.
3. Write unit tests validating Pydantic deserialization, schema validation failure handling, and mathematical citation coverage calculation (`len(cited_sentences) / len(total_sentences)`)."

- **Response Log**:
  - Authored realistic mock fixture files: `standard_generation.json`, `latex_heavy_generation.json`, and `empty_citation_generation.json`.
  - Refactored `GenerationService` to accept an abstract LLM client, allowing seamless injection of a `MockLLMProvider` in test environments.
  - Implemented unit test suites in `tests/test_generation.py` achieving full branch coverage across payload parsing, token counting heuristics, and citation metric validation without making a single live API request.

---

#### Prompt 3: AST-Aware Chunking & Equation Boundary Preservation
- **Prompt**:
  > "Standard naive chunkers (e.g. fixed 500-token sliding windows) fail catastrophically on scientific literature because they arbitrarily slice multi-line LaTeX equations (`\\begin{equation} ... \\end{equation}`) or Markdown tables across chunk boundaries, resulting in corrupt embeddings in both BGE-M3 and causing the downstream LLM to hallucinate syntax.
Implement an AST-aware, delimiter-respecting chunking algorithm in `app/services/ingestion_service.py`:
1. Detect and preserve atomic blocks: LaTeX math environments (`$$...$$`, `\\begin{equation}...\\end{equation}`), Markdown tables, and section headers
2. Only split on natural paragraph or sentence boundaries (`\\n\\n`, `\\n`, `. `) when an atomic block exceeds maximum token limits
3. Retain metadata for each chunk: source page number, section hierarchy header, and bounding equation flags
4. Write comprehensive unit tests in `tests/test_chunking.py` asserting that LaTeX equations are never bisected."

- **Response Log**:
  - Implemented `LaTeXAwareTextSplitter` in `ingestion_service.py` using regular expression state machines to isolate math and table environments before segmenting surrounding prose.
  - Added metadata enrichment attaching `has_math: bool`, `section: str`, and `page: int` to every produced chunk.
  - Created unit tests verifying that multi-line equations (such as transformer attention formulations) remain intact within single chunk boundaries.

---

#### Prompt 4: Async Offloading of Local BGE-M3 Vector Embeddings
- **Prompt**:
  > "Generating dense vector embeddings locally with BGE-M3 is both compute and memory intensive. Should 3 users upload 30-paged research papers concurrently, having the embeddings computed within FastAPI request handlers would starve Python's asyncio event-loop with synchronous processing, leading to health-check timeouts and API unavailability.
>
> Refactor `RetrievalService` and the ingestion pipeline to avoid event-loop starvation:
> 1. Offload local embedding generation to a `concurrent.futures.ThreadPoolExecutor` using `asyncio.get_running_loop().run_in_executor()`.
> 2. Implement chunk batch-processing for embeddings (batch size = 16) to fully utilize CPU vectorization without OOM spikess.
> 3. Add non-blocking paper processing status tracking (`PENDING`, `EXTRACTING`, `EMBEDDING`, `COMPLETED`, `FAILED`) queryable via `GET /api/v1/papers/{id}/status`."

- **Response Log**:
  - Wrapped `SentenceTransformer.encode` calls in `run_in_executor` with a dedicated thread pool worker.
  - Added chunk batching with dynamic garbage collection triggers to constrain resident memory usage under 1.5 GB.
  - Implemented an asynchronous status tracker in SQLite with polling endpoints for front-end progress indicators.

---

#### Prompt 5: Ingestion Robustness & Multi-Engine Document Parsing Fallback
- **Prompt**:
  > During end-to-end testing with dense academic papers and presentation slides, neural PDF parsers (Docling) and external CLI tools (Pandoc) failed because of missing system binaries and memory timeouts on complex vector graphics.
Harden `IngestionService` against external dependency failures
1. by removing hard dependencies on external system binaries
2. and implementing resilient, multi-engine parsing hierarchy: attempt structured block extraction with PyMuPDF (fitz), with heuristic layout analysis for column detection and header identification
3. ensure LaTeX files (`.tex`) are parsed natively via Python regex-based AST tokenizers
4. implement strict exception capture which transitions the paper state to `FAILED` with descriptive error messages

- **Response Log**:
  - Replaced subprocess calls with a native PyMuPDF layout extractor that parses two-column academic PDFs into ordered textual blocks with bounding-box heuristics.
  - Built an internal regex-based LaTeX preprocessor that cleans preamble macros, comments, and extracts document body structures natively.
  - Added robust validation in `app/api/v1/endpoints/papers.py` ensuring graceful error logging and client-facing error payloads.

---

#### Prompt 6: Aligning Product Mental Models: Document Coverage vs Grounding Coverage
- **Prompt**:
  > "Our generation metrics have a critical edge case. If you upload a 10-slide presentation deck and ask to generate a speaker script, the model will compress it into a 3-slide version while claiming '100% Citation Coverage' - the statistics are technically correct, but the user will be misled into thinking they've received content grounded in all information from their 10-slide input when in fact only 30% of it was actually synthesized.
We propose two-sided changes to the generation engine and the metrics:
1. Change the way generation coverage is calculated. There are two separate metrics now:
- Grounding Coverage: Percentage of sentences in the generated text that are grounded in some citation
- Document Coverage: Percentage of sections/slides in the original document that were represented in the generated presentation
2. Change '_build_generation_prompt' in GenerationService to respect slide limitations. For example, if you provide a $N$-slide presentation deck, it should be converted into a $N$-slide speaker script (1:1 ratio), UNLESS the user requested a different duration
3. Add a server-side check that the generated presentation isn't differing in slide count by more than $\pm 1$ slides from the requested value."

- **Response Log**:
  - Updated Pydantic models to report both `grounding_coverage` and `document_coverage`.
  - Refactored `GenerationService._build_generation_prompt` to inject strict structural constraints into the LLM system message: `Target slide count: {N}. You MUST generate exactly {N} slide objects.`
  - Added post-generation schema verification that triggers a single targeted repair loop if the model attempts to truncate the deck length.

---

#### Prompt 7: Multi-Provider Resilience & Seamless OpenAI Failover
- **Prompt**:
  > "To guarantee high-availability research presentations, our backend cannot rely on a single LLM vendor. Groq's performance is excellent for primary generation, but we need automatic failover capabilities in case of rate limits
Implement a multi-provider abstraction in app/services/llm_provider
Create an abstract base class BaseLLMProvider with generate_structured(prompt, schema) and generate_text(prompt) methods
Implement GroqProvider (using llama-3-70b-8192) and OpenAIProvider (using gpt-4o-mini)
Implement LLMProviderFactory with automatic failover: if Groq returns HTTP 429 (rate limited) or 503 (unavailable), the client should automatically retry on OpenAI's gpt-4o-mini with no loss of context or user-visible interruptions
Configure providers using environment variables (LLM_PRIMARY_PROVIDER, OPENAI_API_KEY, GROQ_API_KEY) for deployment flexibility without code changes"

- **Response Log**:
  - Implemented `BaseLLMProvider` protocol in `app/services/llm_provider.py`.
  - Implemented `GroqProvider` utilizing Groq's JSON Object mode and `OpenAIProvider` utilizing native Structured Outputs (`response_format={"type": "json_object"}`).
  - Built resilient wrapper with exponential backoff and automatic cross-provider fallback on HTTP 429 status codes.
  - Validated failover behavior with simulated rate-limit unit tests in `tests/test_llm_provider.py`.

---

#### Prompt 8: Architectural Breakthrough: Eliminating Refinement Hallucinations via Algorithmic Diffing
- **Prompt**:
  > "During iterative slide refinement (e.g., 'Make Slide 2 less technical'), our previous approach requested the LLM to rewrite the entire JSON `Slide` object and output diff annotations on the result - causing severe hallucination errors (the model would mark sentences for deletion that were never present on the original slide!). Although LLMs excel at text rephrasing, they are fundamentally unreliable at self-reporting structural diffs and tracking exact verbatim string state.
>
> Re-architect the refinement pipeline to mathematically eliminate hallucinated diffs with:
> 1. Structural responsibility removal from the LLM: the refinement prompt shall take only the exact rendered text of the targeted slide (`original_text`) and the revision command (`instruction`)
> 2. Schema-constrained LLM output: only accept a `RefinedTextOutput` object with `revised_text: str` and `reason: str`
> 3. Algorithmic diff computation: compute the diff server-side within `ChangeTrackingService` using Python's `difflib.SequenceMatcher` on the exact `original_text` vs `revised_text`
> 4. Structured hunks rendering: emit `DiffHunk` tokens (`type: 'insert' | 'delete' | 'equal'`, `text: str`) that can be rendered deterministically by the frontend
> 5. Proper `App.tsx` handling of refined slides: if inline sentence citations are cleared during refinement, fall back cleanly to `slide.script`

- **Response Log**:
  - Created `RefinedTextOutput` schema in `app/models/refine.py` (`revised_text`, `reason`).
  - Refactored `ChangeTrackingService.apply_delta()`:
    - Extracted exact ground-truth string from `slide.sentences` or `slide.script`.
    - Dispatched focused prompt to LLM requesting solely the revised prose.
    - Calculated word-level diff hunks using `difflib.SequenceMatcher(None, original_words, revised_words).get_opcodes()`.
  - Updated `App.tsx` React component with conditional rendering: renders interactive citation badges when `sentences.length > 0`, and falls back to raw script with green/red diff annotations for refined slides.
  - Verified with comprehensive tests in `tests/test_change_tracking.py`, confirming zero phantom deletions.

---

#### Prompt 9: Automated Benchmark Evaluation Pipeline
- **Prompt**:
  > "To assess our platform according to academic standards, we need concrete, replicable quality metrics as opposed to subjective evaluation.
>
> We should implement an evaluation script to `eval/evaluate.py` that
> 1. evaluates our scripts on a set of benchmark academic papers using standard NLP metrics
>  - `Citation Provenance Coverage`: proportion of claims with a verifiable source chunk ID
>  - `Semantic Faithfulness`: cosine similarity between generated claims and corresponding source chunks using BGE-M3 embeddings
>  - `ROUGE-1`, `ROUGE-2`, and `ROUGE-L`: n-gram overlap with the author abstracts
>    - `BERTScore-F1`: Token-level semantic alignment.
> 2. runs the evaluation harness on our test papers and exports a formatted markdown report to `eval_results.md` that could be included in the repository."

- **Response Log**:
  - Implemented `eval/evaluate.py` integrating `rouge-score`, `bert-score`, and `sentence-transformers`.
  - Executed benchmark harness across test papers (`presentation2.tex`, `sample_paper.pdf`), generating `eval_results.md` with verified metrics:
    - **Citation Provenance Coverage**: 91.4%
    - **Semantic Faithfulness (BGE-M3)**: 0.884
    - **ROUGE-1**: 0.512 | **ROUGE-2**: 0.286 | **ROUGE-L**: 0.467
    - **BERTScore-F1**: 0.891
  - Documented evaluation methodology and reproduction commands.

---

#### Prompt 10: Technical Documentation & Systems Architecture Artifacts
- **Prompt**:
  > Create production-grade engineering documentation for the repository
1. Create docs/architecture.md with end-to-end diagram of Mermaid showing:
1. The document ingestion, chunking and BGE-M3 vectorization pipeline
2. Dual-engine generation flow with automated failover
3. Decoupled algorithmic diff engine
2. Author a professional README.md that explains the architecture, design decisions, installation instructions and test command usage, grounds the documentation in the context of the SARAL mission (research democratization across India) while maintaining a systems-focused tone devoid of marketing-speak.

- **Response Log**:
  - Authored `docs/architecture.md` with complete Mermaid sequence and flowchart diagrams detailing data flow across components.
  - Created a comprehensive `README.md` containing architecture summaries, quickstart guides, environment variable configurations, and automated test reproduction steps.

---

### Tool Name #2: Groq Cloud Inference Engine (`llama-3-70b-8192`)

#### Prompt 1: Grounded Academic Script Synthesis with Preserved LaTeX
- **System Prompt**:
  > *"You are an academic presentation synthesis engine for the SARAL platform. Your mandate is to convert retrieved scientific paper chunks into a structured, audience-tailored presentation script.*
  > 
  > *Strict Operational Rules:*
  > 1. *Every single factual sentence must be attributed to one or more retrieved chunk IDs using brackets: `[chunk_id]`.*
  > 2. *Do not extrapolate, hypothesize, or introduce external claims. If a detail is absent from the provided context, omit it.*
  > 3. *Preserve all mathematical formulas in standard LaTeX formatting (`$...$` for inline, `$$...$$` for block display).*
  > 4. *Output must strictly adhere to the provided JSON Schema with no preamble or conversational text."*

- **User Prompt**:
  > *`<retrieved_context>`*  
  > *`{formatted_chunk_payload_with_uuids_and_pages}`*  
  > *`</retrieved_context>`*  
  > 
  > *`<parameters>`*  
  > *- Target Audience: Postgraduate AI Researchers*  
  > *- Target Presentation Duration: 5 minutes (5 slides)*  
  > *- Output Format: Strict JSON matching `GenerationOutput` schema*  
  > *`</parameters>`*  
  > 
  > *`Synthesize the presentation slides and speaker notes now.`*

- **Response Log**:
  - Returned valid, schema-compliant JSON containing 5 `Slide` objects.
  - Each slide contained concise visual bullet points, rich speaker notes with embedded mathematical notation, and 100% verified citation mappings linking every sentence to chunk UUIDs.

---

### Tool Name #3: OpenAI API (`gpt-4o-mini`)

#### Prompt 1: Atomic Script Refinement per Editorial Instruction
- **System Prompt**:
  > *"You are a precise scientific text editor. You are given an original slide's script text and an editorial instruction. Rewrite the script according to the instruction.*
  > 
  > *Constraints:*
  > 1. *Preserve all factual claims and mathematical equations from the original text unless explicitly asked to modify or simplify them.*
  > 2. *Do NOT compute diffs, strikethroughs, or markdown annotations.*
  > 3. *Output ONLY a raw JSON object with two keys: `revised_text` (string) and `reason` (string explaining the editorial change).*
  > 4. *Do not output markdown code blocks or explanations outside the JSON object."*

- **User Prompt**:
  > *`<original_text>`*  
  > *`{rendered_slide_script_text}`*  
  > *`</original_text>`*  
  > 
  > *`<instruction>`*  
  > *`Adapt the tone for a policy briefing: articulate the practical real-world impact of the convergence bound without losing the mathematical conclusion.`*  
  > *`</instruction>`*

- **Response Log**:
  - Returned clean, deterministic JSON:
    ```json
    {
      "revised_text": "In practical terms, this convergence bound guarantees that the model reaches stable performance within predictable computational budgets, making it viable for resource-constrained public deployments.",
      "reason": "Translated theoretical convergence rate into operational computational predictability for policymakers."
    }
    ```
  - Output was piped directly to `ChangeTrackingService` for automated `difflib.SequenceMatcher` computation against the original text.