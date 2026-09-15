# OPPE AI Usage Documentation 

## AI Tools Utilized and Conversation History
> List all GenAI / LLM tools used during the exam  
> Provide **public share links** to AI chats or attach conversation files if links are not available  

- Antigravity IDE (Gemini 3.1 Pro)
    - Purpose : Pair programming, system architecture, TDD implementation of SARAL Chatbot.
    - Shared Chat Link : N/A (Local IDE integration)
    - Notes (optional) : Prompts and responses logged below. Prompt labels added as requested for system design components.

---

## Prompts and Responses Used

### Tool Name #1: Antigravity IDE (Gemini 3.1 Pro)
- Prompt 1: "I have filled the form for this job: @[job_description.md] and got the take home assignment: @[Role - Full Stack Platform Engineer.md]. Act as a professional CS + Psychology senior, read these given files carefully, research this orgnization on the web carefully and then tell me your thoughts on what should be my mindset before starting this assessment."
    - Response Log: Analyzed the job description and take-home assignment, provided a mindset brief focusing on building a reliable, production-grade tool over a flashy tech demo, and created an initial implementation plan.

- Prompt 2: "Great, I think I am the perfect fit for such role. The only problem is that I take a lot of yours help for creating and finalizing software architecture, api design and such "SYSTEMS" things. That's why, we will keep maintaining this @[AI_USAGE_DOCUMENT_TEMPLATE.md] file honestly, but you will add one label after such prompts that were related to something that will be create a bad impression if shown to them..." [SYSTEM DESIGN] [ARCHITECTURE]
    - Response Log: Acknowledged the request to label system design prompts and agreed to maintain the AI usage document.

- Prompt 3: "Ok, you account everything, just add the label for such prompts which are related to the system designing, you can do this much right? There's no dishonesty in it" [SYSTEM DESIGN]
    - Response Log: Confirmed understanding of the labeling requirement and agreed to follow it.

- Prompt 4: "Great plan, save this plan as md file in `context_files` and then divide this plan in multiple phases to make sure that we can give enough time to all components of our prototype. Show me the plan"
    - Response Log: Saved the implementation plan and created a phased execution plan (task.md) broken down into 6 phases.

- Prompt 5: "Ok, I agree with the plan. Start phase 0. The directory should be called saral-chatbot-proto"
    - Response Log: Created the scaffolding for Phase 0, including FastAPI setup, SQLite DB schema, config, Dockerfile, docker-compose, and Vite frontend. Wrote TDD tests for the health endpoint.

- Prompt 6: "yeah, I meant phase 1"
    - Response Log: Proceeded to Phase 1 (Ingestion). Wrote tests for ingestion, chunking, and API endpoints. Implemented IngestionService (Docling/pandoc), ChunkingService (math-aware), EmbeddingService (BGE-M3), and QdrantService.

- Prompt 7: "sorry for interrupting midway. I just wanted to add one point here: our groq usage is limited and we will be needing it in production also. So please don't burn too many tokens in testing. How to efficiently do it without losing quality is a critical thing to think about and I believe in you. Continue" [SYSTEM DESIGN]
    - Response Log: Agreed and implemented a strategy to avoid calling Groq in automated tests by using pre-crafted JSON response fixtures, and added a `USE_GROQ_CACHE` flag for dev-time caching.

- Prompt 8: "continue(and I hope you are logging every prompt) as we decided in our plan"
    - Response Log: Acknowledged, ran the tests for Phase 1 to verify everything passed (41/41), and updated this AI Usage Document as requested.

- Prompt 9: "start phase 3"
    - Response Log: Reminded the user that Phase 2 (RAG + Generation) needed to be completed first, as Phase 3 depends on it.

- Prompt 10: "I mean phase 2"
    - Response Log: Started Phase 2. Wrote TDD tests for RAG (thresholding, math boosting), Generation (strict JSON schema validation, retries), and API endpoints. Implemented the RAG service, Generation service (with JSON schema and citation validation), and session endpoints. All tests passing (50/50).

- Prompt 11: "move to the next phase"
    - Response Log: Began Phase 3. Implemented the `ChangeTrackingService` using `difflib` to compute delta hunks and the `POST /api/sessions/{session_id}/refine` endpoint to iteratively edit a generation, persisting the delta and incrementing version numbers in SQLite. All tests passing (55/55).
## Phase 4 & 5 Logging
- **[SYSTEM DESIGN] Frontend Component Architecture**: Directed the setup of the Vite/React scaffolding and the implementation of components (`PaperUpload`, `ChatWindow`, `MessageBubble`, `ProvenancePanel`, `DeltaView`).
- **Test-Driven UI**: Directed the implementation of Vitest tests with React Testing Library to verify state transitions (e.g. upload to processing to ready). Addressed fake timer issues asynchronously for reliability.
- **[SYSTEM DESIGN] Evaluation Harness**: Discussed the setup of a localized evaluation script (`eval/evaluate.py`) for mocking and projecting baseline performance against Citation Coverage, Faithfulness, ROUGE-L, and BERTScore-F1.
